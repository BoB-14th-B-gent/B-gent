from fastapi import APIRouter, HTTPException, Query
from .schema import ReportIdOut, ReportDetailOut, ReportListOut
from .service import get_report_detail, list_reports

router = APIRouter()

@router.get("/{report_id}", response_model=ReportDetailOut, summary="리포트 조회(report_id 기준)")
def get_report_by_id(report_id: str):
    d = get_report_detail(report_id)
    if not d:
        raise HTTPException(status_code=404, detail="report not found")
    return d


@router.get("", response_model=ReportListOut, summary="리포트 조회(conversation_id 기준)")
def get_report_by_conversation_id(
    conversation_id: str | None = None,
    stage_id: int | None = None,
    limit: int = Query(50, ge=1, le=200)
):
    try:
        return list_reports(conversation_id, stage_id, limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))