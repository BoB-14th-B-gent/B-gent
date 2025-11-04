"""MongoDB 스토리지 모듈

작업과 결과를 MongoDB에 저장하고 조회하는 기능 제공
"""
from __future__ import annotations
from typing import Dict, Any, Optional
from datetime import datetime
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from ..config import get_config
_cfg = get_config()
_client: Optional[MongoClient] = None
_db = None

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
    conversation_id: Optional[str] = None,
    additional_data: Optional[Dict[str, Any]] = None
) -> bool:
    """에이전트 상태를 AGENT_STATES 컬렉션에 저장

    Args:
        agent_id: 에이전트 ID (job_id와 동일)
        stage_id: 현재 스테이지 ID
        plan: 실행 계획 (high_level_tasks)
        status: 상태 (running, completed, failed 등)
        mcp_tools: 사용된 MCP 도구 목록
        trigger_id: 트리거 ID (선택사항, 추후 구현)
        conversation_id: 대화 ID (선택사항, 추후 구현)
        additional_data: 추가 데이터 (선택사항)

    Returns:
        bool: 저장 성공 여부
    """
    try:
        db = _get_client()
        if db is None:
            return False

        state_doc = {
            "agent_id": agent_id,
            "trigger_id": trigger_id,
            "conversation_id": conversation_id,
            "stage_id": stage_id,
            "plan": plan or [],
            "status": status,
            "mcp_tools": mcp_tools or [],
            "updated_at": datetime.utcnow()
        }

        if additional_data:
            state_doc.update(additional_data)

        db.AGENT_STATES.update_one(
            {"agent_id": agent_id},
            {
                "$set": state_doc,
                "$setOnInsert": {"created_at": datetime.utcnow()}
            },
            upsert=True
        )

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

        db.AGENT_STATES.update_one(
            {"agent_id": agent_id},
            {
                "$set": {
                    "status": status,
                    "updated_at": datetime.utcnow()
                }
            }
        )

        return True

    except Exception as e:
        print(f"[X]  상태 업데이트 실패: {e}")
        return False


def add_mcp_tool(agent_id: str, mcp_name: str, tool_name: str) -> bool:
    """사용된 MCP 도구를 추가 (중복 제거)

    Args:
        agent_id: 에이전트 ID
        mcp_name: MCP 서버 이름
        tool_name: 도구 이름

    Returns:
        bool: 추가 성공 여부
    """
    try:
        db = _get_client()
        if db is None:
            return False

        tool_identifier = f"{mcp_name}.{tool_name}"

        db.AGENT_STATES.update_one(
            {"agent_id": agent_id},
            {
                "$addToSet": {"mcp_tools": tool_identifier},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )

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

        return True

    except Exception as e:
        print(f"[X]  스테이지 업데이트 실패: {e}")
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

