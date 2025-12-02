import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from bson import ObjectId

from app.db.mongo import get_db
from app.domains.ui.schema import UILayoutUpsertIn

UI_COLL = os.getenv("UI_COLL")

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _doc_to_layout(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "conversation_id": str(doc["conversation_id"]),
        "stage_id": int(doc["stage_id"]),
        "nodes": doc.get("nodes", []),
        "edges": doc.get("edges", []),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }

def get_layout(conversation_id: str, stage_id: int) -> Optional[Dict[str, Any]]:
    if not ObjectId.is_valid(conversation_id):
        raise ValueError("invalid conversation_id")

    cid = ObjectId(conversation_id)
    db = get_db()

    doc = db[UI_COLL].find_one({"conversation_id": cid, "stage_id": int(stage_id)})
    if not doc:
        return None
    return _doc_to_layout(doc)

def upsert_layout(conversation_id: str, stage_id: int, body: UILayoutUpsertIn) -> Dict[str, Any]:
    if not ObjectId.is_valid(conversation_id):
        raise ValueError("invalid conversation_id")

    cid = ObjectId(conversation_id)
    db = get_db()
    now = _now()

    update_doc = {
        "nodes": [n.model_dump() for n in body.nodes],
        "edges": [e.model_dump() for e in body.edges],
        "updated_at": now,
    }

    result = db[UI_COLL].find_one_and_update(
        {"conversation_id": cid, "stage_id": int(stage_id)},
        {
            "$set": update_doc,
            "$setOnInsert": {
                "conversation_id": cid,
                "stage_id": int(stage_id),
                "created_at": now,
            },
        },
        upsert=True,
        return_document=True,
    )

    if result is None:
        result = db[UI_COLL].find_one({"conversation_id": cid, "stage_id": int(stage_id)})

    return _doc_to_layout(result)