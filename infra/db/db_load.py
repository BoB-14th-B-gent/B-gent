from typing import Any, Dict, Iterable, List, Optional, Tuple, Set
from bson import ObjectId
from pymongo import MongoClient
from datetime import datetime, timezone
import gridfs, os, json
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")

INPUT_EVIDENCE_COLL = os.getenv("INPUT_EVIDENCE_COLL")
PROMPT_COLL = os.getenv("PROMPT_COLL")
MCP_EVIDENCE_COLL = os.getenv("MCP_EVIDENCE_COLL")
TRIGGER_COLL = os.getenv("TRIGGER_COLL")
REPORTS_COLL = os.getenv("REPORTS_COLL")

MAX_PREVIEW_BYTES      = 2 * 1024 * 1024
MAX_PROMPT_CHARS       = 120_000
MAX_EVIDENCES_PER_CALL = 100


def _now() -> datetime:
    return datetime.now(timezone.utc)

def get_client() -> MongoClient:
    return MongoClient(MONGO_URI, retryWrites=True)

def get_db(c: MongoClient):
    return c[DB_NAME]

def get_fs(db):
    return gridfs.GridFS(db)

def load_prompt(prompt_id: ObjectId | str) -> Optional[Dict[str, Any]]:
    _id = ObjectId(prompt_id) if not isinstance(prompt_id, ObjectId) else prompt_id
    c = get_client(); db = get_db(c)
    return db[PROMPT_COLL].find_one({"_id": _id})

def worker_load_trigger(trigger_id: ObjectId | str) -> Optional[Dict[str, Any]]:
    _tid = ObjectId(trigger_id) if not isinstance(trigger_id, ObjectId) else trigger_id
    c = get_client(); db = get_db(c)
    return db[TRIGGER_COLL].find_one({"_id": _tid})

def get_latest_done_trigger() -> Optional[Dict[str, Any]]:
    c = get_client(); db = get_db(c)
    return db[TRIGGER_COLL].find_one({"status":"done"}, sort=[("finished_at",-1)])

def agent_get_latest_report_by_batch(batch_id: str) -> Optional[Dict[str, Any]]:
    c = get_client(); db = get_db(c)
    return db[REPORTS_COLL].find_one({"batch_id": batch_id}, sort=[("created_at", -1)])

def agent_load_report_by_id(report_id: str | ObjectId) -> Optional[Dict[str, Any]]:
    _id = ObjectId(report_id) if not isinstance(report_id, ObjectId) else report_id
    c = get_client(); db = get_db(c)
    return db[REPORTS_COLL].find_one({"_id": _id})

def get_used_evidence_set(trigger_doc: Dict[str, Any]) -> Set[Tuple[str, ObjectId]]:
    used: Set[Tuple[str, ObjectId]] = set()
    for r in (trigger_doc.get("evidence_refs") or []):
        coll = r.get("collection"); _id = r.get("id")
        if not coll or not _id: 
            continue
        oid = ObjectId(_id) if not isinstance(_id, ObjectId) else _id
        used.add((coll, oid))
    return used

def _iter_refs(db, refs: List[Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
    by_coll: Dict[str, List[ObjectId]] = {}
    for r in refs or []:
        coll = r.get("collection"); _id = r.get("id")
        if not coll or not _id:
            continue
        oid = ObjectId(_id) if not isinstance(_id, ObjectId) else _id
        by_coll.setdefault(coll, []).append(oid)

    ids = by_coll.get(INPUT_EVIDENCE_COLL, [])
    if ids:
        for d in db[INPUT_EVIDENCE_COLL].find({"_id": {"$in": ids}}).sort("_id", 1):
            d["_collection"] = INPUT_EVIDENCE_COLL
            yield d

    ids = by_coll.get(MCP_EVIDENCE_COLL, [])
    if ids:
        for d in db[MCP_EVIDENCE_COLL].find({"_id": {"$in": ids}}).sort("created_at", 1):
            d["_collection"] = MCP_EVIDENCE_COLL
            yield d

def _prompt_block(db, trig: Dict[str, Any]) -> Optional[str]:
    pref = trig.get("prompt_ref")
    if not pref:
        return None
    pdoc = db[PROMPT_COLL].find_one({"_id": pref})
    if not pdoc:
        return None
    parts: List[str] = []
    parts.append(f"[PROMPT#{pdoc['_id']}]")
    if pdoc.get("user_prompt"):
        parts.append("user_prompt:\n" + str(pdoc["user_prompt"]))
    if pdoc.get("unprocessed_filenames"):
        parts.append("unprocessed_filenames: " + ", ".join(pdoc["unprocessed_filenames"]))
    if pdoc.get("inline_text_blobs"):
        for blob in pdoc["inline_text_blobs"]:
            label = blob.get("label","blob")
            text  = blob.get("text","")
            parts.append(f"{label}:\n{text[:4000]}")
    return "\n".join(parts)

def evidence_to_prompt_chunk(db, ev: Dict[str, Any]) -> str:
    fs = get_fs(db)
    parts: List[str] = []
    tag = ev.get("_collection", "EVIDENCE")
    parts.append(f"[{tag}#{ev['_id']}]")

    for k in ("created_at", "source", "filename"):
        if k in ev:
            parts.append(f"{k}: {ev[k]}")

    if ev.get("data") is not None:
        try:
            parts.append(json.dumps(ev["data"], ensure_ascii=False)[:4000])
        except Exception:
            parts.append("[json render error]")
    elif ev.get("raw") is not None:
        try:
            parts.append(bytes(ev["raw"]).decode("utf-8", errors="replace")[:4000])
        except Exception:
            parts.append("[raw bytes decode error]")

    gfid = ev.get("gridfs_id")
    if gfid:
        try:
            b = fs.get(gfid).read(MAX_PREVIEW_BYTES)
            ct = ev.get("content_type") or "application/octet-stream"
            if ct.startswith("text/") or ct.endswith("/json") or ct.endswith("+json"):
                parts.append(b.decode("utf-8", errors="replace")[:4000])
            else:
                parts.append(f"[binary preview {len(b)} bytes, content_type={ct}]")
        except Exception as e:
            parts.append(f"[gridfs read error: {e}]")

    return "\n".join(parts)

def build_prompt_chunks(db, trig: Dict[str, Any]) -> Iterable[Tuple[str, List[Dict[str, Any]]]]:
    header = _prompt_block(db, trig)
    header_added = False

    buf, batch, total = [], [], 0
    for ev in _iter_refs(db, trig.get("evidence_refs") or []):
        txt = evidence_to_prompt_chunk(db, ev)
        if not header_added and header:
            txt = header + "\n\n" + txt
            header_added = True

        if len(batch) >= MAX_EVIDENCES_PER_CALL or (total + len(txt) > MAX_PROMPT_CHARS):
            yield "\n\n---\n\n".join(buf), batch
            buf, batch, total = [], [], 0

        buf.append(txt); batch.append(ev); total += len(txt)

    if batch:
        yield "\n\n---\n\n".join(buf), batch