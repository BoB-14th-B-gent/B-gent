"""디버깅 출력 유틸리티 모듈

환경 변수 DEBUG=1 설정 시에만 디버깅 메시지 출력
모든 에이전트 모듈에서 일관된 디버깅 출력을 위해 사용
"""
from __future__ import annotations
import os
import sys
from functools import lru_cache


@lru_cache(maxsize=1)
def is_debug_mode() -> bool:
    """디버그 모드 활성화 여부 확인

    환경 변수 DEBUG=1이면 True 반환
    MCP_DEBUG=1도 디버그 모드로 취급 (하위 호환성)

    Returns:
        bool: 디버그 모드 활성화 여부
    """
    return os.getenv("DEBUG") == "1" or os.getenv("MCP_DEBUG") == "1"


def debug_print(*args, **kwargs) -> None:
    """디버그 모드일 때만 stdout에 출력

    DEBUG=1 환경 변수가 설정된 경우에만 메시지 출력
    print()와 동일한 인터페이스 제공

    Args:
        *args: print()에 전달할 인자들
        **kwargs: print()에 전달할 키워드 인자들
    """
    if is_debug_mode():
        print(*args, **kwargs)


def debug_write(message: str, flush: bool = True) -> None:
    """디버그 모드일 때만 sys.__stdout__에 직접 출력

    리다이렉트를 우회하여 실제 stdout에 출력
    sys.__stdout__.write()의 디버그 버전

    Args:
        message: 출력할 메시지
        flush: 출력 후 flush 여부 (기본값: True)
    """
    if is_debug_mode():
        sys.__stdout__.write(message)
        if flush:
            sys.__stdout__.flush()


def debug_error(message: str, flush: bool = True) -> None:
    """디버그 모드일 때만 sys.__stderr__에 직접 출력

    리다이렉트를 우회하여 실제 stderr에 출력
    sys.__stderr__.write()의 디버그 버전

    Args:
        message: 출력할 에러 메시지
        flush: 출력 후 flush 여부 (기본값: True)
    """
    if is_debug_mode():
        sys.__stderr__.write(message)
        if flush:
            sys.__stderr__.flush()


def info_print(*args, **kwargs) -> None:
    """정보성 메시지 출력 (항상 출력)

    디버그 모드와 관계없이 항상 출력되어야 하는 정보 메시지용
    에러 메시지나 중요 상태 변경 알림에 사용

    Args:
        *args: print()에 전달할 인자들
        **kwargs: print()에 전달할 키워드 인자들
    """
    print(*args, **kwargs)


def info_write(message: str, flush: bool = True) -> None:
    """정보성 메시지 직접 출력 (항상 출력)

    리다이렉트를 우회하여 실제 stdout에 출력
    디버그 모드와 관계없이 항상 출력

    Args:
        message: 출력할 메시지
        flush: 출력 후 flush 여부 (기본값: True)
    """
    sys.__stdout__.write(message)
    if flush:
        sys.__stdout__.flush()


def error_write(message: str, flush: bool = True) -> None:
    """에러 메시지 직접 출력 (항상 출력)

    리다이렉트를 우회하여 실제 stderr에 출력
    디버그 모드와 관계없이 항상 출력

    Args:
        message: 출력할 에러 메시지
        flush: 출력 후 flush 여부 (기본값: True)
    """
    sys.__stderr__.write(message)
    if flush:
        sys.__stderr__.flush()
