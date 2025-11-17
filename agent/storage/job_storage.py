"""MongoDB 스토리지 모듈

작업과 결과를 MongoDB에 저장하고 조회하는 기능 제공
"""
from __future__ import annotations

import json
from typing import Dict, Any, Optional, Callable
from datetime import datetime
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from ..config import get_config

_cfg = get_config()
_client: Optional[MongoClient] = None
_db = None

_state_update_callback: Optional[Callable[[Dict[str, Any]], None]] = None

def set_state_update_callback(callback: Optional[Callable[[Dict[str, Any]], None]]):
    """AGENT_STATES 업데이트 시 호출될 콜백 함수 설정

    Args:
        callback: 업데이트된 state_doc을 받는 함수
    """
    global _state_update_callback
    _state_update_callback = callback

def _print_state_json(state_doc: Dict[str, Any]):
    """MongoDB AGENT_STATES 변경사항을 JSON으로 출력

    sys.__stdout__을 사용하여 stdout 리다이렉트를 우회하고 원본 stdout에 직접 출력

    Args:
        state_doc: 출력할 state document
    """
    try:
        import sys
        output_doc = state_doc.copy()

        output_doc.pop('_id', None)

        if 'updated_at' in output_doc:
            output_doc['updated_at'] = output_doc['updated_at'].isoformat()
        if 'created_at' in output_doc:
            output_doc['created_at'] = output_doc['created_at'].isoformat()

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
            pass

        except ConnectionFailure as e:
            print(f"[X]  MongoDB 연결 실패 (작업은 계속됨): {e}")
            _client = None
            _db = None

    return _db

def save_agent_state(
    agent_id: str,
    stage_id: Optional[int] = None,
    plan: Optional[list] = None,
    status: str = "running",
    mcp_tools: Optional[list] = None,
    trigger_id: Optional[str] = None,
    conversation_id: Optional[str] = None
) -> bool:
    """에이전트 상태를 AGENT_STATES 컬렉션에 저장 (간결한 구조)

    Args:
        agent_id: 에이전트 ID (job_id와 동일) - PK
        stage_id: 현재 Task 번호 (0=초기화, 1=planning, 2~N=tasks)
        plan: 실행 계획 [{"task_id": str, "description": str, "mcp_server": str, "mcp_tools": [str], "status": str}, ...]
        status: 상태 (running | completed | failed)
        mcp_tools: (Deprecated - ignored) 하위 호환성 유지용 파라미터
        trigger_id: 트리거 ID (외부 시스템 연동용, optional)
        conversation_id: 대화 ID (채팅/세션 그룹핑, optional)

    Returns:
        bool: 저장 성공 여부

    Schema:
        {
            "agent_id": str (PK),
            "trigger_id": str | null,
            "conversation_id": str | null,
            "stage_id": int,
            "status": str,
            "plan": [{"task_id": str, "description": str, "mcp_server": str, "mcp_tools": [str], "status": str}],
            "created_at": datetime,
            "updated_at": datetime
        }

    Note: mcp_tools는 이제 plan 내부의 각 task에만 저장됩니다. 최상위 레벨의 mcp_tools 필드는 제거되었습니다.
    """
    try:
        db = _get_client()
        if db is None:
            return False

        # 기존 문서를 조회하여 trigger_id와 conversation_id 보존
        existing_doc = db.AGENT_STATES.find_one({"agent_id": agent_id})

        # trigger_id와 conversation_id가 None이면 기존 값 유지
        if trigger_id is None and existing_doc:
            trigger_id = existing_doc.get("trigger_id")
        if conversation_id is None and existing_doc:
            conversation_id = existing_doc.get("conversation_id")

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
            except Exception as cb_err:
                pass

        return True

    except Exception as e:
        print(f"[X]  AGENT_STATES 저장 실패: {e}")
        return False


def update_agent_status(agent_id: str, status: str) -> bool:
    """에이전트 상태만 업데이트

    Args:
        agent_id: 에이전트 ID
        status: 새로운 상태

    Returns:
        bool: 업데이트 성공 여부
    """
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
    """사용된 MCP 도구를 해당 task에 추가

    Args:
        agent_id: 에이전트 ID
        mcp_name: MCP 서버 이름
        tool_name: 도구 이름
        task_id: Task ID (필수는 아니지만, 없으면 기록되지 않음)

    Returns:
        bool: 추가 성공 여부
    """
    try:
        db = _get_client()
        if db is None:
            return False

        if not task_id:
            # task_id가 없으면 기록하지 않음 (경고만 출력)
            # print(f"[!] Warning: add_mcp_tool called without task_id for {mcp_name}.{tool_name}")
            return True

        tool_identifier = f"{tool_name}"

        # task별 mcp_tools 업데이트
        # plan 배열에서 해당 task_id를 찾아 mcp_tools와 mcp_server 업데이트
        state = db.AGENT_STATES.find_one({"agent_id": agent_id})
        if not state:
            return False

        plan = state.get("plan", [])
        updated = False

        for task in plan:
            if task.get("task_id") == task_id:
                # mcp_server 설정 (아직 없으면)
                if "mcp_server" not in task or not task["mcp_server"]:
                    task["mcp_server"] = mcp_name

                # mcp_tools 배열에 추가 (중복 제거)
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
                    "$unset": {"mcp_tools": ""}  # 기존 전역 mcp_tools 필드 제거
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
    """현재 스테이지 업데이트

    Args:
        agent_id: 에이전트 ID
        stage_id: 스테이지 ID

    Returns:
        bool: 업데이트 성공 여부
    """
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
    """plan 배열 내 특정 task의 상태 업데이트

    Args:
        agent_id: 에이전트 ID
        task_id: 업데이트할 task의 ID
        task_status: 새로운 task 상태 (pending | in_progress | done | failed)

    Returns:
        bool: 업데이트 성공 여부
    """
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
    """에이전트 상태 조회

    Args:
        agent_id: 에이전트 ID

    Returns:
        Optional[Dict[str, Any]]: 에이전트 상태 (없으면 None)
    """
    try:
        db = _get_client()
        if db is None:
            return None

        return db.AGENT_STATES.find_one({"agent_id": agent_id})

    except Exception as e:
        print(f"[X]  상태 조회 실패: {e}")
        return None

