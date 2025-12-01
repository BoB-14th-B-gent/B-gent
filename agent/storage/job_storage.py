import json
from typing import Dict, Any, Optional, Callable
from datetime import datetime
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from bson import ObjectId

from ..config import get_config

_cfg = get_config()
_client: Optional[MongoClient] = None
_db = None

_state_update_callback: Optional[Callable[[Dict[str, Any]], None]] = None


def set_state_update_callback(callback: Optional[Callable[[Dict[str, Any]], None]]):
    global _state_update_callback
    _state_update_callback = callback

def _convert_for_json(obj: Any) -> Any:
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _convert_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_for_json(v) for v in obj]
    return obj

def _print_state_json(state_doc: Dict[str, Any]):
    try:
        import sys
        output_doc = state_doc.copy()
        output_doc.pop('_id', None)

        output_doc = _convert_for_json(output_doc)

        json_str = json.dumps(output_doc, ensure_ascii=False)
        sys.__stdout__.write(json_str + '\n')
        sys.__stdout__.flush()
    except Exception:
        pass

def _get_client():
    global _client, _db

    if _client is None:
        try:
            _client = MongoClient(
                _cfg.mongo.uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000
            )
            _client.admin.command('ping')
            _db = _client[_cfg.mongo.db]
        except ConnectionFailure as e:
            print(f"[X]  MongoDB 연결 실패 (작업은 계속됨): {e}")
            _client = None
            _db = None

    return _db

def _to_oid_or_keep(val: Optional[str | ObjectId]) -> Optional[ObjectId | str]:
    if val is None:
        return None
    if isinstance(val, ObjectId):
        return val
    if isinstance(val, str) and ObjectId.is_valid(val):
        return ObjectId(val)
    return val

def save_agent_state(
    agent_id: str,
    stage_id: Optional[int] = None,
    plan: Optional[list] = None,
    status: str = "running",
    mcp_tools: Optional[list] = None,
    trigger_id: Optional[str] = None,
    conversation_id: Optional[str] = None
) -> bool:
    try:
        db = _get_client()
        if db is None:
            return False

        existing_doc = db.AGENT_STATES.find_one({"agent_id": agent_id})

        if trigger_id is None and existing_doc:
            trigger_id = existing_doc.get("trigger_id")
        if conversation_id is None and existing_doc:
            conversation_id = existing_doc.get("conversation_id")

        trigger_id = _to_oid_or_keep(trigger_id)
        conversation_id = _to_oid_or_keep(conversation_id)

        state_doc = {
            "agent_id": agent_id,
            "trigger_id": trigger_id,
            "conversation_id": conversation_id,
            "stage_id": stage_id if stage_id is not None else 0,
            "status": status,
            "plan": plan or [],
            "updated_at": datetime.utcnow()
        }

        db.AGENT_STATES.update_one(
            {"agent_id": agent_id},
            {
                "$set": state_doc,
                "$setOnInsert": {"created_at": datetime.utcnow()}
            },
            upsert=True
        )

        _print_state_json(state_doc)

        if _state_update_callback:
            try:
                _state_update_callback(state_doc)
            except Exception:
                pass

        return True

    except Exception as e:
        print(f"[X]  AGENT_STATES 저장 실패: {e}")
        return False

def update_agent_status(agent_id: str, status: str) -> bool:
    try:
        db = _get_client()
        if db is None:
            return False

        update_doc = {
            "status": status,
            "updated_at": datetime.utcnow()
        }

        db.AGENT_STATES.update_one(
            {"agent_id": agent_id},
            {"$set": update_doc}
        )

        full_state = db.AGENT_STATES.find_one({"agent_id": agent_id})
        if full_state:
            _print_state_json(full_state)

        if _state_update_callback:
            try:
                if full_state:
                    _state_update_callback(full_state)
            except Exception:
                pass

        return True

    except Exception as e:
        print(f"[X]  상태 업데이트 실패: {e}")
        return False

def add_mcp_tool(agent_id: str, mcp_name: str, tool_name: str, task_id: Optional[str] = None) -> bool:
    try:
        db = _get_client()
        if db is None:
            return False

        if not task_id:
            return True

        tool_identifier = f"{tool_name}"

        state = db.AGENT_STATES.find_one({"agent_id": agent_id})
        if not state:
            return False

        plan = state.get("plan", [])
        updated = False

        for task in plan:
            if task.get("task_id") == task_id:
                if "mcp_server" not in task or not task["mcp_server"]:
                    task["mcp_server"] = mcp_name

                if "mcp_tools" not in task:
                    task["mcp_tools"] = []
                if tool_identifier not in task["mcp_tools"]:
                    task["mcp_tools"].append(tool_identifier)

                updated = True
                break

        if updated:
            db.AGENT_STATES.update_one(
                {"agent_id": agent_id},
                {
                    "$set": {
                        "plan": plan,
                        "updated_at": datetime.utcnow()
                    },
                    "$unset": {"mcp_tools": ""}
                }
            )

        full_state = db.AGENT_STATES.find_one({"agent_id": agent_id})
        if full_state:
            _print_state_json(full_state)

        if _state_update_callback:
            try:
                if full_state:
                    _state_update_callback(full_state)
            except Exception:
                pass

        return True

    except Exception as e:
        print(f"[X]  MCP 도구 추가 실패: {e}")
        return False

def update_stage(agent_id: str, stage_id: int) -> bool:
    try:
        db = _get_client()
        if db is None:
            return False

        db.AGENT_STATES.update_one(
            {"agent_id": agent_id},
            {
                "$set": {
                    "stage_id": stage_id,
                    "updated_at": datetime.utcnow()
                }
            }
        )

        full_state = db.AGENT_STATES.find_one({"agent_id": agent_id})
        if full_state:
            _print_state_json(full_state)

        if _state_update_callback:
            try:
                if full_state:
                    _state_update_callback(full_state)
            except Exception:
                pass

        return True

    except Exception as e:
        print(f"[X]  스테이지 업데이트 실패: {e}")
        return False

def update_task_status(agent_id: str, task_id: str, task_status: str) -> bool:
    try:
        db = _get_client()
        if db is None:
            return False

        db.AGENT_STATES.update_one(
            {"agent_id": agent_id, "plan.task_id": task_id},
            {
                "$set": {
                    "plan.$.status": task_status,
                    "updated_at": datetime.utcnow()
                }
            }
        )

        full_state = db.AGENT_STATES.find_one({"agent_id": agent_id})
        if full_state:
            _print_state_json(full_state)

        if _state_update_callback:
            try:
                if full_state:
                    _state_update_callback(full_state)
            except Exception:
                pass

        return True

    except Exception as e:
        print(f"[X]  Task 상태 업데이트 실패: {e}")
        return False

def get_agent_state(agent_id: str) -> Optional[Dict[str, Any]]:
    try:
        db = _get_client()
        if db is None:
            return None

        return db.AGENT_STATES.find_one({"agent_id": agent_id})

    except Exception as e:
        print(f"[X]  상태 조회 실패: {e}")
        return None

def is_first_execution_in_conversation(conversation_id: Optional[str]) -> bool:
    if not conversation_id:
        return True

    try:
        db = _get_client()
        if db is None:
            return True

        conv_id = _to_oid_or_keep(conversation_id)

        existing = db.AGENT_STATES.find_one({"conversation_id": conv_id})
        return existing is None

    except Exception as e:
        print(f"[X]  첫 실행 여부 확인 실패: {e}")
        return True