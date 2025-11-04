import os, re
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from bson import ObjectId
from app.db.mongo import get_db
from app.domains.messages.service import create_message

CONV_COLL = os.getenv("CONVERSATIONS_COLL")

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _title_from_input(s: str, limit: int = 30) -> str:
    first = ""
    for line in (s or "").splitlines():
        ln = line.strip()
        if ln:
            first = ln
            break
    if not first:
        first = (s or "").strip()[:limit] or "Untitled"
    first = re.sub(r"\s+", " ", first).strip()
    if len(first) > limit:
        first = first[:limit - 1] + "…"
    return first or "Untitled"

def create_conversation_with_input(input_text: str) -> Dict[str, Any]:
    db = get_db()
    now = _now()
    title = _title_from_input(input_text)

    conv_doc = {
        "title": title,
        "last_stage_id": 1,
        "created_at": now,
        "updated_at": now,
    }
    conv_id = db[CONV_COLL].insert_one(conv_doc).inserted_id

    create_message(
        str(conv_id),
        {
            "role": "USER",
            "stage_id": 1,
            "content": input_text,
        },
    )

    return {"_id": str(conv_id), "title": title, "created_at": now}

def get_conversation_detail(conversation_id: str) -> Optional[Dict[str, Any]]:
    db = get_db()

    if not ObjectId.is_valid(conversation_id):
        return None
    oid = ObjectId(conversation_id)

    d = db[CONV_COLL].find_one({"_id": oid})
    if not d:
        return None
    
    return {
        "_id": str(d["_id"]),
        "title": d.get("title", ""),
        "last_stage_id": d.get("last_stage_id"),
        "created_at": d.get("created_at"),
        "updated_at": d.get("updated_at"),
    }