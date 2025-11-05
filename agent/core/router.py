"""메인 라우터 (오케스트레이터) 모듈

하이브리드 워크플로우 실행:
- High-level Planning: LLM이 추상적 Task 생성
- ReAct Execution: 각 Task를 ReAct Agent가 동적으로 실행
"""
from __future__ import annotations
import time
import uuid
from typing import Dict, Any, Optional, List, Literal
from .graph import create_workflow
from ..storage.job_storage import save_agent_state, update_agent_status
from ..schemas.results import JobSummary

WORKFLOW_MODE: Literal["two_stage"] = "two_stage"

def run_job(
    user_prompt: str,
    file_paths: Optional[List[str]] = None,
    file_meta: Optional[Dict[str, Any]] = None,
    generate_report_flag: bool = False,
    report_dir: str = "./data/reports",
    conversation_id: Optional[str] = None,
    trigger_id: Optional[str] = None,
    stage_id: Optional[int] = None
) -> Dict[str, Any]:
    """작업 실행 메인 진입점

    사용자 요청을 받아 LangGraph 워크플로우를 실행하고 결과 반환

    로직:
        1. Job ID 생성 (uuid)
        2. 초기 상태 생성 및 MongoDB 저장
        3. LangGraph 워크플로우 실행 (plan → execute → finish)
        4. 실행 시간 및 요약 생성
        5. MongoDB에 결과 저장
        6. 리포트 생성 (옵션)
        7. 결과 반환

    Args:
        user_prompt: 사용자 요청 (예: "지난 24시간 IIS에서 cmd.exe 스폰 탐지")
        file_paths: 파일 경로 배열 (디스크 이미지 등, 선택)
        file_meta: 파일 ��타데이터 (선택)
        generate_report_flag: 리포트 생성 여부 (기본값: False)
        report_dir: 리포트 저장 디렉터리 (기본값: ./data/reports)

    Returns:
        Dict[str, Any]: 작업 결과
            - job_id: 작업 ID
            - summary: 작업 요약 (성공/실패, 실행 시간 등)
            - state: 최신 상태 (계획, 결과 등)
            - report: 리포트 데이터 (generate_report_flag=True 경우)

    Example:
        >>> result = run_job(
        ...     user_prompt="인덱스 목록 조회",
        ...     generate_report_flag=True
        ... )
        >>> print(result["summary"]["ok"])
        True
    """
    job_id = uuid.uuid4().hex[:24]
    start_time = time.time()
    file_paths = file_paths or []
        
    if WORKFLOW_MODE == "two_stage":
        initial_state = {
            "job_id": job_id,
            "user_prompt": user_prompt,
            "file_paths": file_paths,
            "file_meta": file_meta or {},
            "high_level_tasks": [],
            "task_queue_state": {},
            "current_task": None,
            "completed_tasks": [],
            "plan": [],
            "results": [],
            "current_step": 0,
            "timing": {
                "high_level_planning": 0.0,
                "tasks": {}
            },
            "completed": False,
            "error": None
        }
    else:
        initial_state = {
            "job_id": job_id,
            "user_prompt": user_prompt,
            "file_paths": file_paths,
            "file_meta": file_meta or {},
            "plan": [],
            "results": [],
            "current_step": 0,
            "completed": False,
            "error": None
        }

    save_agent_state(
        agent_id=job_id,
        stage_id=stage_id if stage_id is not None else 0,
        plan=[],
        status="running",
        mcp_tools=[],
        conversation_id=conversation_id,
        trigger_id=trigger_id,
        additional_data=initial_state
    )

    try:
        workflow = create_workflow(mode=WORKFLOW_MODE)
        final_state = workflow.invoke(initial_state, config={"recursion_limit": 50})
        execution_time = time.time() - start_time

        completed_tasks = final_state.get("completed_tasks", [])
        all_results = []
        for task in completed_tasks:
            task_results = task.get("execution_results", [])
            all_results.extend(task_results)

        results = all_results

        total_steps = len(results)
        success_count = sum(1 for r in results if r.get("success"))
        fail_count = total_steps - success_count
        summary = JobSummary(
            job_id=job_id,
            user_prompt=user_prompt,
            ok=fail_count == 0,
            total_steps=total_steps,
            success_count=success_count,
            fail_count=fail_count,
            execution_time_seconds=execution_time
        )

        save_agent_state(
            agent_id=job_id,
            status="completed" if fail_count == 0 else "failed",
            additional_data={
                "result": final_state,
                "summary": summary.to_dict(),
                "execution_time_seconds": execution_time
            }
        )

        result = {
            "job_id": job_id,
            "summary": summary.to_dict(),
            "state": final_state
        }

        print(f"\n[Summary]")
        print(f"Total: {len(completed_tasks)} tasks, {total_steps} actions, {execution_time:.2f}s")
        if fail_count > 0:
            print(f"Status: {success_count} succeeded, {fail_count} failed")

        return result

    except Exception as e:
        execution_time = time.time() - start_time
        error_msg = str(e)

        if "recursion limit" in error_msg.lower() or "GRAPH_RECURSION_LIMIT" in error_msg:
            completed_tasks = initial_state.get("completed_tasks", [])
            all_results = []
            for task in completed_tasks:
                task_results = task.get("execution_results", [])
                all_results.extend(task_results)

            total_steps = len(all_results)
            success_count = sum(1 for r in all_results if r.get("success"))
            fail_count = total_steps - success_count

            summary = JobSummary(
                job_id=job_id,
                user_prompt=user_prompt,
                ok=True,
                total_steps=total_steps,
                success_count=success_count,
                fail_count=fail_count,
                execution_time_seconds=execution_time
            )

            save_agent_state(
                agent_id=job_id,
                status="completed",
                additional_data={
                    "summary": summary.to_dict(),
                    "execution_time_seconds": execution_time,
                    "note": "Stopped at iteration limit"
                }
            )

            print(f"\n[Summary]")
            print(f"Total: {len(completed_tasks)} tasks, {total_steps} actions, {execution_time:.2f}s")

            return {
                "job_id": job_id,
                "summary": summary.to_dict(),
                "state": initial_state
            }

        print(f"\n[✗] Error: {error_msg}")

        save_agent_state(
            agent_id=job_id,
            status="failed",
            additional_data={
                "error": error_msg,
                "execution_time_seconds": execution_time
            }
        )

        return {
            "job_id": job_id,
            "summary": {
                "job_id": job_id,
                "user_prompt": user_prompt,
                "ok": False,
                "total_steps": 0,
                "success_count": 0,
                "fail_count": 1,
                "execution_time_seconds": execution_time
            },
            "error": error_msg
        }

