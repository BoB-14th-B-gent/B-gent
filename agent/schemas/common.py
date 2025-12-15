"""공통 스키마 및 상태 모듈

에이전트 상태(AgentState)와 작업 상태(JobState) 구조 정의
"""
from __future__ import annotations
from typing import Dict, Any, List, Optional, TypedDict
from dataclasses import dataclass, field
from .actions import Action, ActionResult

class AgentState(TypedDict, total=False):
    """LangGraph 워크플로우 상태 (TypedDict 버전) - Two-Stage Planning

    LangGraph는 TypedDict를 사용하여 타입 안전성을 보장합니다.
    total=False는 모든 필드가 선택적임을 의미합니다.

    Two-Stage Planning 추가 필드:
        - task_queue: High-level Task 큐 (직렬화된 TaskQueue)
        - current_task: 현재 처리 중인 Task (dict)
        - completed_tasks: 완료된 Task 목록 (dict list)
        - react_context: ReAct 루프 컨텍스트 (dict)

    Multi-Stage Conversation 필드:
        - conversation_id: 대화 ID
        - stage_id: Stage 번호 (1부터 시작)
        - is_first_execution: 첫 번째 실행 여부
        - previous_context: 이전 Stage AI 분석 결과
        - ioc_analysis_results: 현재 Stage IoC 분석 결과
    """
    job_id: str
    user_prompt: str
    file_paths: Optional[List[str]]
    file_meta: Dict[str, Any]

    high_level_tasks: List[Dict[str, Any]]
    task_queue_state: Dict[str, Any]
    current_task: Optional[Dict[str, Any]]
    completed_tasks: List[Dict[str, Any]]
    react_context: Dict[str, Any]

    plan: List[Dict[str, Any]]
    results: List[Dict[str, Any]]
    current_step: int
    timing: Dict[str, Any]

    completed: bool
    error: Optional[str]

    conversation_id: Optional[str]
    stage_id: int
    is_first_execution: bool
    previous_context: Optional[Dict[str, Any]]
    ioc_analysis_results: List[Dict[str, Any]]

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

