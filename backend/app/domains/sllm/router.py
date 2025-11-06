from fastapi import APIRouter, HTTPException
from .schema import TriggerAnalyzeIn, TriggerAnalyzeOut
from .service import request_report_creation

router = APIRouter()

@router.post("/reports", response_model=TriggerAnalyzeOut, summary="sLLM에 report 생성 요청")
async def create_report_by_trigger(body: TriggerAnalyzeIn):
    try:
        rid = await request_report_creation(body.trigger_id)
        return {"ok": True, "report_id": rid}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))