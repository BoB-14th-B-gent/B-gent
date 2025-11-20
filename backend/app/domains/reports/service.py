import os
from typing import Any, Dict, Optional, List
from datetime import datetime
from bson import ObjectId
from app.db.mongo import get_db

from app.domains.reports.parser import parse_incident_report

REPORTS_COLL = os.getenv("REPORTS_COLL")

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

def _to_objid_str(s: Optional[str]) -> Optional[ObjectId]:
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    if not ObjectId.is_valid(s):
        raise ValueError("invalid conversation_id")
    return ObjectId(s)

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
        "structured": doc.get("structured"),
    }

def get_latest_report_detail() -> Optional[Dict[str, Any]]:
    db = get_db()
    doc = db[REPORTS_COLL].find_one({}, sort=[("created_at", -1), ("_id", -1)])
    if not doc:
        return None

    return {
        "_id": str(doc["_id"]),
        "report": doc.get("report", ""),
        "conversation_id": _to_str_oid(doc.get("conversation_id")),
        "stage_id": doc.get("stage_id"),
        "trigger_id": _to_str_oid(doc.get("trigger_id")),
        "created_at": _fmt_date(doc.get("created_at")),
        "structured": doc.get("structured"),
    }

def parse_and_save_structured(report_id: str, text_override: Optional[str] = None) -> Dict[str, Any]:
    if not ObjectId.is_valid(report_id):
        raise ValueError("invalid report_id")

    db = get_db()
    doc = db[REPORTS_COLL].find_one({"_id": ObjectId(report_id)})
    if not doc:
        raise ValueError("report not found")

    report_text: str = (text_override if text_override is not None else doc.get("report", "")) or ""

    parsed = parse_incident_report(report_text)
    structured = {"header": parsed.header, "sections": parsed.sections}

    db[REPORTS_COLL].update_one(
        {"_id": ObjectId(report_id)},
        {"$set": {"structured": structured}},
        upsert=False,
    )
    return {"report_id": report_id, "structured": structured}

def list_reports_by_conversation_stage(conversation_id: Optional[str] = None, stage_id: Optional[int] = None) -> Dict[str, Any]:
    db = get_db()
    query: Dict[str, Any] = {}

    if conversation_id is not None:
        oid = _to_objid_str(conversation_id)
        query["conversation_id"] = oid

    if stage_id is not None:
        query["stage_id"] = stage_id

    cursor = db[REPORTS_COLL].find(query).sort(
        [
            ("stage_id", 1),
            ("created_at", 1),
            ("_id", 1),
        ]
    )

    items: List[Dict[str, Any]] = []
    for doc in cursor:
        items.append(
            {
                "_id": str(doc["_id"]),
                "report": doc.get("report", ""),
                "conversation_id": _to_str_oid(doc.get("conversation_id")),
                "stage_id": doc.get("stage_id"),
                "trigger_id": _to_str_oid(doc.get("trigger_id")),
                "created_at": _fmt_date(doc.get("created_at")) or "",
                "structured": doc.get("structured"),
            }
        )

    return {
        "total": len(items),
        "items": items,
    }