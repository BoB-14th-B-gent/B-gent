from fastapi import APIRouter, HTTPException
from .schema import UILayoutOut, UILayoutUpsertIn
from .service import get_layout, upsert_layout

router = APIRouter()

@router.get("/{conversation_id}/{stage_id}", response_model=UILayoutOut, summary="UI 레이아웃 조회")
def get_ui_layout(conversation_id: str, stage_id: int):
    try:
        layout = get_layout(conversation_id, stage_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not layout:
        raise HTTPException(status_code=404, detail="ui layout not found")
    return layout

@router.put("/{conversation_id}/{stage_id}", response_model=UILayoutOut, summary="UI 레이아웃 저장 및 업데이트")
def put_ui_layout(conversation_id: str, stage_id: int, body: UILayoutUpsertIn):
    try:
        layout = upsert_layout(conversation_id, stage_id, body)
        return layout
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))