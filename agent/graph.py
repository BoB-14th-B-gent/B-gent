"""LangGraph 워크플로우 정의 모듈

Simple Mode: 계획 생성 → 실행 → 완료
Two-Stage Mode: High-level Task 생성 → Task별 Low-level 계획 → 실행
"""
from __future__ import annotations
from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, END
from .schemas.common import AgentState
from .planner import generate_plan
from .executor import execute_action

def create_workflow(mode: Literal["simple", "two_stage"] = "simple") -> StateGraph:
    """LangGraph 워크플로우 생성

    Args:
        mode: 워크플로우 모드
            - "simple": 단순 계획 → 실행 모드 (기본값)
            - "two_stage": High-level Task → Low-level Action 2단계 모드

    Returns:
        StateGraph: 컴파일된 LangGraph 워크플로우

    Example (Simple Mode):
        >>> workflow = create_workflow()
        >>> initial_state = {
        ...     "job_id": "abc123",
        ...     "user_prompt": "로그 검색",
        ...     "plan": [],
        ...     "results": [],
        ...     "current_step": 0,
        ...     "completed": False
        ... }
        >>> final_state = workflow.invoke(initial_state)

    Example (Two-Stage Mode):
        >>> workflow = create_workflow(mode="two_stage")
        >>> initial_state = {
        ...     "job_id": "abc123",
        ...     "user_prompt": "악성코드 분석",
        ...     "file_paths": ["/path/to/file"],
        ...     "completed": False
        ... }
        >>> final_state = workflow.invoke(initial_state)
    """
    if mode == "two_stage":
        return _create_two_stage_workflow()
    else:
        return _create_simple_workflow()


def _create_simple_workflow() -> StateGraph:
    """Simple Mode 워크플로우 생성

    워크플로우 구조:
        [START] → [plan] → [execute] ⇄ [execute] → [finish] → [END]
                             ↓
                        should_continue?
                         ↓        ↓
                     continue   finish

    로직:
        1. plan 노드에서 실행 계획 생성
        2. execute 노드에서 액션 순차 실행
        3. should_continue로 다음 액션 존재 여부 판단
        4. 모든 액션 완료 시 finish 노드로 이동

    Returns:
        StateGraph: 컴파일된 LangGraph 워크플로우
    """
    workflow = StateGraph(AgentState)
    workflow.add_node("plan", node_plan)
    workflow.add_node("execute", node_execute)
    workflow.add_node("finish", node_finish)
    workflow.set_entry_point("plan")
    workflow.add_edge("plan", "execute")
    workflow.add_conditional_edges(
        "execute",
        should_continue,
        {
            "continue": "execute",
            "finish": "finish"
        }
    )
    workflow.add_edge("finish", END)

    return workflow.compile()

def node_plan(state: Dict[str, Any]) -> Dict[str, Any]:
    """계획 생성 노드

    사용자 프롬프트를 기반으로 실행 계획 생성

    Args:
        state: 현재 상태
            - user_prompt: 사용자 요청
            - file_paths: 파일 경로 배열 (선택)
            - file_meta: 파일 메타데이터 (선택)

    Returns:
        Dict[str, Any]: 업데이트된 상태
            - plan: 생성된 실행 계획 (Action.to_dict() 리스트)
            - current_step: 0으로 초기화
            - results: 빈 리스트로 초기화
            - error: 검증 실패 시 오류 메시지
    """
    print("\n[단계 1/3] 실행 계획 생성 중...")
    user_prompt = state["user_prompt"]
    file_paths = state.get("file_paths", [])
    file_meta = state.get("file_meta", {})

    try:
        plan = generate_plan(user_prompt, file_paths, file_meta)

        if not plan:
            error_msg = "실행 계획을 생성할 수 없습니다. 요청을 다시 확인해주세요."
            print(f"\n[X]  {error_msg}\n")

            return {
                **state,
                "plan": [],
                "current_step": 0,
                "results": [],
                "error": error_msg,
                "completed": True
            }
        print(f"✓ 실행 계획 생성 완료: {len(plan)}단계\n")

        for idx, action in enumerate(plan, 1):
            print(f"  {idx}. {action.tool}.{action.operation} - {action.reason}")

        return {
            **state,
            "plan": [a.to_dict() for a in plan],
            "current_step": 0,
            "results": []
        }

    except ValueError as e:
        error_msg = str(e)
        print(f"\n{error_msg}\n")

        return {
            **state,
            "plan": [],
            "current_step": 0,
            "results": [],
            "error": error_msg,
            "completed": True
        }

    except Exception as e:
        error_msg = f"계획 생성 중 오류 발생: {str(e)}"
        print(f"\n[X] {error_msg}\n")
        import traceback
        traceback.print_exc()

        return {
            **state,
            "plan": [],
            "current_step": 0,
            "results": [],
            "error": error_msg,
            "completed": True
        }

