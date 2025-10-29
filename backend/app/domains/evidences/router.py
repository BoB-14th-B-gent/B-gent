from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from .schema import EvidenceFromConversationIn, EvidenceCreatedOut, EvidenceListOut, EvidenceInputDetail
from .service import create_evidences_from_latest_message, list_input_evidences, get_input_evidence_detail, preview_input_evidence

router = APIRouter()

@router.post("/input", response_model=EvidenceCreatedOut, summary="사용자 프롬프트 내용에서 전처리기 증거 추출 및 변환 후 저장")
def create_from_conversation(body: EvidenceFromConversationIn):
    try:
        res = create_evidences_from_latest_message(conversation_id=body.conversation_id, inline_threshold=body.inline_threshold)
        return EvidenceCreatedOut.model_validate(res)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"internal error: {e}")

@router.get("", response_model=EvidenceListOut, summary="전체 증거 목록 조회")
def list_all(conversation_id: Optional[str] = Query(None), stage_id: Optional[int] = Query(None), limit: int = Query(100, ge=1, le=1000)):
    items = list_input_evidences(conversation_id, stage_id, limit)
    return EvidenceListOut(items=items)

@router.get("/input/{evidence_id}", response_model=EvidenceInputDetail, summary="전처리기 증거 상세 조회")
def get_detail(evidence_id: str):
    d = get_input_evidence_detail(evidence_id)
    if not d:
        raise HTTPException(status_code=404, detail="not found")
    return EvidenceInputDetail.model_validate(d)

@router.get("/input/{evidence_id}/preview", summary="전처리기 증거 상세 조회(GridFS 샘플 확인)")
def get_preview(evidence_id: str):
    result = preview_input_evidence(evidence_id)
    if not result:
        raise HTTPException(404, "not found")
    return result