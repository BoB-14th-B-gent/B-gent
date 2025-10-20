"""메인 라우터 (오케스트레이터) 모듈

작업 흐름을 관리하고 LangGraph 워크플로우를 실행
"""
from __future__ import annotations
import time
import uuid
from typing import Dict, Any, Optional, List
from .graph import create_workflow
from .storage.mongo import save_job, save_result
from .reporter import generate_report
from .schemas.results import JobSummary

def run_job(
    user_prompt: str,
    file_paths: Optional[List[str]] = None,
    file_meta: Optional[Dict[str, Any]] = None,
    generate_report_flag: bool = False,
    report_dir: str = "./data/reports"
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
        file_meta: 파일 메타데이터 (선택)
        generate_report_flag: 리포트 생성 여부 (기본값: False)
        report_dir: 리포트 저장 디렉터리 (기본값: ./data/reports)

    Returns:
        Dict[str, Any]: 작업 결과
            - job_id: 작업 ID
            - summary: 작업 요약 (성공/실패, 실행 시간 등)
            - state: 최종 상태 (계획, 결과 등)
            - report: 리포트 데이터 (generate_report_flag=True인 경우)

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
    print("=" * 80)
    print(f"🚀 B-gent 작업 시작")
    print(f"   Job ID: {job_id}")
    print(f"   요청: {user_prompt}")

    if file_paths:
        print(f"   파일: {', '.join(file_paths)}")
    print("=" * 80)
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
    save_job(job_id, initial_state)

    try:
        workflow = create_workflow()
        final_state = workflow.invoke(initial_state)
        execution_time = time.time() - start_time
        results = final_state.get("results", [])
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
        save_result(job_id, final_state)
        report_data = None

        if generate_report_flag:
            report_data = generate_report(final_state, report_dir)
        result = {
            "job_id": job_id,
            "summary": summary.to_dict(),
            "state": final_state
        }

        if report_data:
            result["report"] = report_data.to_dict()
        print("\n" + "=" * 80)
        print(f"   작업 완료 (Job ID: {job_id})")
        print(f"   실행 시간: {execution_time:.2f}초")
        print(f"   성공/실패: {success_count}/{fail_count}")
        print("=" * 80)

        return result

    except Exception as e:
        execution_time = time.time() - start_time
        error_msg = str(e)
        print("\n" + "=" * 80)
        print(f"   작업 실패 (Job ID: {job_id})")
        print(f"   오류: {error_msg}")
        print("=" * 80)

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

