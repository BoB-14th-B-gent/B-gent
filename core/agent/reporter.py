"""리포트 생성기 모듈

작업 결과를 JSON 및 Markdown 형식으로 리포트 생성
"""
from __future__ import annotations
import json
import os
from datetime import datetime
from typing import Dict, Any
from .schemas.results import JobSummary, ReportData

def generate_report(state: Dict[str, Any], report_dir: str = "./data/reports") -> ReportData:
    """작업 결과 리포트 생성

    JSON과 Markdown 형식으로 리포트 파일을 생성하고 저장

    Args:
        state: 작업 최종 상태 (job_id, results 등 포함)
        report_dir: 리포트 저장 디렉터리 (기본값: ./data/reports)

    Returns:
        ReportData: 생성된 리포트 데이터 (저장된 파일 경로 포함)
    """
    job_id = state["job_id"]
    user_prompt = state["user_prompt"]
    results = state.get("results", [])
    total_steps = len(results)
    success_count = sum(1 for r in results if r.get("success"))
    fail_count = total_steps - success_count
    execution_time = sum(r.get("execution_time_seconds", 0) for r in results)
    summary = JobSummary(
        job_id=job_id,
        user_prompt=user_prompt,
        ok=fail_count == 0,
        total_steps=total_steps,
        success_count=success_count,
        fail_count=fail_count,
        execution_time_seconds=execution_time
    )
    report_data = ReportData(
        job_id=job_id,
        summary=summary,
        state=state
    )
    report_dir = os.path.abspath(report_dir)
    os.makedirs(report_dir, exist_ok=True)
    json_file = os.path.join(report_dir, f"report_{job_id}.json")

    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(report_data.to_dict(), f, indent=2, ensure_ascii=False)
    md_file = os.path.join(report_dir, f"report_{job_id}.md")
    md_content = _generate_markdown(report_data, state)

    with open(md_file, "w", encoding="utf-8") as f:
        f.write(md_content)
    report_data.saved_files = {
        "json_file": json_file,
        "markdown_file": md_file
    }
    print(f"\n📄 리포트 생성 완료:")
    print(f"   - JSON: {json_file}")
    print(f"   - Markdown: {md_file}")

    return report_data

def _generate_markdown(report: ReportData, state: Dict[str, Any]) -> str:
    """Markdown 형식의 리포트 생성

    Args:
        report: 리포트 데이터
        state: 작업 최종 상태

    Returns:
        str: Markdown 형식의 리포트 문자열
    """
    summary = report.summary
    results = state.get("results", [])
    lines = [
        "# B-gent 작업 리포트",
        "",
        f"**생성 시간**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
        f"**작업 ID**: `{summary.job_id}`",
        f"**상태**: {'✅ SUCCESS' if summary.ok else '⚠️ PARTIAL SUCCESS'}",
        "",
        "## 📋 실행 요약",
        "",
        f"**사용자 요청**: {summary.user_prompt}",
        f"**실행 시간**: {summary.execution_time_seconds:.2f}초",
        f"**총 액션 수**: {summary.total_steps}",
        f"**성공**: {summary.success_count} | **실패**: {summary.fail_count}",
        f"**성공률**: {(summary.success_count / summary.total_steps * 100) if summary.total_steps > 0 else 0:.1f}%",
        "",
        "## 🎯 실행 계획",
        ""
    ]
    plan = state.get("plan", [])

    for idx, action in enumerate(plan, 1):
        lines.append(f"### {idx}. {action['tool']}.{action['operation']}")
        lines.append(f"**이유**: {action.get('reason', 'N/A')}")
        lines.append(f"**파라미터**: `{json.dumps(action.get('params', {}), ensure_ascii=False)}`")
        lines.append("")
    lines.extend([
        "## 🔍 실행 결과",
        ""
    ])

    for idx, result in enumerate(results, 1):
        action = result.get("action", {})
        status = "✅ 성공" if result.get("success") else "❌ 실패"
        lines.append(f"### {idx}. {action.get('tool')}.{action.get('operation')} - {status}")
        lines.append(f"**실행 시간**: {result.get('execution_time_seconds', 0):.2f}초")

        if result.get("success"):
            lines.append(f"**결과**:")
            lines.append("```")
            result_content = result.get("result", "N/A")

            try:

                if isinstance(result_content, str) and (result_content.startswith('[') or result_content.startswith('{')):
                    parsed = json.loads(result_content)
                    formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
                    lines.append(formatted)
                else:
                    lines.append(str(result_content))
            except (json.JSONDecodeError, ValueError):
                lines.append(str(result_content))
            lines.append("```")

        else:
            error_msg = result.get('error', 'Unknown error')

            if error_msg == 'Unknown error' and result.get('result'):
                result_content = result.get('result')

                try:

                    if isinstance(result_content, str):
                        parsed = json.loads(result_content)
                        stderr = parsed.get('stderr', '')
                        stdout = parsed.get('stdout', '')

                        if stderr:
                            error_msg = f"stderr: {stderr}"

                        elif stdout:
                            error_msg = f"stdout: {stdout}"

                        else:
                            error_msg = result_content

                except (json.JSONDecodeError, ValueError):
                    error_msg = str(result_content)
            lines.append(f"**오류**: {error_msg}")

            if result.get('result'):
                lines.append(f"**전체 응답**:")
                lines.append("```")
                result_content = result.get("result", "")

                try:

                    if isinstance(result_content, str) and (result_content.startswith('[') or result_content.startswith('{')):
                        parsed = json.loads(result_content)
                        formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
                        lines.append(formatted)

                    else:
                        lines.append(str(result_content))

                except (json.JSONDecodeError, ValueError):
                    lines.append(str(result_content))
                lines.append("```")
        lines.append("")
    lines.extend([
        "---",
        "",
        "*이 리포트는 B-gent에 의해 자동 생성되었습니다.*"
    ])

    return "\n".join(lines)

