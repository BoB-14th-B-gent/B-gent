"""Task Queue 관리 모듈

High-level Task의 큐 관리 및 의존성 해결
"""
from __future__ import annotations
from typing import List, Optional, Set, Dict, Any
from collections import deque
from ..schemas.task import HighLevelTask, TaskStatus


class TaskQueue:
    """Task 큐 관리 클래스

    FIFO 기반이지만 의존성을 고려하여 실행 가능한 Task만 반환
    DAG(방향성 비순환 그래프) 기반 의존성 해결

    Attributes:
        _queue: Task 대기 큐 (FIFO)
        _tasks_by_id: Task ID → Task 객체 매핑
        _completed_task_ids: 완료된 Task ID 집합
        _in_progress_task_ids: 실행 중인 Task ID 집합

    Example:
        >>> queue = TaskQueue()
        >>> task1 = HighLevelTask(task_id="task_001", description="로그 검색", ...)
        >>> task2 = HighLevelTask(task_id="task_002", description="파일 추출", dependencies=["task_001"], ...)
        >>> queue.add_tasks([task1, task2])
        >>>
        >>> # task1만 실행 가능 (의존성 없음)
        >>> next_task = queue.get_next_ready_task()
        >>> assert next_task.task_id == "task_001"
        >>>
        >>> # task1 완료 표시
        >>> queue.mark_completed("task_001")
        >>>
        >>> # 이제 task2 실행 가능 (의존성 충족)
        >>> next_task = queue.get_next_ready_task()
        >>> assert next_task.task_id == "task_002"
    """

    def __init__(self):
        self._queue: deque[HighLevelTask] = deque()
        self._tasks_by_id: Dict[str, HighLevelTask] = {}
        self._completed_task_ids: Set[str] = set()
        self._in_progress_task_ids: Set[str] = set()

    def add_task(self, task: HighLevelTask) -> None:
        """단일 Task 추가

        Args:
            task: 추가할 Task
        """
        self._queue.append(task)
        self._tasks_by_id[task.task_id] = task

    def add_tasks(self, tasks: List[HighLevelTask]) -> None:
        """여러 Task 일괄 추가

        Args:
            tasks: Task 리스트
        """
        for task in tasks:
            self.add_task(task)

    def get_next_ready_task(self) -> Optional[HighLevelTask]:
        """다음 실행 가능한 Task 반환

        큐에서 순차적으로 탐색하여 의존성이 충족된 첫 번째 Task 반환
        의존성이 충족되지 않은 Task는 큐에 남겨둠

        Returns:
            Optional[HighLevelTask]: 실행 가능한 Task (없으면 None)

        로직:
            1. 큐를 순회하며 각 Task 확인
            2. 의존성이 충족된 Task 발견 시:
               - 큐에서 제거
               - 상태를 IN_PROGRESS로 변경
               - _in_progress_task_ids에 추가
               - 반환
            3. 의존성이 충족되지 않은 Task는 큐 뒤로 이동 (재확인용)
            4. 큐를 한 바퀴 돌아도 실행 가능한 Task가 없으면 None 반환
        """
        if not self._queue:
            return None

        checked_count = 0
        max_checks = len(self._queue)

        while checked_count < max_checks:
            task = self._queue.popleft()
            checked_count += 1

            if task.is_ready(self._completed_task_ids):
                task.status = TaskStatus.IN_PROGRESS
                self._in_progress_task_ids.add(task.task_id)
                return task
            else:
                self._queue.append(task)
        return None

    def mark_completed(self, task_id: str, results: List[Dict[str, Any]] = None) -> None:
        """Task 완료 표시

        Args:
            task_id: 완료된 Task ID
            results: 실행 결과 (선택)
        """
        if task_id in self._tasks_by_id:
            task = self._tasks_by_id[task_id]
            task.status = TaskStatus.COMPLETED
            if results:
                task.execution_results = results

        self._completed_task_ids.add(task_id)
        self._in_progress_task_ids.discard(task_id)

    def mark_failed(self, task_id: str, error: str = None) -> None:
        """Task 실패 표시

        Args:
            task_id: 실패한 Task ID
            error: 에러 메시지 (선택)
        """
        if task_id in self._tasks_by_id:
            task = self._tasks_by_id[task_id]
            task.status = TaskStatus.FAILED
            if error:
                task.metadata["error"] = error

        self._in_progress_task_ids.discard(task_id)

    def is_empty(self) -> bool:
        """큐가 비어있는지 확인

        Returns:
            bool: 큐가 비어있으면 True
        """
        return len(self._queue) == 0

    def has_ready_tasks(self) -> bool:
        """실행 가능한 Task가 있는지 확인 (큐에서 제거하지 않음)

        Returns:
            bool: 실행 가능한 Task가 있으면 True
        """
        if not self._queue:
            return False

        for task in self._queue:
            if task.is_ready(self._completed_task_ids):
                return True
        return False

    def get_pending_count(self) -> int:
        """대기 중인 Task 수

        Returns:
            int: 큐에 남아있는 Task 수
        """
        return len(self._queue)

    def get_completed_count(self) -> int:
        """완료된 Task 수

        Returns:
            int: 완료된 Task 수
        """
        return len(self._completed_task_ids)

    def get_all_tasks(self) -> List[HighLevelTask]:
        """모든 Task 반환 (ID로 접근)

        Returns:
            List[HighLevelTask]: 전체 Task 리스트
        """
        return list(self._tasks_by_id.values())

    def get_task_by_id(self, task_id: str) -> Optional[HighLevelTask]:
        """Task ID로 Task 조회

        Args:
            task_id: Task ID

        Returns:
            Optional[HighLevelTask]: Task 객체 (없으면 None)
        """
        return self._tasks_by_id.get(task_id)

    def get_status_summary(self) -> Dict[str, int]:
        """Task 상태 요약

        Returns:
            Dict[str, int]: 상태별 Task 수
                {"pending": 3, "in_progress": 1, "completed": 2, "failed": 0}
        """
        summary = {
            "pending": 0,
            "in_progress": 0,
            "completed": 0,
            "failed": 0
        }

        for task in self._tasks_by_id.values():
            summary[task.status.value] += 1

        return summary

    def validate_dependencies(self) -> bool:
        """의존성 검증: 순환 참조 확인

        Returns:
            bool: 의존성이 유효하면 True, 순환 참조가 있으면 False

        알고리즘: Topological Sort (Kahn's Algorithm)
        """
        in_degree = {task_id: 0 for task_id in self._tasks_by_id}
        for task in self._tasks_by_id.values():
            for dep_id in task.dependencies:
                if dep_id in in_degree:
                    in_degree[task.task_id] += 1

        queue = deque([task_id for task_id, degree in in_degree.items() if degree == 0])
        sorted_count = 0

        while queue:
            task_id = queue.popleft()
            sorted_count += 1

            for task in self._tasks_by_id.values():
                if task_id in task.dependencies:
                    in_degree[task.task_id] -= 1
                    if in_degree[task.task_id] == 0:
                        queue.append(task.task_id)
        return sorted_count == len(self._tasks_by_id)
