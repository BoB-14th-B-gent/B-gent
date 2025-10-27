"""액션 실행기 모듈

MCP 도구 호출, 타임아웃 및 재시도 관리 담당
Lazy Loading으로 필요한 MCP 서버만 초기화
"""
from __future__ import annotations
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Dict, Any, Optional
from .schemas.actions import Action, ActionResult
from .mcp_lazy_client import get_mcp_client_for_server
from .storage.evidence_logger import log_mcp_execution

def execute_action(action: Action, job_id: Optional[str] = None) -> ActionResult:
    """액션 실행 (재시도 및 타임아웃 지원)

    MCP 도구 호출 및 액션 실행, 실패 시 자동 재시도
    재시�� 가능한 에러인 경우 지수 백오프(exponential backoff) 적용

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
        job_id: 작업 ID (MCP 로깅용)

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

    if action.params.get("_skip_execution"):
        print(f"[!]  건너뜀: {action.tool}.{action.operation}")
        print(f"   이유: 이전 단계 실패로 인해 실행 불가")
        return ActionResult(
            action=action,
            success=False,
            error="이전 단계에서 필요한 값을 추출하지 못해 실행을 건너뜁니다.",
            execution_time_seconds=0.0
        )

    for attempt in range(max_retries + 1):
        start_time = time.time()

        try:

            if attempt > 0:
                print(f"[!] 재시도 {attempt}/{max_retries}: {action.tool}.{action.operation}")
                sleep_time = min(2 ** (attempt - 1), 10)
                time.sleep(sleep_time)

            else:
                print(f"   실행 중: {action.tool}.{action.operation}")
                print(f"   이유: {action.reason}")
            result = _call_mcp_tool_with_timeout(action, timeout)
            execution_time = time.time() - start_time

            # 결과 타입 검증 (디버깅용)
            if not isinstance(result, dict):
                error_msg = f"MCP 응답 타입 오류: {type(result).__name__} (dict 기대됨)"
                print(f"[X] {error_msg}")
                print(f"   응답 내용: {str(result)[:500]}")
                return ActionResult(
                    action=action,
                    success=False,
                    error=error_msg,
                    execution_time_seconds=execution_time
                )

            if result.get("success"):
                result_data = result.get("result", "")

                log_mcp_execution(
                    mcp_name=action.tool,
                    tool_name=action.operation,
                    request=action.params,
                    response=result_data,
                    success=True,
                    job_id=job_id
                )

                if action.tool == "sleuthkit" and action.operation == "search_inode_by_path":
                    try:
                        if isinstance(result_data, str):
                            import json
                            parsed = json.loads(result_data)
                        else:
                            parsed = result_data

                        inodes = parsed.get("inodes", [])
                        if isinstance(inodes, list) and any("not found" in str(inode).lower() or "error" in str(inode).lower() for inode in inodes):
                            error_msg = f"파일을 찾을 수 없습니다: {parsed.get('path', 'unknown')}"
                            print(f"[X] 실패: {error_msg}")
                            print(f"   inode 검색 결과: {inodes}")
                            return ActionResult(
                                action=action,
                                success=False,
                                error=error_msg,
                                result=result_data,
                                execution_time_seconds=execution_time
                            )
                    except Exception as e:
                        print(f"[X]  결과 검증 중 오류 (무시하고 계속): {e}")

                if result_data:
                    preview = str(result_data)
                    if len(preview) > 1000:
                        preview = preview[:1000] + f"\n... (총 {len(preview)}자, 나머지 생략)"

                    print(f"[✓] 완료 ({execution_time:.2f}초)")
                    print(f"\n   결과:")
                    print("-" * 60)
                    print(preview)
                    print("-" * 60)
                else:
                    print(f"[✓] 완료 ({execution_time:.2f}초) - 결과 없음")

                return ActionResult(
                    action=action,
                    success=True,
                    result=result_data,
                    execution_time_seconds=execution_time
                )

            else:
                error_msg = result.get("error", "Unknown error")
                last_error = error_msg

                log_mcp_execution(
                    mcp_name=action.tool,
                    tool_name=action.operation,
                    request=action.params,
                    response=result.get("result"),
                    success=False,
                    job_id=job_id
                )

                # 전체 응답 출력 (디버깅용)
                print(f"[X]  MCP 응답 (success=False):")
                print(f"   응답 전체: {result}")
                print(f"   에러 메시지: {error_msg}")

                if attempt < max_retries and _is_retryable_error(error_msg):
                    print(f"[X]  실패 (재시도 가능): {error_msg}")
                    continue

                else:
                    print(f"[X] 실패: {error_msg}")

                    return ActionResult(
                        action=action,
                        success=False,
                        error=error_msg,
                        execution_time_seconds=execution_time
                    )

        except (FuturesTimeoutError, asyncio.TimeoutError):
            execution_time = time.time() - start_time
            error_msg = f"타임아웃 ({timeout}초 초과)"
            last_error = error_msg

            if attempt < max_retries:
                print(f"[!]  {error_msg} - 재시도 중...")
                continue

            else:
                print(f"[X] {error_msg}")

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
                print(f"[X]  예외 발생 (재시도 가능): {e}")
                continue

            else:
                print(f"[X] 예외 발생: {e}")
                # traceback 출력 (디버깅용)
                import traceback
                traceback.print_exc()

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

    ThreadPoolExecutor를 사용하여 별도 스레드에서 실행하고,
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
    client = get_mcp_client_for_server(action.tool)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            client.call_tool,
            server_name=action.tool,
            tool_name=action.operation,
            arguments=action.params,
            timeout=None
        )

        try:
            return future.result(timeout=timeout)
        except FuturesTimeoutError:
            raise FuturesTimeoutError(f"MCP 도구 호출 타임아웃 ({timeout}초)")

def _call_mcp_tool(action: Action) -> Dict[str, Any]:
    """MCP 도구 호출 (Lazy Loading)

    필요한 MCP 서버만 초기화하여 도구 호출
    성능 최적화: 사용하지 않는 서버는 초기화하지 않음

    Args:
        action: 실행할 액션

    Returns:
        Dict[str, Any]: MCP 호출 결과
            - success: 성공 여부
            - result: 결과 데이터 (성공 시)
            - error: 에러 메시지 (실패 시)
    """
    client = get_mcp_client_for_server(action.tool)

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

