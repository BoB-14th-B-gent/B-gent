import os
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone
from bson import ObjectId
from app.db.mongo import get_db

TRIGGER_COLL = os.getenv("TRIGGER_COLL")

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _oid(s: str) -> ObjectId:
    if not ObjectId.is_valid(s):
        raise ValueError("invalid ObjectId")
    return ObjectId(s)

def collected_evidences(evidences: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[Tuple[str, str]] = set()
    out: List[Dict[str, Any]] = []
    for e in evidences or []:
        coll = e.get("collection")
        _id = e.get("id")
        if not coll or not _id:
            continue
        key = (coll, str(_id))
        if key in seen:
            continue
        seen.add(key)
        out.append({"collection": coll, "id": _id})
    return out

def create_trigger_with_conversation_id(conversation_id: str, stage_id: int) -> Dict[str, Any]:
    db = get_db()
    conv_oid = _oid(conversation_id)
    now = _now()
    doc = {
        "conversation_id": conv_oid,
        "stage_id": int(stage_id),
        "evidences": [],
        "prompt_id": None,
        "status": "initial",
        "report_id": None,
        "created_at": now,
        "updated_at": now
    }
    _id = db[TRIGGER_COLL].insert_one(doc).inserted_id
    return {"trigger_id": str(_id), "status": "initial", "created_at": now}

def get_trigger_with_trigger_id(trigger_id: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    tid = _oid(trigger_id)
    d = db[TRIGGER_COLL].find_one({"_id": tid})
    if not d:
        return None
    return {
        "_id": str(d["_id"]),
        "conversation_id": str(d["conversation_id"]),
        "stage_id": int(d.get("stage_id", 1)),
        "evidences": [
            {"collection": r["collection"], "id": str(r["id"])}
            for r in (d.get("evidences") or [])
        ],
        "prompt_id": str(d["prompt_id"]) if d.get("prompt_id") else None,
        "status": d.get("status", "initial"),
        "report_id": str(d["report_id"]) if d.get("report_id") else None,
        "created_at": d.get("created_at"),
        "updated_at": d.get("updated_at"),
    }

def get_triggers_by_conversation_id(
    conversation_id: str,
    *,
    stage_id: Optional[int] = None,
    status: Optional[str] = None,
    include_evidences: bool = False,
    limit: int = 100,
) -> Dict[str, Any]:
    if not ObjectId.is_valid(conversation_id):
        raise ValueError("invalid conversation_id")

    limit = max(1, min(int(limit), 200))

    query: Dict[str, Any] = {"conversation_id": ObjectId(conversation_id)}
    if stage_id is not None:
        query["stage_id"] = int(stage_id)
    if status is not None:
        query["status"] = status

    proj: Dict[str, int] = {
        "stage_id": 1,
        "status": 1,
        "prompt_id": 1,
        "report_id": 1,
        "created_at": 1,
        "updated_at": 1,
    }
    if include_evidences:
        proj["evidence_refs"] = 1
    db = get_db()
    cur = db[TRIGGER_COLL].find(query, projection=proj).sort([("stage_id"), ("created_at"), ("_id")]).limit(limit)

    items: List[Dict[str, Any]] = []
    for d in cur:
        item: Dict[str, Any] = {
            "id": str(d["_id"]),
            "conversation_id": conversation_id,
            "stage_id": int(d.get("stage_id")),
            "status": d.get("status"),
            "prompt_id": str(d["prompt_id"]) if d.get("prompt_id") else None,
            "report_id": str(d["report_id"]) if d.get("report_id") else None,
            "created_at": d.get("created_at"),
            "updated_at": d.get("updated_at"),
        }
        if include_evidences:
            evs = []
            for r in d.get("evidence_refs", []):
                evs.append({"collection": r.get("collection"), "id": str(r.get("id"))})
            item["evidences"] = evs
        else:
            item["evidences"] = []
        items.append(item)

    return {"conversation_id": conversation_id, "items": items}

def add_prompt_to_trigger(trigger_id: str, prompt_id: str) -> Dict[str, Any]:
    db = get_db()
    tid = _oid(trigger_id)
    pid = _oid(prompt_id)

    d = db[TRIGGER_COLL].find_one({"_id": tid})
    if not d:
        raise ValueError("trigger not found")
    if d.get("status") in ("processing", "done"):
        raise ValueError("cannot modify prompt when processing/done")

    db[TRIGGER_COLL].update_one(
        {"_id": tid},
        {
            "$set": {
                "prompt_id": pid,
                "status": "collecting" if d.get("status") == "initial" else d.get("status"),
                "updated_at": _now(),
            }
        },
    )
    return get_trigger_with_trigger_id(trigger_id)

def add_evidences_to_trigger(trigger_id: str, evidences: List[Dict[str, Any]]) -> Dict[str, Any]:
    db = get_db()
    tid = _oid(trigger_id)

    d = db[TRIGGER_COLL].find_one({"_id": tid})
    if not d:
        raise ValueError("trigger not found")
    if d.get("status") in ("processing", "done"):
        raise ValueError("cannot modify evidences when processing/done")

    new_evidences: List[Dict[str, Any]] = []
    for e in evidences or []:
        coll = e.get("collection")
        if coll not in ("input_evidences", "mcp_evidences"):
            raise ValueError("invalid evidence.collection")
        new_evidences.append({"collection": coll, "id": _oid(e.get("id"))})

    merged = collected_evidences((d.get("evidences") or []) + new_evidences)

    db[TRIGGER_COLL].update_one(
        {"_id": tid},
        {"$set": {"evidences": merged, "status": "collecting", "updated_at": _now()}},
    )
    return get_trigger_with_trigger_id(trigger_id)

def add_report_to_trigger(trigger_id: str, report_id: str) -> Dict[str, Any]:
    db = get_db()
    tid = _oid(trigger_id)
    rid = _oid(report_id)

    d = db[TRIGGER_COLL].find_one({"_id": tid})
    if not d:
        raise ValueError("trigger not found")

    db[TRIGGER_COLL].update_one(
        {"_id": tid},
        {"$set": {"report_id": rid, "status": "done", "updated_at": _now()}},
    )
    return get_trigger_with_trigger_id(trigger_id)