def node_execute(state: Dict[str, Any]) -> Dict[str, Any]:
    """액션 실행 노드

    현재 단계의 액션을 실행하고 결과 저장

    Args:
        state: 현재 상태
            - plan: 실행 계획
            - current_step: 현재 실행 단계 (0-based index)
            - results: 이전 실행 결과 리스트

    Returns:
        Dict[str, Any]: 업데이트된 상태
            - results: 실행 결과 추가
            - current_step: 다음 단계로 증가

    로직:
        1. 현재 단계의 액션 가져오기
        2. PlaceholderResolver로 파라미터 치환 (이전 결과 사용)
        3. Executor로 액션 실행
        4. 결과를 state.results에 추가
        5. current_step 증가
    """
    from .schemas.actions import Action
    from .placeholder_resolver import PlaceholderResolver
    current_step = state["current_step"]
    plan = state["plan"]
    results = state.get("results", [])

    if current_step >= len(plan):

        return state
    print(f"\n[단계 2/3] 액션 실행 중... ({current_step + 1}/{len(plan)})")
    action_dict = plan[current_step]
    params = action_dict.get("params", {})
    params = PlaceholderResolver.resolve(params, results)
    action = Action(
        tool=action_dict["tool"],
        operation=action_dict["operation"],
        params=params,
        reason=action_dict.get("reason", ""),
        timeout_seconds=action_dict.get("timeout_seconds", 300)
    )
    result = execute_action(action, job_id=state.get("job_id"))
    results.append(result.to_dict())

    return {
        **state,
        "results": results,
        "current_step": current_step + 1
    }

def node_finish(state: Dict[str, Any]) -> Dict[str, Any]:
    """완료 노드

    모든 액션 실행이 완료되었음을 표시

    Args:
        state: 현재 상태

    Returns:
        Dict[str, Any]: 업데이트된 상태
            - completed: True로 설정
    """
    print("\n[단계 3/3] 작업 완료\n")

    return {
        **state,
        "completed": True
    }

def should_continue(state: Dict[str, Any]) -> str:
    """계속 실행할지 판단하는 조건부 엣지 함수

    Args:
        state: 현재 상태
            - current_step: 현재 실행 단계
            - plan: 실행 계획
            - error: 오류 메시지 (있는 경우)

    Returns:
        str: 다음 노드 이름
            - "continue": 다음 액션 실행
            - "finish": 완료
    """
    if state.get("error") or not state.get("plan"):
        return "finish"
    current_step = state["current_step"]
    plan = state["plan"]

    if current_step < len(plan):
        return "continue"
    else:
        return "finish"


# ============================================================================
# Two-Stage Planning Mode
# ============================================================================

