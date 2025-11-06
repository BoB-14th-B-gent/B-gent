import os
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from bson import ObjectId
from app.db.mongo import get_db

REPORTS_COLL = os.getenv("REPORTS_COLL", "REPORTS")

def _fmt_date(v: Any) -> Optional[str]:
    if isinstance(v, datetime):
        return v.isoformat()
    return None

def _to_str_oid(v: Any) -> Optional[str]:
    if isinstance(v, ObjectId):
        return str(v)
    if isinstance(v, dict) and "$oid" in v:
        try:
            return str(ObjectId(v["$oid"]))
        except Exception:
            return None
    if isinstance(v, str) and ObjectId.is_valid(v):
        return v
    return None

def get_report_detail(report_id: str) -> Optional[Dict[str, Any]]:
    if not ObjectId.is_valid(report_id):
        return None

    db = get_db()
    doc = db[REPORTS_COLL].find_one({"_id": ObjectId(report_id)})
    if not doc:
        return None

    return {
        "_id": str(doc["_id"]),
        "report": doc.get("report", ""),
        "conversation_id": _to_str_oid(doc.get("conversation_id")),
        "stage_id": doc.get("stage_id"),
        "trigger_id": _to_str_oid(doc.get("trigger_id")),
        "created_at": _fmt_date(doc.get("created_at")),
    }

def list_reports(
    conversation_id: Optional[str] = None,
    stage_id: Optional[int] = None,
    limit: int = 50
) -> Dict[str, Any]:
    query: Dict[str, Any] = {}

    if conversation_id is not None:
        if not ObjectId.is_valid(conversation_id):
            raise ValueError("invalid conversation_id")
        query["conversation_id"] = ObjectId(conversation_id)

    if stage_id is not None:
        try:
            query["stage_id"] = int(stage_id)
        except Exception:
            raise ValueError("stage_id must be int")

    db = get_db()
    cursor = db[REPORTS_COLL].find(query).sort("created_at", -1).limit(int(limit))

    items = []
    for doc in cursor:
        items.append({
            "_id": str(doc["_id"]),
            "report": doc.get("report", ""),
            "conversation_id": _to_str_oid(doc.get("conversation_id")),
            "stage_id": doc.get("stage_id"),
            "trigger_id": _to_str_oid(doc.get("trigger_id")),
            "created_at": _fmt_date(doc.get("created_at")),
        })

    return {
        "total": len(items),
        "items": items,
    }