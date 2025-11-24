import os
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from bson import ObjectId

from app.db.mongo import get_db
from app.domains.conversations.service import create_conversation_with_input, list_conversations_by_case

CASES_COLL = os.getenv("CASES_COLL")
CONV_COLL = os.getenv("CONVERSATIONS_COLL")

def _now() -> datetime:
    return datetime.now(timezone.utc)

def create_case(name: str, description: Optional[str], analyst: Optional[str]) -> Dict[str, Any]:
    db = get_db()
    now = _now()

    doc: Dict[str, Any] = {
        "name": name.strip(),
        "description": (description or "").strip() if description else None,
        "analyst": (analyst or "").strip() if analyst else None,
        "created_at": now,
        "updated_at": now,
    }

    case_id = db[CASES_COLL].insert_one(doc).inserted_id
    return {"_id": str(case_id), "created_at": now}

def get_case_detail(case_id: str) -> Optional[Dict[str, Any]]:
    if not ObjectId.is_valid(case_id):
        return None
    db = get_db()
    oid = ObjectId(case_id)

    d = db[CASES_COLL].find_one({"_id": oid})
    if not d:
        return None

    return {
        "_id": str(d["_id"]),
        "name": d.get("name", ""),
        "description": d.get("description"),
        "analyst": d.get("analyst"),
        "created_at": d.get("created_at"),
        "updated_at": d.get("updated_at"),
    }

def list_cases() -> List[Dict[str, Any]]:
    db = get_db()
    cursor = db[CASES_COLL].find().sort("created_at", 1)

    items: List[Dict[str, Any]] = []
    for d in cursor:
        items.append(
            {
                "_id": str(d["_id"]),
                "name": d.get("name", ""),
                "description": d.get("description"),
                "analyst": d.get("analyst"),
                "created_at": d.get("created_at"),
                "updated_at": d.get("updated_at"),
            }
        )
    return items

def create_case_conversation(case_id: str, input_text: str) -> Dict[str, Any]:
    if not ObjectId.is_valid(case_id):
        raise ValueError("invalid case_id")

    db = get_db()
    if not db[CASES_COLL].find_one({"_id": ObjectId(case_id)}):
        raise ValueError("case not found")

    return create_conversation_with_input(input_text, case_id=case_id)

def list_case_conversations(case_id: str) -> Dict[str, Any]:
    if not ObjectId.is_valid(case_id):
        raise ValueError("invalid case_id")

    items = list_conversations_by_case(case_id)
    return {"case_id": case_id, "items": items}

def get_case_conversation_detail(case_id: str, conversation_id: str) -> Optional[Dict[str, Any]]:
    if not (ObjectId.is_valid(case_id) and ObjectId.is_valid(conversation_id)):
        return None

    db = get_db()
    cid = ObjectId(case_id)
    oid = ObjectId(conversation_id)

    d = db[CONV_COLL].find_one({"_id": oid, "case_id": cid})
    if not d:
        return None

    return {
        "_id": str(d["_id"]),
        "title": d.get("title", ""),
        "last_stage_id": d.get("last_stage_id", 1),
        "created_at": d.get("created_at"),
        "updated_at": d.get("updated_at"),
    }