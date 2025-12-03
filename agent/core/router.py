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
from ..storage.job_storage import (
    save_agent_state, update_agent_status, is_first_execution_in_conversation,
    get_available_resources, update_agent_resources
)
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
    import sys
    job_id = uuid.uuid4().hex[:24]
    start_time = time.time()
    file_paths = file_paths or []

    sys.stderr.write(f"\n[DEBUG router.run_job] conversation_id={conversation_id}, stage_id={stage_id}, trigger_id={trigger_id}\n")
    sys.stderr.write(f"[DEBUG router.run_job] file_paths (input)={file_paths}\n")

    # 해당 conversation에서 첫 번째 실행인지 확인
    is_first_execution = is_first_execution_in_conversation(conversation_id)
    sys.stderr.write(f"[DEBUG router.run_job] is_first_execution_from_db={is_first_execution}\n")

    # file_paths가 비어있으면 이전 Stage의 리소스에서 자동 로드 (AGENT_STATES에서 조회)
    previous_context = None  # 현재 사용하지 않음
    if conversation_id:
        if not file_paths:
            available_resources = get_available_resources(conversation_id)
            disk_images = available_resources.get("disk_images", [])
            if disk_images:
                file_paths = disk_images
                is_first_execution = False  # 리소스가 있으면 첫 실행이 아님
                sys.stderr.write(f"[DEBUG router.run_job] file_paths auto-loaded from AGENT_STATES: {file_paths}\n")

    # stage_id가 명시적으로 2 이상이면 첫 실행이 아님
    if stage_id is not None and stage_id > 1:
        is_first_execution = False
        sys.stderr.write(f"[DEBUG router.run_job] is_first_execution overridden to False (stage_id={stage_id})\n")

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
            "error": None,
            "is_first_execution": is_first_execution,  # 첫 실행 여부 플래그
            "previous_context": previous_context,  # 이전 Stage AI 분석 결과
            "ioc_analysis_results": [],  # 현재 Stage IoC 분석 결과
            "conversation_id": conversation_id,  # conversation_id 전달
            "stage_id": stage_id if stage_id is not None else 1  # Stage ID 추가
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

    # 초기 상태 저장 (plan 수립 전)
    save_agent_state(
        agent_id=job_id,
        stage_id=stage_id if stage_id is not None else 0,
        plan=[],
        status="running",
        mcp_tools=[],  # 초기에는 비워둠
        conversation_id=conversation_id,
        trigger_id=trigger_id
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

        update_agent_status(
            agent_id=job_id,
            status="done" if fail_count == 0 else "failed"
        )

        # Stage 완료 시 available_resources 저장 (AGENT_STATES)
        _save_available_resources_on_complete(
            final_state=final_state,
            file_paths=file_paths
        )

        result = {
            "job_id": job_id,
            "summary": summary.to_dict(),
            "state": final_state
        }

        # print(f"\n[Summary]")
        # print(f"Total: {len(completed_tasks)} tasks, {total_steps} actions, {execution_time:.2f}s")
        if fail_count > 0:
            # print(f"Status: {success_count} succeeded, {fail_count} failed")
            pass

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

            update_agent_status(
                agent_id=job_id,
                status="done"
            )

            # print(f"\n[Summary]")
            # print(f"Total: {len(completed_tasks)} tasks, {total_steps} actions, {execution_time:.2f}s")

            return {
                "job_id": job_id,
                "summary": summary.to_dict(),
                "state": initial_state
            }

        # print(f"\n[✗] Error: {error_msg}")

        save_agent_state(
            agent_id=job_id,
            status="failed"
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


def _save_available_resources_on_complete(
    final_state: Dict[str, Any],
    file_paths: Optional[List[str]] = None
) -> None:
    """Stage 완료 시 available_resources를 AGENT_STATES에 저장

    Args:
        final_state: 최종 상태 (job_id 포함)
        file_paths: 이 Stage에서 사용된 파일 경로 목록
    """
    try:
        job_id = final_state.get("job_id")
        if not job_id:
            return

        # available_resources 구성
        available_resources = {
            "disk_images": [],
            "extracted_files": []
        }

        # 디스크 이미지 파일 경로 저장 (E01, raw, dd 등)
        if file_paths:
            disk_image_extensions = {'.e01', '.raw', '.dd', '.img', '.vmdk', '.vhd', '.vhdx'}
            for path in file_paths:
                if any(path.lower().endswith(ext) for ext in disk_image_extensions):
                    available_resources["disk_images"].append(path)

        # AGENT_STATES에 저장
        if available_resources["disk_images"] or available_resources["extracted_files"]:
            update_agent_resources(job_id, available_resources)

    except Exception as e:
        import sys
        sys.stderr.write(f"[Router] 리소스 저장 실패: {e}\n")

