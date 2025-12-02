from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from .schema import ReportDetailOut, ReportListOut
from .service import get_report_detail, get_latest_report_detail, parse_and_save_structured, list_reports_by_conversation_stage

router = APIRouter()

@router.get("", response_model=ReportListOut, summary="report 목록 조회")
def list_reports(conversation_id: str | None = Query(default=None), stage_id: int | None = Query(default=None)):
    try:
        return list_reports_by_conversation_stage(conversation_id, stage_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/latest", response_model=ReportDetailOut, summary="가장 최신 report 조회")
def get_latest_report():
    try:
        d = get_latest_report_detail()
        if not d:
            raise HTTPException(404, "no report")
        return d
    except RuntimeError as e:
        if str(e) == "db_unavailable":
            raise HTTPException(503, "database unavailable")
        raise
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.get("/{report_id}", response_model=ReportDetailOut, summary="report_id로 report 조회")
def get_report_by_id(report_id: str):
    d = get_report_detail(report_id)
    if not d:
        raise HTTPException(404, "report not found")
    return d

class PatchStructuredBody(BaseModel):
    text_override: str | None = None

@router.patch("/{report_id}/structured", summary="구조화된 report 저장")
def patch_report_structured(report_id: str, body: PatchStructuredBody):
    try:
        out = parse_and_save_structured(report_id, body.text_override)
        return {"ok": True, "report_id": out["report_id"], "structured": out["structured"]}
    except ValueError as e:
        raise HTTPException(400, str(e))