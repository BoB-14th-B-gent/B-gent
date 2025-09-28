from typing import Any, Dict, List, Optional
from pathlib import Path
import time, json, mimetypes, hashlib, os
from datetime import datetime, timezone
from bson import ObjectId
from bson.binary import Binary
from pymongo import MongoClient
import gridfs
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")

MAX_INLINE_JSON_BYTES = 1 * 1024 * 1024
GRIDFS_SAMPLE_BYTES = 64 * 1024
BSON_DOC_HARD_LIMIT = 16 * 1024 * 1024

INPUT_EVIDENCE_COLL = os.getenv("INPUT_EVIDENCE_COLL")
PROMPT_COLL = os.getenv("PROMPT_COLL")
MCP_EVIDENCE_COLL = os.getenv("MCP_EVIDENCE_COLL")
TRIGGER_COLL = os.getenv("TRIGGER_COLL")
REPORTS_COLL = os.getenv("REPORTS_COLL")

def _now() -> datetime:
    return datetime.now(timezone.utc)

def get_client() -> MongoClient:
    return MongoClient(MONGO_URI)

def get_db(client: MongoClient):
    return client[DB_NAME]

def get_fs(db) -> gridfs.GridFS:
    return gridfs.GridFS(db)

def _infer_dtype(path: Path, content_type: Optional[str]) -> Optional[str]:
    if content_type:
        if "json" in content_type:
            return "json"
        if "xml" in content_type:
            return "xml"
        if "csv" in content_type:
            return "csv"
    suf = path.suffix.lower()
    if suf == ".json":  return "json"
    if suf == ".xml":   return "xml"
    if suf == ".csv":   return "csv"
    if suf == ".jsonl": return "json"
    return None

