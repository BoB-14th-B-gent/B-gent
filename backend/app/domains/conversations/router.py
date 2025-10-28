from fastapi import APIRouter, HTTPException
from app.domains.conversations.schema import ConversationCreateInput, ConversationCreatedOut, ConversationDetailOut
from app.domains.conversations.service import create_conversation_with_input, get_conversation_detail

router = APIRouter()

@router.post("", response_model=ConversationCreatedOut,summary="대화 생성")
def create_conversation_api(body: ConversationCreateInput):
    out = create_conversation_with_input(body.input)
    return ConversationCreatedOut(**out)

@router.get("/{conversation_id}", response_model=ConversationDetailOut, summary="대화 상세 조회")
def get_conversation_api(conversation_id: str):
    d = get_conversation_detail(conversation_id)
    if not d:
        raise HTTPException(status_code=404, detail="conversation not found")
    return d