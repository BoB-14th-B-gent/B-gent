import os, re
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from bson import ObjectId
from app.db.mongo import get_db
from app.domains.messages.service import create_message

CONV_COLL = os.getenv("CONVERSATIONS_COLL")
TRIGGERS_COLL = os.getenv("TRIGGER_COLL")
REPORTS_COLL = os.getenv("REPORTS_COLL")

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

def create_conversation_with_input(input_text: str, case_id: Optional[str] = None) -> Dict[str, Any]:
    db = get_db()
    now = _now()
    title = _title_from_input(input_text)

    conv_doc = {
        "title": title,
        "last_stage_id": 1,
        "created_at": now,
        "updated_at": now,
    }

    if case_id:
        if not ObjectId.is_valid(case_id):
            raise ValueError("invalid case_id")
        conv_doc["case_id"] = ObjectId(case_id)

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

def list_conversations() -> List[Dict[str, Any]]:
    db = get_db()
    cursor = db[CONV_COLL].find().sort("created_at", 1)

    items: List[Dict[str, Any]] = []
    for d in cursor:
        items.append(
            {
                "_id": str(d["_id"]),
                "title": d.get("title", ""),
                "last_stage_id": d.get("last_stage_id", 1),
                "created_at": d.get("created_at"),
                "updated_at": d.get("updated_at"),
            }
        )
    return items

def list_conversations_by_case(case_id: str) -> List[Dict[str, Any]]:
    if not ObjectId.is_valid(case_id):
        raise ValueError("invalid case_id")

    db = get_db()
    cid = ObjectId(case_id)

    cursor = db[CONV_COLL].find({"case_id": cid}).sort("created_at", 1)

    items: List[Dict[str, Any]] = []
    for d in cursor:
        items.append(
            {
                "_id": str(d["_id"]),
                "title": d.get("title", ""),
                "last_stage_id": d.get("last_stage_id", 1),
                "created_at": d.get("created_at"),
                "updated_at": d.get("updated_at"),
            }
        )
    return items

def get_conversation_reports(conversation_id: str) -> Optional[Dict[str, Any]]:
    if not ObjectId.is_valid(conversation_id):
        raise ValueError("invalid conversation_id")

    db = get_db()
    cid = ObjectId(conversation_id)

    triggers = list(
        db[TRIGGERS_COLL].find({"conversation_id": cid}).sort([("stage_id", 1), ("created_at", 1)])
    )
    if not triggers:
        return None

    trigger_ids = [t["_id"] for t in triggers]

    reports = list(
        db[REPORTS_COLL]
        .find({"trigger_id": {"$in": trigger_ids}})
        .sort([("created_at", 1)])
    )
    if not reports:
        return None

    trig_meta = {t["_id"]: {"stage_id": int(t.get("stage_id", 1))} for t in triggers}

    items: List[Dict[str, Any]] = []
    for r in reports:
        tid = r.get("trigger_id")
        stage_id = trig_meta.get(tid, {}).get("stage_id", 1)
        items.append(
            {
                "_id": str(r["_id"]),
                "stage_id": stage_id,
                "report": r.get("report", ""),
                "created_at": r.get("created_at"),
            }
        )

    items.sort(key=lambda x: (x["stage_id"], x["created_at"]))

    return {"conversation_id": conversation_id, "items": items}

def update_last_stage(conversation_id: str, stage_id: int) -> Optional[Dict[str, Any]]:
    if not ObjectId.is_valid(conversation_id):
        raise ValueError("invalid conversation_id")

    db = get_db()
    oid = ObjectId(conversation_id)

    res = db[CONV_COLL].find_one_and_update(
        {"_id": oid},
        {
            "$set": {
                "last_stage_id": stage_id,
                "updated_at": _now(),
            }
        },
        return_document=True,
    )

    if not res:
        return None

    return {
        "_id": str(res["_id"]),
        "title": res.get("title", ""),
        "last_stage_id": res.get("last_stage_id"),
        "created_at": res.get("created_at"),
        "updated_at": res.get("updated_at"),
    }