def _create_two_stage_workflow() -> StateGraph:
    """Two-Stage Planning 워크플로우 생성

    워크플로우 구조:
        [START]
          ↓
        [high_level_plan] → TaskQueue 생성
          ↓
        [get_next_task] → 다음 Task 꺼내기
          ↓
        [low_level_plan] → RAG 검색 + LLM 계획 생성
          ↓
        [execute] ⇄ [execute] → Low-level Action 실행
          ↓
        [task_complete] → Task 완료 표시
          ↓
        has_more_tasks?
          ├─ yes → [get_next_task]
          └─ no → [finish] → [END]

    로직:
        1. high_level_plan: 사용자 프롬프트 → High-level Task 리스트 생성
        2. get_next_task: TaskQueue에서 실행 가능한 Task 꺼내기
        3. low_level_plan: Task 임베딩 → RAG 검색 → Low-level Action 생성
        4. execute: Low-level Action 순차 실행
        5. task_complete: Task 결과 저장, TaskQueue 완료 표시
        6. has_more_tasks: 다음 Task가 있으면 2번으로, 없으면 종료

    Returns:
        StateGraph: 컴파일된 LangGraph 워크플로우
    """
    workflow = StateGraph(AgentState)

    workflow.add_node("high_level_plan", node_high_level_plan)
    workflow.add_node("get_next_task", node_get_next_task)
    workflow.add_node("low_level_plan", node_low_level_plan)
    workflow.add_node("execute", node_execute_two_stage)
    workflow.add_node("task_complete", node_task_complete)
    workflow.add_node("finish", node_finish_two_stage)

    workflow.set_entry_point("high_level_plan")
    workflow.add_edge("high_level_plan", "get_next_task")
    workflow.add_conditional_edges(
        "get_next_task",
        should_get_next_task,
        {
            "plan": "low_level_plan",
            "finish": "finish"
        }
    )
    workflow.add_edge("low_level_plan", "execute")
    workflow.add_conditional_edges(
        "execute",
        should_continue_execute,
        {
            "continue": "execute",
            "task_complete": "task_complete"
        }
    )
    workflow.add_edge("task_complete", "get_next_task")
    workflow.add_edge("finish", END)

    return workflow.compile()


def node_high_level_plan(state: Dict[str, Any]) -> Dict[str, Any]:
    """Phase 1: High-level Task 생성

    사용자 프롬프트 + 파일 목록 → LLM → High-level Task 리스트
    TaskQueue 초기화

    Args:
        state: 현재 상태
            - user_prompt: 사용자 요청
            - file_paths: 파일 경로 리스트
            - file_meta: 파일 메타데이터

    Returns:
        Dict[str, Any]: 업데이트된 상태
            - high_level_tasks: High-level Task 리스트 (dict)
            - task_queue_state: TaskQueue 상태
    """
    import time
    from .high_level_planner import generate_high_level_plan
    from .task_queue import TaskQueue
    from .storage.job_storage import save_agent_state, update_stage

    print("\n" + "="*60)
    print("[Phase 1] High-level Planning")
    print("="*60)

    user_prompt = state["user_prompt"]
    file_paths = state.get("file_paths", [])
    file_meta = state.get("file_meta", {})

    start_time = time.time()

    try:
        high_level_tasks = generate_high_level_plan(user_prompt, file_paths, file_meta)

        if not high_level_tasks:
            error_msg = "High-level 계획을 생성할 수 없습니다."
            print(f"\n[X] {error_msg}\n")
            return {
                **state,
                "high_level_tasks": [],
                "completed": True,
                "error": error_msg
            }

        task_queue = TaskQueue()
        task_queue.add_tasks(high_level_tasks)

        if not task_queue.validate_dependencies():
            error_msg = "Task 간 순환 의존성이 감지되었습니다!"
            print(f"\n[X] {error_msg}\n")
            return {
                **state,
                "high_level_tasks": [],
                "completed": True,
                "error": error_msg
            }

        high_level_planning_time = time.time() - start_time

        print(f"\n✓ High-level 계획 생성 완료: {len(high_level_tasks)}개 Task ({high_level_planning_time:.2f}초)")
        print(f"✓ TaskQueue 초기화 완료")
        print(f"  - 대기 중: {task_queue.get_pending_count()}개")
        print(f"  - 의존성 검증: 통과")

        timing = state.get("timing", {"high_level_planning": 0.0, "tasks": {}})
        timing["high_level_planning"] = high_level_planning_time

        job_id = state.get("job_id")
        if job_id:
            plan_list = [{"task_id": t.task_id, "description": t.description} for t in high_level_tasks]
            save_agent_state(
                agent_id=job_id,
                stage_id=1,
                plan=plan_list,
                status="running",
                mcp_tools=[]
            )

        return {
            **state,
            "high_level_tasks": [t.to_dict() for t in high_level_tasks],
            "task_queue_state": {
                "all_tasks": {t.task_id: t.to_dict() for t in task_queue.get_all_tasks()},
                "completed_ids": list(task_queue._completed_task_ids)
            },
            "completed_tasks": [],
            "current_task": None,
            "timing": timing
        }

    except Exception as e:
        error_msg = f"High-level 계획 생성 실패: {str(e)}"
        print(f"\n[X] {error_msg}\n")
        import traceback
        traceback.print_exc()

        return {
            **state,
            "high_level_tasks": [],
            "completed": True,
            "error": error_msg
        }


