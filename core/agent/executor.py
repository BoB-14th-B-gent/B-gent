"""액션 실행기 모듈

MCP 도구 호출, 타임아웃 및 재시도 관리 담당
"""
from __future__ import annotations
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Dict, Any
from .schemas.actions import Action, ActionResult
from .mcp_singleton import get_mcp_client

def execute_action(action: Action) -> ActionResult:
    """액션 실행 (재시도 및 타임아웃 지원)

    MCP 도구 호출 및 액션 실행, 실패 시 자동 재시도
    재시도 가능한 에러인 경우 지수 백오프(exponential backoff) 적용

    로직:
        1. 최대 retry_count + 1회 반복
        2. 각 시도마다:
           a. MCP 도구 호출 (타임아웃 적용)
           b. 성공 시 ActionResult 반환
           c. 실패 시 재시도 가능 여부 판단
           d. 재시도 가능하면 지수 백오프 후 재시도
           e. 재시도 불가능하면 즉시 실패 반환
        3. 모든 재시도 실패 시 최종 실패 반환

    Args:
        action: 실행할 액션 (도구 이름, 파라미터 등 포함)

    Returns:
        ActionResult: 실행 결과 (성공/실패, 결과 데이터, 실행 시간 등)

    Example:
        >>> action = Action(
        ...     tool="elastic",
        ...     operation="search_documents",
        ...     params={"index": "logs-*", "body": {...}},
        ...     reason="SIEM 로그 검색",
        ...     retry_count=2,
        ...     timeout_seconds=60
        ... )
        >>> result = execute_action(action)
        >>> if result.success:
        ...     print(f"결과: {result.result}")
        ... else:
        ...     print(f"에러: {result.error}")
    """
    max_retries = action.retry_count
    timeout = action.timeout_seconds
    last_error = None

    for attempt in range(max_retries + 1):
        start_time = time.time()

        try:

            if attempt > 0:
                print(f"🔄 재시도 {attempt}/{max_retries}: {action.tool}.{action.operation}")
                sleep_time = min(2 ** (attempt - 1), 10)
                time.sleep(sleep_time)

            else:
                print(f"🔧 실행 중: {action.tool}.{action.operation}")
                print(f"   이유: {action.reason}")
            result = _call_mcp_tool_with_timeout(action, timeout)
            execution_time = time.time() - start_time

            if result.get("success"):
                print(f"✓ 완료 ({execution_time:.2f}초)")

                return ActionResult(
                    action=action,
                    success=True,
                    result=result.get("result"),
                    execution_time_seconds=execution_time
                )

            else:
                error_msg = result.get("error", "Unknown error")
                last_error = error_msg

                if attempt < max_retries and _is_retryable_error(error_msg):
                    print(f"⚠️  실패 (재시도 가능): {error_msg}")
                    continue

                else:
                    print(f"✗ 실패: {error_msg}")

                    return ActionResult(
                        action=action,
                        success=False,
                        error=error_msg,
                        execution_time_seconds=execution_time
                    )

        except FuturesTimeoutError:
            execution_time = time.time() - start_time
            error_msg = f"타임아웃 ({timeout}초 초과)"
            last_error = error_msg

            if attempt < max_retries:
                print(f"⏱️  {error_msg} - 재시도 중...")
                continue

            else:
                print(f"✗ {error_msg}")

                return ActionResult(
                    action=action,
                    success=False,
                    error=error_msg,
                    execution_time_seconds=execution_time
                )

        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = str(e)
            last_error = error_msg

            if attempt < max_retries and _is_retryable_error(error_msg):
                print(f"⚠️  예외 발생 (재시도 가능): {e}")
                continue

            else:
                print(f"✗ 예외 발생: {e}")

                return ActionResult(
                    action=action,
                    success=False,
                    error=error_msg,
                    execution_time_seconds=execution_time
                )

    return ActionResult(
        action=action,
        success=False,
        error=f"모든 재시도 실패: {last_error}",
        execution_time_seconds=0.0
    )

def _call_mcp_tool_with_timeout(action: Action, timeout: float) -> Dict[str, Any]:
    """타임아웃을 적용하여 MCP 도구 호출

    ThreadPoolExecutor를 사용하여 별도 스레드에서 MCP 도구를 호출하고,
    지정된 시간 내에 응답이 없으면 TimeoutError 발생

    Args:
        action: 실행할 액션
        timeout: 타임아웃 (초)

    Returns:
        Dict[str, Any]: MCP 호출 결과
            - success: 성공 여부
            - result: 결과 데이터 (성공 시)
            - error: 에러 메시지 (실패 시)

    Raises:
        FuturesTimeoutError: 타임아웃 발생 시
    """
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_call_mcp_tool, action)

        return future.result(timeout=timeout)

def _call_mcp_tool(action: Action) -> Dict[str, Any]:
    """MCP 도구 호출

    전역 싱글톤 MCP 클라이언트를 사용하여 도구 호출

    Args:
        action: 실행할 액션

    Returns:
        Dict[str, Any]: MCP 호출 결과
            - success: 성공 여부
            - result: 결과 데이터 (성공 시)
            - error: 에러 메시지 (실패 시)
    """
    client = get_mcp_client()

    return client.call_tool(
        server_name=action.tool,
        tool_name=action.operation,
        arguments=action.params
    )

def _is_retryable_error(error_msg: str) -> bool:
    """재시도 가능한 에러인지 판단

    네트워크 관련 일시적 에러는 재시도 가능으로 판단

    Args:
        error_msg: 에러 메시지

    Returns:
        bool: 재시도 가능 여부

    Note:
        재시도 가능 패턴:
        - connection: 연결 실패
        - timeout: 타임아웃
        - temporary: 일시적 에러
        - unavailable: 서비스 불가
        - network: 네트워크 에러
        - refused: 연결 거부
        - reset: 연결 리셋
    """
    retryable_patterns = [
        "connection",
        "timeout",
        "temporary",
        "unavailable",
        "network",
        "refused",
        "reset",
    ]
    error_lower = error_msg.lower()

    return any(pattern in error_lower for pattern in retryable_patterns)

