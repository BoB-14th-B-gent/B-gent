"""공통 스키마 및 상태 모듈

에이전트 상태(AgentState)와 작업 상태(JobState) 구조 정의
"""
from __future__ import annotations
from typing import Dict, Any, List, Optional, TypedDict
from dataclasses import dataclass, field
from .actions import Action, ActionResult

class AgentState(TypedDict, total=False):
    """LangGraph 워크플로우 상태 (TypedDict 버전)

    LangGraph는 TypedDict를 사용하여 타입 안전성을 보장합니다.
    total=False는 모든 필드가 선택적임을 의미합니다.
    """
    job_id: str
    user_prompt: str
    file_path: Optional[str]
    file_meta: Dict[str, Any]
    plan: List[Dict[str, Any]]
    results: List[Dict[str, Any]]
    current_step: int
    completed: bool
    error: Optional[str]

@dataclass

class JobState:
    """LangGraph 작업 상태 (Dataclass 버전, 레거시 호환용)"""
    job_id: str
    user_prompt: str
    file_path: Optional[str] = None
    file_meta: Dict[str, Any] = field(default_factory=dict)
    plan: List[Action] = field(default_factory=list)
    results: List[ActionResult] = field(default_factory=list)
    current_step: int = 0
    completed: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:

        return {
            "job_id": self.job_id,
            "user_prompt": self.user_prompt,
            "file_path": self.file_path,
            "file_meta": self.file_meta,
            "plan": [a.to_dict() for a in self.plan],
            "results": [r.to_dict() for r in self.results],
            "current_step": self.current_step,
            "completed": self.completed,
            "error": self.error
        }

