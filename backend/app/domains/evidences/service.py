import os, re, tempfile, json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from bson import ObjectId

from app.db.mongo import get_db, get_fs
from app.db.db_upload import preprocessor_upload_file, preprocessor_save_prompt
from app.domains.messages.service import get_latest_user_message_for_stage

from app.domains.evidences.preprocessor.file_preprocessing import convert_files_to_json, DATA_DIR
from app.domains.evidences.preprocessor.text_preprocessing import inline_to_grouped_json

INPUT_EVIDENCE_COLL = os.getenv("INPUT_EVIDENCE_COLL")
MCP_EVIDENCE_COLL = os.getenv("MCP_EVIDENCE_COLL")

SUPPORTED_INPUT_EXTS = {".json", ".jsonl", ".xml", ".csv"}
UNSUPPORTED_KNOWN_EXTS = {".001", ".evtx", ".pcap", ".pcapng", ".vmdk", ".img", ".zip", ".gz", ".xz"}
ALLOWED_EXTS_FOR_DETECTION = SUPPORTED_INPUT_EXTS | UNSUPPORTED_KNOWN_EXTS

def _is_safe_relative_under_data(token: str) -> bool:
    try:
        p = Path(token.strip().strip('\'"'))
    except Exception:
        return False
    if p.is_absolute():
        return False

    try:
        normalized = p.resolve().parts
    except Exception:
        normalized = p.parts
    if any(part == ".." for part in p.parts):
        return False

    s = str(p)
    if not s or len(s) > 255 or any(ch in s for ch in ["\n", "\r", "\t"]):
        return False
    return True

def _ext_of(token: str) -> str:
    try:
        return Path(token.strip().strip('\'"')).suffix.lower()
    except Exception:
        return ""

def _looks_like_filename(token: str) -> bool:
    t = token.strip().strip('\'"')
    if not t or " " in t:
        return False

    if ":" in t and not ("/" in t or "\\" in t):
        return False
    if t.startswith(("http://", "https://")):
        return False
    ext = _ext_of(t)
    if ext not in ALLOWED_EXTS_FOR_DETECTION:
        return False
    if not _is_safe_relative_under_data(t):
        return False
    return True

