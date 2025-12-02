"""MongoDB 스토리지 모듈

작업과 결과를 MongoDB에 저장하고 조회하는 기능 제공
"""
from __future__ import annotations

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
    """AGENT_STATES 업데이트 시 호출될 콜백 함수 설정"""
    global _state_update_callback
    _state_update_callback = callback


def _convert_for_json(obj: Any) -> Any:
    """ObjectId / datetime 등을 JSON 직렬화 가능하게 변환 (재귀)"""
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
    """MongoDB AGENT_STATES 변경사항을 JSON으로 출력

    sys.__stdout__을 사용하여 stdout 리다이렉트를 우회하고 원본 stdout에 직접 출력
    """
    try:
        import sys
        output_doc = state_doc.copy()
        output_doc.pop('_id', None)

        # ObjectId / datetime 등 변환
        output_doc = _convert_for_json(output_doc)

        json_str = json.dumps(output_doc, ensure_ascii=False)
        sys.__stdout__.write(json_str + '\n')
        sys.__stdout__.flush()
    except Exception:
        pass


def _get_client():
    """MongoDB 클라이언트 가져오기 (지연 초기화)"""
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
    """문자열이면 ObjectId로 변환 가능하면 변환, 아니면 원본 유지"""
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
    mcp_tools: Optional[list] = None,  # deprecated
    trigger_id: Optional[str] = None,
    conversation_id: Optional[str] = None
) -> bool:
    """에이전트 상태를 AGENT_STATES 컬렉션에 저장 (간결한 구조)

    trigger_id / conversation_id 는 가능하면 ObjectId로 저장
    """
    try:
        db = _get_client()
        if db is None:
            return False

        # 기존 문서 조회
        existing_doc = db.AGENT_STATES.find_one({"agent_id": agent_id})

        # 새 값이 None이면 기존 값 유지
        if trigger_id is None and existing_doc:
            trigger_id = existing_doc.get("trigger_id")
        if conversation_id is None and existing_doc:
            conversation_id = existing_doc.get("conversation_id")

        # 문자열이면 ObjectId로 변환 (가능한 경우)
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
    """에이전트 상태만 업데이트"""
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
    """사용된 MCP 도구를 해당 task에 추가"""
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
    """현재 스테이지 업데이트"""
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
    """plan 배열 내 특정 task의 상태 업데이트"""
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
    """에이전트 상태 조회"""
    try:
        db = _get_client()
        if db is None:
            return None

        return db.AGENT_STATES.find_one({"agent_id": agent_id})

    except Exception as e:
        print(f"[X]  상태 조회 실패: {e}")
        return None


def is_first_execution_in_conversation(conversation_id: Optional[str]) -> bool:
    """해당 conversation에서 첫 번째 실행인지 확인

    conversation_id가 동일한 기존 AGENT_STATES가 있는지 조회하여
    첫 실행 여부를 판단합니다.

    Args:
        conversation_id: 대화 ID

    Returns:
        bool: 첫 실행이면 True, 아니면 False
    """
    if not conversation_id:
        return True  # conversation_id가 없으면 첫 실행으로 간주

    try:
        db = _get_client()
        if db is None:
            return True  # DB 연결 실패 시 첫 실행으로 간주

        # conversation_id를 ObjectId로 변환 (가능한 경우)
        conv_id = _to_oid_or_keep(conversation_id)

        existing = db.AGENT_STATES.find_one({"conversation_id": conv_id})
        return existing is None

    except Exception as e:
        print(f"[X]  첫 실행 여부 확인 실패: {e}")
        return True  # 오류 시 첫 실행으로 간주