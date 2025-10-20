"""LangGraph 워크플로우 정의 모듈

계획 생성 → 실행 → 완료 워크플로우를 LangGraph로 정의
"""
from __future__ import annotations
from typing import Dict, Any
from langgraph.graph import StateGraph, END
from .schemas.common import AgentState
from .planner import generate_plan
from .executor import execute_action

def create_workflow() -> StateGraph:
    """LangGraph 워크플로우 생성

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

    Example:
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
            print(f"\n⚠️  {error_msg}\n")

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
        print(f"\n❌ {error_msg}\n")
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
        timeout_seconds=action_dict.get("timeout_seconds", 60)
    )
    result = execute_action(action)
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

