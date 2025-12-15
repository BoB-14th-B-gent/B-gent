"""Task 스키마 정의

High-level Task와 Low-level Action을 연결하는 중간 계층
"""
from __future__ import annotations
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum


class TaskStatus(Enum):
    """Task 상태"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"


class TaskType(Enum):
    """Task 타입 (분석 대상별)"""
    LOG_COLLECTION = "log_collection"
    FILE_EXTRACT = "file_extract"
    ARTIFACT_COLLECTION = "artifact_collection"
    FILE_ANALYSIS = "file_analysis"
    CUSTOM = "custom"


@dataclass
class HighLevelTask:
    """High-level Task (상위 계획)

    LLM이 생성하는 추상적인 작업 단계
    각 Task는 RAG 검색을 통해 Low-level Action으로 변환됨

    Attributes:
        task_id: Task 고유 ID (예: "task_001")
        description: Task 설명 (예: "Windows 로그에서 의심 활동 탐지")
        task_type: Task 타입 (LOG_COLLECTION, FILE_EXTRACT 등)
        target_files: 분석 대상 파일 경로 리스트 (선택)
        dependencies: 의존하는 Task ID 리스트 (선택)
        status: Task 상태 (PENDING, IN_PROGRESS, COMPLETED, FAILED)
        low_level_plan: RAG 검색으로 생성된 Low-level Action 리스트
        execution_results: 실행 결과 리스트
        metadata: 추가 메타데이터 (도구 힌트, 우선순위 등)

    Example:
        >>> task = HighLevelTask(
        ...     task_id="task_001",
        ...     description="Elasticsearch에서 IIS 로그 검색 후 cmd.exe 실행 이벤트 탐지",
        ...     task_type=TaskType.LOG_COLLECTION,
        ...     dependencies=[],
        ...     metadata={"priority": "high", "tool_hint": "elastic"}
        ... )
    """
    task_id: str
    description: str
    task_type: TaskType
    target_files: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    low_level_plan: List[Dict[str, Any]] = field(default_factory=list)
    execution_results: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    mcp_call: Optional[Dict[str, Any]] = field(default=None)

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환 (JSON 직렬화용)"""
        result = {
            "task_id": self.task_id,
            "description": self.description,
            "task_type": self.task_type.value,
            "target_files": self.target_files,
            "dependencies": self.dependencies,
            "status": self.status.value,
            "low_level_plan": self.low_level_plan,
            "execution_results": self.execution_results,
            "metadata": self.metadata
        }
        if self.mcp_call:
            result["mcp_call"] = self.mcp_call
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> HighLevelTask:
        """딕셔너리에서 생성"""
        return cls(
            task_id=data["task_id"],
            description=data["description"],
            task_type=TaskType(data["task_type"]),
            target_files=data.get("target_files", []),
            dependencies=data.get("dependencies", []),
            status=TaskStatus(data.get("status", "pending")),
            low_level_plan=data.get("low_level_plan", []),
            execution_results=data.get("execution_results", []),
            metadata=data.get("metadata", {}),
            mcp_call=data.get("mcp_call")
        )

    def is_ready(self, completed_task_ids: set) -> bool:
        """의존성 확인: 모든 의존 Task가 완료되었는지 확인

        Args:
            completed_task_ids: 완료된 Task ID 집합

        Returns:
            bool: 실행 가능 여부 (의존성이 모두 충족되면 True)
        """
        if not self.dependencies:
            return True
        return all(dep_id in completed_task_ids for dep_id in self.dependencies)

    def get_dependency_results(self, all_tasks: List[HighLevelTask]) -> Dict[str, List[Dict[str, Any]]]:
        """의존하는 Task들의 실행 결과 가져오기

        Args:
            all_tasks: 전체 Task 리스트

        Returns:
            Dict[str, List[Dict]]: {task_id: execution_results} 형태
        """
        dependency_results = {}
        for task in all_tasks:
            if task.task_id in self.dependencies:
                dependency_results[task.task_id] = task.execution_results
        return dependency_results
