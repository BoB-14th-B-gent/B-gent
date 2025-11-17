"""프롬프트 파일 로더 유틸리티

프롬프트 파일을 읽어오는 유틸리티 함수 모음
"""
import os
from pathlib import Path
from typing import Dict, Optional

# 프롬프트 디렉토리 경로
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# 캐시: 파일을 한 번만 읽고 메모리에 저장
_prompt_cache: Dict[str, str] = {}


def load_prompt(filename: str, use_cache: bool = True) -> str:
    """프롬프트 파일 로드

    Args:
        filename: 프롬프트 파일 이름 (예: "high_level_planning_system.txt")
        use_cache: 캐시 사용 여부 (기본값: True)

    Returns:
        str: 프롬프트 내용

    Raises:
        FileNotFoundError: 파일이 없는 경우

    Example:
        >>> prompt = load_prompt("high_level_planning_system.txt")
        >>> print(prompt[:100])
    """
    if use_cache and filename in _prompt_cache:
        return _prompt_cache[filename]

    file_path = PROMPTS_DIR / filename

    if not file_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    if use_cache:
        _prompt_cache[filename] = content

    return content


def format_prompt(filename: str, **kwargs) -> str:
    """프롬프트 파일 로드 및 포맷팅

    Args:
        filename: 프롬프트 파일 이름
        **kwargs: 포맷팅에 사용할 키워드 인자

    Returns:
        str: 포맷팅된 프롬프트 내용

    Example:
        >>> prompt = format_prompt("react_task_template.txt",
        ...                        task_description="Analyze disk image",
        ...                        dependency_context="")
    """
    template = load_prompt(filename)
    return template.format(**kwargs)


def clear_cache():
    """프롬프트 캐시 초기화

    개발/디버깅 시 프롬프트 파일을 수정한 후 재로드할 때 사용
    """
    global _prompt_cache
    _prompt_cache.clear()
