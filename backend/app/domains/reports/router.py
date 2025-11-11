from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from .schema import ReportDetailOut, ReportListOut
from .service import get_report_detail, list_reports, parse_and_save_structured

router = APIRouter()

@router.get("/{report_id}", response_model=ReportDetailOut, summary="report_id로 report 조회")
def get_report_by_id(report_id: str):
    d = get_report_detail(report_id)
    if not d:
        raise HTTPException(404, "report not found")
    return d

@router.get("", response_model=ReportListOut, summary="conversation_id로 report 조회")
def get_report_by_conversation_id(
    conversation_id: str | None = None,
    stage_id: int | None = None,
    limit: int = Query(50, ge=1, le=200),
):
    try:
        return list_reports(conversation_id, stage_id, limit)
    except ValueError as e:
        raise HTTPException(400, str(e))

class PatchStructuredBody(BaseModel):
    text_override: str | None = None

@router.patch("/{report_id}/structured", summary="구조화된 report 저장")
def patch_report_structured(report_id: str, body: PatchStructuredBody):
    try:
        out = parse_and_save_structured(report_id, body.text_override)
        return {"ok": True, "report_id": out["report_id"], "structured": out["structured"]}
    except ValueError as e:
        raise HTTPException(400, str(e))