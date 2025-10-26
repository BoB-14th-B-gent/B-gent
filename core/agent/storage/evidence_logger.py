"""MCP 실행 로깅 모듈

MCP 도구 호출 결과를 MongoDB MCP_EVIDENCES 컬렉션에 저장
"""
from __future__ import annotations
from typing import Dict, Any, Optional
from datetime import datetime
from .job_storage import _get_client


def log_mcp_execution(
    mcp_name: str,
    tool_name: str,
    request: Dict[str, Any],
    response: Any,
    success: bool,
    stage: Optional[int] = None
) -> bool:
    """MCP 도구 실행 결과를 MongoDB에 저장

    Args:
        mcp_name: MCP 서버 이름 (elastic, velociraptor, sleuthkit, ghidra)
        tool_name: 사용된 도구 이름
        request: 도구에 전달된 파라미터
        response: 도구 실행 결과 데이터
        success: 실행 성공 여부
        stage: 스테이지 번호 (선택사항)

    Returns:
        bool: 저장 성공 여부
    """
    try:
        db = _get_client()
        if db is None:
            return False

        evidence = {
            "stage": stage,
            "mcp_name": mcp_name,
            "tool_name": tool_name,
            "request": request,
            "response": response,
            "success": success,
            "timestamp": datetime.utcnow()
        }

        db.MCP_EVIDENCES.insert_one(evidence)

        return True

    except Exception as e:
        print(f"[X]  MCP 실행 로그 저장 실패: {e}")
        return False