def node_get_next_task(state: Dict[str, Any]) -> Dict[str, Any]:
    """다음 실행 가능한 Task 가져오기

    TaskQueue에서 의존성이 충족된 Task 꺼내기

    Args:
        state: 현재 상태

    Returns:
        Dict[str, Any]: 업데이트된 상태
            - current_task: 다음 Task (dict) 또�� None
    """
    from .schemas.task import HighLevelTask, TaskStatus
    from .task_queue import TaskQueue

    task_queue_state = state.get("task_queue_state", {})
    all_tasks_dict = task_queue_state.get("all_tasks", {})
    completed_ids = set(task_queue_state.get("completed_ids", []))

    task_queue = TaskQueue()
    for task_dict in all_tasks_dict.values():
        task = HighLevelTask.from_dict(task_dict)
        if task.status == TaskStatus.PENDING:
            task_queue.add_task(task)
        elif task.status == TaskStatus.COMPLETED:
            task_queue._completed_task_ids.add(task.task_id)

    next_task = task_queue.get_next_ready_task()

    if next_task:
        import time

        print(f"\n[Task Queue] 다음 Task: {next_task.task_id}")
        print(f"  - 설명: {next_task.description}")
        print(f"  - 타입: {next_task.task_type.value}")
        print(f"  - 의존성: {next_task.dependencies if next_task.dependencies else '없음'}")

        all_tasks_dict[next_task.task_id] = next_task.to_dict()

        timing = state.get("timing", {"high_level_planning": 0.0, "tasks": {}})
        if "tasks" not in timing:
            timing["tasks"] = {}
        timing["tasks"][next_task.task_id] = {
            "start_time": time.time(),
            "mcp_search": 0.0,
            "low_level_planning": 0.0,
            "execution": 0.0,
            "total": 0.0
        }

        job_id = state.get("job_id")
        if job_id:
            try:
                stage_num = int(next_task.task_id.split("_")[1])
                update_stage(job_id, stage_num + 1)
            except:
                pass

        return {
            **state,
            "current_task": next_task.to_dict(),
            "task_queue_state": {
                "all_tasks": all_tasks_dict,
                "completed_ids": list(task_queue._completed_task_ids)
            },
            "plan": [],
            "results": [],
            "current_step": 0,
            "timing": timing
        }
    else:
        print(f"\n[Task Queue] 실행 가능한 Task가 없습니다.")
        return {
            **state,
            "current_task": None
        }


