"""스키마 정의 모듈

B-gent 에이전트의 데이터 구조 정의
"""
from .actions import Action, ActionResult
from .common import JobState
from .results import JobSummary, ReportData
__all__ = ["Action", "ActionResult", "JobState", "JobSummary", "ReportData"]

