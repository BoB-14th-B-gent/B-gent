import os
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from bson import ObjectId
from app.db.mongo import get_db

MSG_COLL = os.getenv("MESSAGES_COLL")

def _now() -> datetime:
    return datetime.now(timezone.utc)

def create_message(conversation_id: str, payload: Dict[str, Any]) -> str:
    if not ObjectId.is_valid(conversation_id):
        raise ValueError("invalid conversation_id")

    role = payload.get("role")
    if role not in ("USER", "B-GENT"):
        raise ValueError("role must be 'USER' or 'B-GENT'")

    stage_id = int(payload.get("stage_id", 1))
    if stage_id < 1:
        stage_id = 1

    content = str(payload.get("content") or "")

    db = get_db()
    doc = {
        "conversation_id": ObjectId(conversation_id),
        "role": role,
        "stage_id": stage_id,
        "content": content,
        "created_at": _now(),
    }
    result = db[MSG_COLL].insert_one(doc)
    return str(result.inserted_id)

def list_messages(conversation_id: str, stage_id: Optional[int] = None, limit: int = 100) -> Dict[str, Any]:
    if not ObjectId.is_valid(conversation_id):
        raise ValueError("invalid conversation_id")

    query: Dict[str, Any] = {"conversation_id": ObjectId(conversation_id)}
    if stage_id is not None:
        query["stage_id"] = int(stage_id)

    db = get_db()
    cursor = db[MSG_COLL].find(query).sort("created_at").limit(limit)

    return {
        "conversation_id": conversation_id,
        "items": [
            {
                "_id": str(doc["_id"]),
                "role": doc["role"],
                "stage_id": doc["stage_id"],
                "content": doc["content"],
                "created_at": doc["created_at"],
            }
            for doc in cursor
        ],
    }

def get_message_detail(conversation_id: str, message_id: str) -> Optional[Dict[str, Any]]:
    if not (ObjectId.is_valid(conversation_id) and ObjectId.is_valid(message_id)):
        return None

    db = get_db()
    doc = db[MSG_COLL].find_one(
        {"_id": ObjectId(message_id), "conversation_id": ObjectId(conversation_id)}
    )
    if not doc:
        return None

    return {
        "conversation_id": conversation_id,
        "role": doc["role"],
        "content": doc["content"],
    }