def node_low_level_plan(state: Dict[str, Any]) -> Dict[str, Any]:
    """Phase 2: Low-level Action 생성

    Task 설명 임베딩 → RAG 검색 → LLM 계획 생성

    Args:
        state: 현재 상태
            - current_task: 현재 Task (dict)
            - completed_tasks: 완료된 Task 리스트

    Returns:
        Dict[str, Any]: 업데이트된 상태
            - plan: Low-level Action 리스트 (dict)
    """
    import time
    from .schemas.task import HighLevelTask
    from .low_level_planner import generate_low_level_plan

    print("\n" + "-"*60)
    print("[Phase 2] Low-level Planning")
    print("-"*60)

    current_task_dict = state.get("current_task")
    if not current_task_dict:
        return state

    current_task = HighLevelTask.from_dict(current_task_dict)
    completed_tasks = state.get("completed_tasks", [])

    dependency_results = {}
    if current_task.dependencies:
        for completed_task_dict in completed_tasks:
            task_id = completed_task_dict.get("task_id")
            if task_id in current_task.dependencies:
                dependency_results[task_id] = completed_task_dict.get("execution_results", [])

    low_level_start = time.time()

    try:
        actions = generate_low_level_plan(current_task, dependency_results)

        if not actions:
            error_msg = f"Task {current_task.task_id}의 Low-level 계획 생성 실패"
            print(f"\n[X]  {error_msg}")
            return {
                **state,
                "plan": [],
                "error": error_msg
            }

        low_level_time = time.time() - low_level_start

        print(f"\n✓ Low-level 계획 생성 완료: {len(actions)}단계 ({low_level_time:.2f}초)")
        for idx, action in enumerate(actions, 1):
            print(f"  {idx}. {action.tool}.{action.operation} - {action.reason}")

        timing = state.get("timing", {"high_level_planning": 0.0, "tasks": {}})
        task_id = current_task.task_id
        if task_id in timing.get("tasks", {}):
            timing["tasks"][task_id]["low_level_planning"] = low_level_time

        return {
            **state,
            "plan": [a.to_dict() for a in actions],
            "current_step": 0,
            "results": [],
            "timing": timing
        }

    except Exception as e:
        error_msg = f"Low-level 계획 생성 중 오류: {str(e)}"
        print(f"\n[X] {error_msg}")
        import traceback
        traceback.print_exc()

        return {
            **state,
            "plan": [],
            "error": error_msg
        }


def node_execute_two_stage(state: Dict[str, Any]) -> Dict[str, Any]:
    """Low-level Action 실행 (Two-Stage 모드용)

    현재 단계의 Action 실행

    Args:
        state: 현재 상태
            - plan: Low-level Action 리스트
            - current_step: 현재 실행 단계
            - results: 이전 실행 결과
            - completed_tasks: 완료된 Task 리스트 (의존성 결과용)
            - current_task: 현재 실행 중인 Task

    Returns:
        Dict[str, Any]: 업데이트된 상태
            - results: 실행 결과 추가
            - current_step: 다음 단계로 증가
    """
    import time
    from .schemas.actions import Action
    from .placeholder_resolver import PlaceholderResolver
    from .schemas.task import HighLevelTask

    current_step = state["current_step"]
    plan = state["plan"]
    results = state.get("results", [])

    if current_step >= len(plan):
        return state

    exec_start = None
    current_task_dict = state.get("current_task")
    if current_task_dict and current_step == 0:
        exec_start = time.time()

    print(f"\n[Executing] Action {current_step + 1}/{len(plan)}")

    action_dict = plan[current_step]
    params = action_dict.get("params", {})

    all_results = list(results)  

    current_task_dict = state.get("current_task")
    if current_task_dict:
        current_task = HighLevelTask.from_dict(current_task_dict)
        if current_task.dependencies:
            completed_tasks = state.get("completed_tasks", [])
            for completed_task_dict in completed_tasks:
                task_id = completed_task_dict.get("task_id")
                if task_id in current_task.dependencies:
                    dependency_task_results = completed_task_dict.get("execution_results", [])
                    all_results.extend(dependency_task_results)

    params = PlaceholderResolver.resolve(params, all_results)

    action = Action(
        tool=action_dict["tool"],
        operation=action_dict["operation"],
        params=params,
        reason=action_dict.get("reason", ""),
        timeout_seconds=action_dict.get("timeout_seconds", 300)
    )

    result = execute_action(action, job_id=state.get("job_id"))
    results.append(result.to_dict())

    timing = state.get("timing", {"high_level_planning": 0.0, "tasks": {}})
    if exec_start is not None and current_task_dict:
        current_task = HighLevelTask.from_dict(current_task_dict)
        task_id = current_task.task_id
        if task_id in timing.get("tasks", {}):
            timing["tasks"][task_id]["exec_start"] = exec_start

    return {
        **state,
        "results": results,
        "current_step": current_step + 1,
        "timing": timing
    }


