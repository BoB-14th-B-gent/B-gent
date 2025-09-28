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