def _split_message_to_files_and_inline(msg: str) -> Tuple[List[str], List[str], List[str]]:
    processable_files: List[str] = []
    inline_blocks: List[str] = []
    unprocessed: List[str] = []

    tokens = re.split(r"[\s,;]+", msg or "")
    candidates: List[str] = []
    for t in tokens:
        if not t:
            continue
        if _looks_like_filename(t):
            candidates.append(t.strip().strip('\'"'))

    seen = set()
    uniq_candidates: List[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            uniq_candidates.append(c)

    for rel in uniq_candidates:
        path = DATA_DIR / rel
        ext = _ext_of(rel)
        if path.exists():
            if ext in SUPPORTED_INPUT_EXTS:
                processable_files.append(rel)
            else:
                unprocessed.append(rel)

    blocks, cur = [], []
    for line in (msg or "").splitlines():
        if line.strip() == "":
            if cur:
                blocks.append("\n".join(cur).strip()); cur = []
        else:
            cur.append(line)
    if cur:
        blocks.append("\n".join(cur).strip())

    def looks_structured(s: str) -> bool:
        s2 = s.strip()
        if not s2:
            return False
        if s2.startswith("{") or s2.startswith("["):
            try:
                json.loads(s2); return True
            except Exception:
                pass
        if s2.startswith("<") and s2.endswith(">"):
            return True
        if ("," in s2 or "\t" in s2) and not any(ch in s2 for ch in "{}<>"):
            return True
        return False

    for b in blocks:
        lines = [ln.strip() for ln in b.splitlines() if ln.strip()]
        if lines and all(_looks_like_filename(ln) for ln in lines):
            continue
        if looks_structured(b):
            inline_blocks.append(b)

    return sorted(set(processable_files)), inline_blocks, unprocessed

def _clean_instruction_text(msg: str, file_names: List[str], inline_blocks: List[str], unprocessed: List[str]) -> str:
    if not msg:
        return ""
    known_files = {Path(f).name.lower() for f in (set(file_names) | set(unprocessed))}
    cleaned: List[str] = []
    for ln in msg.splitlines():
        s = ln.strip()
        if not s:
            continue
        if Path(s).name.lower() in known_files:
            continue
        if s.startswith("{") or s.startswith("[") or s.startswith("<") or ("," in s or "\t" in s):
            try:
                json.loads(s)
                continue
            except Exception:
                if s.startswith("<") or ("," in s or "\t" in s):
                    continue
        cleaned.append(s)
    return "\n".join(cleaned).strip()

def create_evidences_from_latest_message(
    *,
    conversation_id: str,
    stage_id: int,
    mode: str = "auto",
    inline_threshold: int = 10 * 1024 * 1024,
) -> Dict[str, Any]:
    db = get_db()
    msg = get_latest_user_message_for_stage(conversation_id, stage_id)
    if not msg:
        raise ValueError("해당 conversation의 user 메시지가 없습니다.")

    file_names, inline_blocks, unprocessed = _split_message_to_files_and_inline(msg["content"])

    with tempfile.TemporaryDirectory() as td:
        out_dir = Path(td)
        out_paths: List[str] = []

        if file_names:
            out_paths += convert_files_to_json(file_names, out_dir=str(out_dir))

        if inline_blocks:
            grouped = inline_to_grouped_json(inline_blocks)
            inline_path = out_dir / "inline_batch.json"
            inline_path.write_text(json.dumps(grouped, ensure_ascii=False, indent=2), encoding="utf-8")
            out_paths.append(str(inline_path))

        instruction = _clean_instruction_text(msg["content"], file_names, inline_blocks, unprocessed)
        
        prompt_id = preprocessor_save_prompt(
            user_prompt=instruction,
            unprocessed_filenames=sorted(set(unprocessed)),
            inline_text_blobs=[],
            attachments=[],
            context_tags=[],
        )

        results: List[Dict[str, Any]] = []
        for p in out_paths:
            try:
                r = preprocessor_upload_file(
                    file_path=p,
                    detected_type="json",
                    mode=mode,
                    inline_threshold_bytes=inline_threshold,
                    extra_meta={
                        "conversation_id": ObjectId(conversation_id) if ObjectId.is_valid(conversation_id) else conversation_id,
                        "stage_id": stage_id,
                        "prompt_ref": ObjectId(prompt_id),
                    },
                )
                meta = db[INPUT_EVIDENCE_COLL].find_one({"_id": ObjectId(r["meta_id"])}, {"filename": 1, "size": 1})
                results.append({
                    "evidence_id": r["meta_id"],
                    "type": "json",
                    "strategy": "gridfs" if "gridfs_id" in r else "inline",
                    "data_gridfs_id": r.get("gridfs_id"),
                    "filename": (meta or {}).get("filename") or Path(p).name,
                    "size": int((meta or {}).get("size") or 0),
                })
            except Exception as e:
                results.append({
                    "evidence_id": "",
                    "type": "json",
                    "strategy": "inline",
                    "data_gridfs_id": None,
                    "filename": Path(p).name,
                    "size": 0,
                    "error": str(e),
                })

    return {"prompt_id": str(prompt_id), "items": results}

def list_input_evidences(conversation_id: Optional[str], stage_id: Optional[int], limit: int = 100) -> List[Dict[str, Any]]:
    db = get_db()
    q: Dict[str, Any] = {}
    if conversation_id:
        q["conversation_id"] = ObjectId(conversation_id) if ObjectId.is_valid(conversation_id) else conversation_id
    if stage_id is not None:
        q["stage_id"] = int(stage_id)
    cur = db[INPUT_EVIDENCE_COLL].find(q, {
        "filename": 1, "size": 1, "created_at": 1, "conversation_id": 1, "stage_id": 1
    }).sort("created_at", -1).limit(limit)

    out: List[Dict[str, Any]] = []
    for d in cur:
        out.append({
            "_id": str(d["_id"]),
            "conversation_id": str(d.get("conversation_id")) if isinstance(d.get("conversation_id"), ObjectId) else d.get("conversation_id"),
            "stage_id": d.get("stage_id"),
            "filename": d.get("filename"),
            "size": d.get("size"),
            "created_at": d.get("created_at"),
        })
    return out

def list_mcp_evidences(conversation_id: Optional[str], stage_id: Optional[int], limit: int = 100) -> List[Dict[str, Any]]:
    db = get_db()
    q: Dict[str, Any] = {}
    if conversation_id:
        q["conversation_id"] = ObjectId(conversation_id) if ObjectId.is_valid(conversation_id) else conversation_id
    if stage_id is not None:
        q["stage_id"] = int(stage_id)
    cur = db[MCP_EVIDENCE_COLL].find(q, {
        "trigger_id": 1, "mcp_name": 1, "tool_name": 1, "created_at": 1,
        "conversation_id": 1, "stage_id": 1,
        "success": 1,
        "response.length": 1,
        }).sort("created_at", -1).limit(limit)

    out: List[Dict[str, Any]] = []
    for d in cur:
        out.append({
            "_id": str(d["_id"]),
            "trigger_id": (str(d.get("trigger_id")) if isinstance(d.get("trigger_id"), ObjectId) else d.get("trigger_id")),
            "conversation_id": str(d.get("conversation_id")) if isinstance(d.get("conversation_id"), ObjectId) else d.get("conversation_id"),
            "stage_id": d.get("stage_id"),
            "mcp_name": d.get("mcp_name"),
            "tool_name": d.get("tool_name"),
            "created_at": d.get("created_at"),
            "success": d.get("success"),
            "response_length": (d.get("response") or {}).get("length"),
        })
    return out

def get_input_evidence_detail(evidence_id: str) -> Optional[Dict[str, Any]]:
    db = get_db(); fs = get_fs(db)
    if not ObjectId.is_valid(evidence_id):
        return None
    d = db[INPUT_EVIDENCE_COLL].find_one({"_id": ObjectId(evidence_id)})
    if not d:
        return None

    detail: Dict[str, Any] = {
        "_id": str(d["_id"]),
        "conversation_id": str(d.get("conversation_id")) if isinstance(d.get("conversation_id"), ObjectId) else d.get("conversation_id"),
        "stage_id": d.get("stage_id"),
        "filename": d.get("filename"),
        "size": d.get("size"),
        "data_gridfs_id": None,
        "ingested_at": d.get("ingested_at"),
        "data": None,
    }

    if d.get("data") is not None:
        try:
            if isinstance(d["data"], (dict, list)):
                detail["data"] = d["data"]
            else:
                detail["data"] = json.loads(d["data"])
        except Exception:
            detail["data"] = None
    elif d.get("raw") is not None:
        try:
            detail["data"] = json.loads(bytes(d["raw"]).decode("utf-8", errors="ignore"))
        except Exception:
            detail["data"] = None
    elif d.get("gridfs_id"):
        detail["data_gridfs_id"] = str(d["gridfs_id"])
    return detail


def preview_input_evidence(evidence_id: str, limit: int = 64 * 1024):
    db = get_db()
    fs = get_fs(db)

    if not ObjectId.is_valid(evidence_id):
        return None

    d = db[INPUT_EVIDENCE_COLL].find_one({"_id": ObjectId(evidence_id)})
    if not d:
        return None

    if d.get("data") is not None:
        return {"type": "inline", "data": d["data"]}

    gid = d.get("gridfs_id")
    if not gid:
        return {"type": "none"}

    g = fs.get(gid)
    head = g.read(limit)
    ctype = d.get("content_type", "application/octet-stream")

    return {"type": "gridfs", "content_type": ctype, "preview": head}

def get_mcp_evidence_detail(evidence_id: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    if not ObjectId.is_valid(evidence_id):
        return None

    d = db[MCP_EVIDENCE_COLL].find_one({"_id": ObjectId(evidence_id)})
    if not d:
        return None

    return {
        "_id": str(d["_id"]),
        "trigger_id": (str(d.get("trigger_id")) if isinstance(d.get("trigger_id"), ObjectId) else d.get("trigger_id")),
        "conversation_id": str(d.get("conversation_id")) if isinstance(d.get("conversation_id"), ObjectId) else d.get("conversation_id"),
        "stage_id": d.get("stage_id"),
        "mcp_name": d.get("mcp_name"),
        "tool_name": d.get("tool_name"),
        "agent_id": d.get("agent_id"),
        "success": d.get("success"),
        "created_at": d.get("created_at"),

        # ✅ 핵심: 상세에서는 request/response 내려줌
        "request": d.get("request"),
        "response": d.get("response"),
    }