def node_task_complete(state: Dict[str, Any]) -> Dict[str, Any]:
    """Task 완료 처리

    현재 Task의 실행 결과를 저장하고 TaskQueue 업데이트

    Args:
        state: 현재 상태

    Returns:
        Dict[str, Any]: 업데이트된 상태
            - completed_tasks: 완료된 Task 추가
            - task_queue_state: 업데이트
    """
    import time
    from .schemas.task import HighLevelTask, TaskStatus

    current_task_dict = state.get("current_task")
    if not current_task_dict:
        return state

    current_task = HighLevelTask.from_dict(current_task_dict)
    results = state.get("results", [])

    current_task.status = TaskStatus.COMPLETED
    current_task.execution_results = results
    current_task.low_level_plan = state.get("plan", [])

    timing = state.get("timing", {"high_level_planning": 0.0, "tasks": {}})
    task_id = current_task.task_id
    if task_id in timing.get("tasks", {}):
        task_timing = timing["tasks"][task_id]
        start_time = task_timing.get("start_time", 0)
        exec_start = task_timing.get("exec_start", 0)

        if exec_start > 0:
            task_timing["execution"] = time.time() - exec_start

        if start_time > 0:
            task_timing["total"] = time.time() - start_time

        task_timing.pop("start_time", None)
        task_timing.pop("exec_start", None)

    completed_tasks = state.get("completed_tasks", [])
    completed_tasks.append(current_task.to_dict())

    task_queue_state = state.get("task_queue_state", {})
    all_tasks_dict = task_queue_state.get("all_tasks", {})
    all_tasks_dict[current_task.task_id] = current_task.to_dict()

    completed_ids = set(task_queue_state.get("completed_ids", []))
    completed_ids.add(current_task.task_id)

    print(f"\n✓ Task {current_task.task_id} 완료")
    print(f"  - 실행 결과: {len(results)}개")
    if task_id in timing.get("tasks", {}):
        task_timing = timing["tasks"][task_id]
        print(f"  - 소요 시간: {task_timing.get('total', 0):.2f}초")

    return {
        **state,
        "completed_tasks": completed_tasks,
        "task_queue_state": {
            "all_tasks": all_tasks_dict,
            "completed_ids": list(completed_ids)
        },
        "current_task": None,
        "timing": timing
    }


def node_finish_two_stage(state: Dict[str, Any]) -> Dict[str, Any]:
    """모든 Task 완료 (Two-Stage 모드용)

    Args:
        state: 현재 상태

    Returns:
        Dict[str, Any]: 업데이트된 상태
            - completed: True
    """
    print("\n" + "="*60)
    print("[완료] 모든 Task 실행 완료")
    print("="*60)

    completed_tasks = state.get("completed_tasks", [])
    print(f"\n총 {len(completed_tasks)}개 Task 완료:")
    for task_dict in completed_tasks:
        print(f"  - [{task_dict['task_id']}] {task_dict['description']}")

    return {
        **state,
        "completed": True
    }


def should_get_next_task(state: Dict[str, Any]) -> str:
    """다음 Task가 있는지 확인

    Args:
        state: 현재 상태

    Returns:
        str: "plan" (다음 Task 있음) 또는 "finish" (없음)
    """
    current_task = state.get("current_task")

    if current_task is None:
        return "finish"
    else:
        return "plan"


def should_continue_execute(state: Dict[str, Any]) -> str:
    """Action 실행 계속 여부 확인

    Args:
        state: 현재 상태

    Returns:
        str: "continue" (다음 Action 있음) 또는 "task_complete" (완료)
    """
    if state.get("error"):
        return "task_complete"

    current_step = state["current_step"]
    plan = state["plan"]

    if current_step < len(plan):
        return "continue"
    else:
        return "task_complete"

