"""결과 및 리포트 스키마 모듈

작업 요약(JobSummary)과 리포트 데이터(ReportData) 구조 정의
"""
from __future__ import annotations
from typing import Dict, Any, List
from dataclasses import dataclass, field

@dataclass

class JobSummary:
    """작업 요약"""
    job_id: str
    user_prompt: str
    ok: bool
    total_steps: int
    success_count: int
    fail_count: int
    execution_time_seconds: float

    def to_dict(self) -> Dict[str, Any]:

        return {
            "job_id": self.job_id,
            "user_prompt": self.user_prompt,
            "ok": self.ok,
            "total_steps": self.total_steps,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "execution_time_seconds": self.execution_time_seconds
        }

@dataclass

class ReportData:
    """리포트 데이터"""
    job_id: str
    summary: JobSummary
    state: Dict[str, Any]
    saved_files: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:

        return {
            "job_id": self.job_id,
            "summary": self.summary.to_dict(),
            "state": self.state,
            "saved_files": self.saved_files
        }

