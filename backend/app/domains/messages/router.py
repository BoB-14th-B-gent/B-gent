from fastapi import APIRouter, HTTPException, Query
from .schema import MessageCreate, MessageIdOut, MessageListOut, MessageDetailOut
from .service import create_message, list_messages, get_message_detail

router = APIRouter()

@router.post("/{conversation_id}/messages", response_model=MessageIdOut, summary="메시지 저장")
def add_message(conversation_id: str, body: MessageCreate):
    try:
        _id = create_message(conversation_id, body.model_dump())
        return {"_id": _id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{conversation_id}/messages", response_model=MessageListOut, summary="메시지 전체 조회")
def get_all_messages(conversation_id: str, stage_id: int, limit: int = Query(100, ge=1, le=500)):
    try:
        return list_messages(conversation_id, stage_id=stage_id, limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{conversation_id}/messages/{message_id}", response_model=MessageDetailOut, summary="개별 메시지 조회")
def get_single_message(conversation_id: str, message_id: str):
    d = get_message_detail(conversation_id, message_id)
    if not d:
        raise HTTPException(status_code=404, detail="message not found")
    return d