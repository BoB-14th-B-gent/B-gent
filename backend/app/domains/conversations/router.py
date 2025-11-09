from fastapi import APIRouter, HTTPException, Query
from app.domains.conversations.schema import ConversationCreateInput, ConversationCreatedOut, ConversationDetailOut
from app.domains.conversations.service import create_conversation_with_input, get_conversation_detail

from app.domains.triggers.service import get_triggers_by_conversation_id
from app.domains.triggers.schema import TriggerListOut


router = APIRouter()

@router.post("", response_model=ConversationCreatedOut, response_model_by_alias=True, summary="대화 생성")
def create_conversation(body: ConversationCreateInput):
    out = create_conversation_with_input(body.input)
    model = ConversationCreatedOut.model_validate(out)
    return model

@router.get("/{conversation_id}", response_model=ConversationDetailOut, summary="대화 상세 조회")
def get_conversation(conversation_id: str):
    d = get_conversation_detail(conversation_id)
    if not d:
        raise HTTPException(status_code=404, detail="conversation not found")
    return d

@router.get("/{conversation_id}/triggers", response_model=TriggerListOut, summary="대화별 트리거 전체 조회")
def get_triggers_with_conversation(
    conversation_id: str,
    stage_id: int = Query(None),
    status: str = Query(None, pattern="^(initial|collecting|ready|processing|done)$"),
    include_evidences: bool = Query(False),
    limit: int = Query(100, ge=1, le=200)
):
    try:
        return get_triggers_by_conversation_id(
            conversation_id=conversation_id,
            stage_id=stage_id,
            status=status,
            include_evidences=include_evidences,
            limit=limit
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))