def store_file_to_gridfs(fs: gridfs.GridFS, path: str, extra_meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    if p.is_dir():
        raise IsADirectoryError(f"{p} is a directory (expected a file)")

    content_type, _ = mimetypes.guess_type(p.name)
    meta = {
        "filename": p.name,
        "content_type": content_type or "application/octet-stream",
        "size": p.stat().st_size,
        "sha256": hashlib.sha256(p.read_bytes()[:GRIDFS_SAMPLE_BYTES]).hexdigest(),
        "ingested_at": int(time.time()),
    }
    if extra_meta:
        meta.update(extra_meta)

    with p.open("rb") as f:
        file_id = fs.put(f, filename=p.name, metadata=meta)

    gout = fs.get(file_id)
    return {
        "_id": file_id,
        "filename": gout.filename,
        "length": gout.length,
        "uploadDate": getattr(gout, "upload_date", None),
        "metadata": getattr(gout, "metadata", None),
        "contentType": getattr(gout, "content_type", None),
    }

def insert_file_meta(db, collection: str, meta_doc: Dict[str, Any]) -> str:
    meta_doc.setdefault("created_at", _now())
    res = db[collection].insert_one(meta_doc)
    return str(res.inserted_id)

def choose_strategy(size_bytes: int, mode: str, inline_threshold_bytes: int) -> str:
    mode = (mode or "").lower()
    if mode in ("inline", "gridfs"):
        return mode
    return "inline" if size_bytes <= inline_threshold_bytes else "gridfs"

def upload_file(
    file_path: str,
    collection: str,
    *,
    detected_type: Optional[str] = None,
    mode: str = "auto",
    inline_threshold_bytes: int = 10 * 1024 * 1024,
) -> Dict[str, Any]:
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(file_path)
    if p.is_dir():
        raise IsADirectoryError(f"{p} is a directory (expected a file)")

    client = get_client()
    try:
        db = get_db(client)

        size = p.stat().st_size
        content_type, _ = mimetypes.guess_type(p.name)
        dtype = (detected_type or _infer_dtype(p, content_type))

        strategy = choose_strategy(size, mode, inline_threshold_bytes)

        if strategy == "inline" and dtype == "json" and size > MAX_INLINE_JSON_BYTES:
            strategy = "gridfs"

        result: Dict[str, Any] = {"strategy": strategy}

        if strategy == "inline":
            meta_doc: Dict[str, Any] = {
                "source_type": "file_inline",
                "filename": p.name,
                "content_type": content_type or "application/octet-stream",
                "size": size,
                "detected_type": dtype,
                "ingested_at": int(time.time()),
                "stats": {},
            }
            try:
                if dtype == "json":
                    txt = p.read_text(encoding="utf-8", errors="strict")
                    meta_doc["data"] = json.loads(txt)
                else:
                    raw = p.read_bytes()
                    if len(raw) >= BSON_DOC_HARD_LIMIT - 1024:
                        raise ValueError("inline BSON size would exceed limit; use gridfs")
                    meta_doc["raw"] = Binary(raw)
            except Exception as e:
                meta_doc["stats"]["parse_error"] = str(e)
                raw = p.read_bytes()
                if len(raw) >= BSON_DOC_HARD_LIMIT - 1024:
                    strategy = "gridfs"
                else:
                    meta_doc["raw"] = Binary(raw)

            if strategy == "inline":
                result["meta_id"] = insert_file_meta(db, collection, meta_doc)
                return result

        fs = get_fs(db)
        files_doc = store_file_to_gridfs(fs, str(p), extra_meta={"detected_type": dtype})

        sample: Optional[Any] = None
        try:
            if dtype == "json" or (content_type and "text" in content_type):
                sample = (p.read_text(encoding="utf-8", errors="ignore"))[:GRIDFS_SAMPLE_BYTES]
            else:
                sample = Binary(p.read_bytes()[:GRIDFS_SAMPLE_BYTES])
        except Exception:
            sample = None

        meta_doc = {
            "source_type": "file",
            "gridfs_id": files_doc["_id"],
            "filename": files_doc.get("filename"),
            "content_type": (files_doc.get("metadata") or {}).get("content_type"),
            "size": files_doc.get("length"),
            "detected_type": dtype,
            "ingested_at": int(time.time()),
            "stats": {},
            "sample": sample,
        }
        result["meta_id"] = insert_file_meta(db, collection, meta_doc)
        result["gridfs_id"] = str(files_doc["_id"])
        return result
    finally:
        try:
            client.close()
        except Exception:
            pass

def preprocessor_upload_file(
    file_path: str,
    *,
    detected_type: Optional[str] = None,
    mode: str = "auto",
    inline_threshold_bytes: int = 10 * 1024 * 1024,
    extra_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    res = upload_file(
        file_path=file_path,
        collection=INPUT_EVIDENCE_COLL,
        detected_type=detected_type,
        mode=mode,
        inline_threshold_bytes=inline_threshold_bytes,
    )
    if extra_meta:
        c = get_client(); db = get_db(c)
        db[INPUT_EVIDENCE_COLL].update_one(
            {"_id": ObjectId(res["meta_id"])},
            {"$set": extra_meta}
        )
    return res

def preprocessor_save_prompt(
    *,
    user_prompt: str,
    unprocessed_filenames: Optional[List[str]] = None,
    inline_text_blobs: Optional[List[Dict[str, str]]] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
    context_tags: Optional[List[str]] = None,
) -> ObjectId:
    c = get_client(); db = get_db(c)
    doc = {
        "created_at": _now(),
        "user_prompt": user_prompt,
        "unprocessed_filenames": unprocessed_filenames or [],
        "inline_text_blobs": inline_text_blobs or [],
        "attachments": attachments or [],
        "context_tags": context_tags or [],
    }
    return db[PROMPT_COLL].insert_one(doc).inserted_id

def agent_mcp_insert_inline(
    *,
    batch_id: str,
    source: str,
    data: Dict[str, Any],
    message: Optional[str] = None,
) -> ObjectId:
    c = get_client(); db = get_db(c)
    doc = {
        "batch_id": batch_id,
        "created_at": _now(),
        "source": source,
        "storage": "inline",
        "data": data,
        "message": message or "",
    }
    return db[MCP_EVIDENCE_COLL].insert_one(doc).inserted_id

def agent_mcp_upload_file(
    file_path: str,
    *,
    batch_id: str,
    source: str,
    detected_type: Optional[str] = None,
    mode: str = "auto",
    inline_threshold_bytes: int = 10 * 1024 * 1024,
    message: Optional[str] = None,
) -> ObjectId:
    r = upload_file(
        file_path=file_path,
        collection=MCP_EVIDENCE_COLL,
        detected_type=detected_type,
        mode=mode,
        inline_threshold_bytes=inline_threshold_bytes,
    )
    c = get_client(); db = get_db(c)
    db[MCP_EVIDENCE_COLL].update_one(
        {"_id": ObjectId(r["meta_id"])},
        {"$set": {
            "batch_id": batch_id,
            "source": source,
            "created_at": _now(),
            "storage": "gridfs" if "gridfs_id" in r else "inline",
            "message": message or "",
        }}
    )
    return ObjectId(r["meta_id"])

def agent_start_trigger(
    *,
    batch_id: str,
    sources: List[str],
    prompt_ref: Optional[ObjectId] = None,
    include_all_input: bool = True,
    max_refs_per_trigger: Optional[int] = None,
) -> ObjectId:
    c = get_client(); db = get_db(c)
    snapshot_ts = _now()

    refs: List[Dict[str, Any]] = []
    if include_all_input:
        q = {"created_at": {"$lte": snapshot_ts}}
        proj = {"_id": 1}
        cur = db[INPUT_EVIDENCE_COLL].find(q, proj).sort([("_id", 1)])
        if max_refs_per_trigger and max_refs_per_trigger > 0:
            cur = cur.limit(max_refs_per_trigger)
        refs = [{"collection": INPUT_EVIDENCE_COLL, "id": d["_id"]} for d in cur]

    doc = {
        "batch_id": batch_id,
        "sources": sources or [],
        "status": "collecting",
        "created_at": snapshot_ts,
        "timeframe": {"start": snapshot_ts},
        "evidence_refs": refs,
        "prompt_ref": prompt_ref,
        "schema_version": 1,
        "snapshot": {
            "inputs_cutoff": snapshot_ts,
            "inputs_count": len(refs),
        },
    }
    return db[TRIGGER_COLL].insert_one(doc).inserted_id

def agent_append_mcp_evidence(
    *,
    trigger_id: ObjectId | str,
    mcp_evidence_ids: List[ObjectId | str],
) -> bool:
    _tid = ObjectId(trigger_id) if not isinstance(trigger_id, ObjectId) else trigger_id
    ids = [ObjectId(x) if not isinstance(x, ObjectId) else x for x in (mcp_evidence_ids or [])]
    if not ids:
        return False

    c = get_client(); db = get_db(c)
    res = db[TRIGGER_COLL].update_one(
        {"_id": _tid, "status": {"$in": ["collecting", "ready"]}},
        {"$push": {"evidence_refs": {"$each": [
            {"collection": MCP_EVIDENCE_COLL, "id": _id} for _id in ids
        ]}}}
    )
    return res.modified_count == 1

def agent_finish_trigger_ready(
    *,
    trigger_id: ObjectId | str,
) -> bool:
    _tid = ObjectId(trigger_id) if not isinstance(trigger_id, ObjectId) else trigger_id
    c = get_client(); db = get_db(c)
    res = db[TRIGGER_COLL].update_one(
        {"_id": _tid, "status": "collecting"},
        {"$set": {"status": "ready", "timeframe.end": _now()}}
    )
    return res.modified_count == 1

def worker_lock_trigger_ready_to_processing(trigger_id: ObjectId | str) -> bool:
    _tid = ObjectId(trigger_id) if not isinstance(trigger_id, ObjectId) else trigger_id
    c = get_client(); db = get_db(c)
    res = db[TRIGGER_COLL].update_one(
        {"_id": _tid, "status": "ready"},
        {"$set": {"status": "processing", "started_at": _now()}}
    )
    return res.modified_count == 1

def _run_key(sources: List[str], evidence_refs: List[Dict[str, Any]]) -> str:
    h = hashlib.sha256()
    h.update(",".join(sorted(sources or [])).encode())
    for r in sorted(evidence_refs, key=lambda x: f"{x.get('collection')}:{x.get('id')}"):
        h.update(str(r.get("collection")).encode())
        h.update(str(r.get("id")).encode())
    return h.hexdigest()[:16]

def worker_save_report_and_mark_done(
    *,
    trigger_id: ObjectId | str,
    batch_id: str,
    sources: List[str],
    timeframe: Dict[str, Any],
    evidence_refs: List[Dict[str, Any]],
    report_text: str,
    model: str,
    prompt_ref: Optional[ObjectId] = None,
    refine_of: Optional[ObjectId] = None,
    confidence: Optional[Dict[str, Any]] = None,
) -> ObjectId:
    _tid = ObjectId(trigger_id) if not isinstance(trigger_id, ObjectId) else trigger_id
    c = get_client(); db = get_db(c)

    rk = _run_key(sources, evidence_refs)
    existing = db[REPORTS_COLL].find_one({"run_key": rk}, {"_id": 1})
    if existing:
        rid = existing["_id"]
    else:
        report = {
            "batch_id": batch_id,
            "created_at": _now(),
            "timeframe": timeframe or {},
            "sources": sources or [],
            "model": model,
            "evidence_refs": evidence_refs or [],
            "prompt_ref": prompt_ref,
            "refine_of": refine_of,
            "report_text": report_text or "",
            "run_key": rk,
            "confidence": confidence or {},
            "schema_version": 1,
        }
        rid = db[REPORTS_COLL].insert_one(report).inserted_id

    db[TRIGGER_COLL].update_one(
        {"_id": _tid, "status": "processing"},
        {"$set": {"status": "done", "finished_at": _now(), "report_id": rid}}
    )
    return rid