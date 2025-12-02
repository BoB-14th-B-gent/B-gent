from fastapi import APIRouter, HTTPException

from app.domains.cases.schema import CaseCreateInput, CaseCreatedOut, CaseDetailOut, CaseListOut, CaseConversationListOut
from app.domains.cases.service import create_case, get_case_detail, list_cases, create_case_conversation, list_case_conversations, get_case_conversation_detail

from app.domains.conversations.schema import ConversationCreateInput, ConversationCreatedOut, ConversationDetailOut

router = APIRouter()

@router.post("", response_model=CaseCreatedOut, response_model_by_alias=True, summary="케이스 생성")
def create_case_route(body: CaseCreateInput):
    out = create_case(body.name, body.description, body.analyst)
    return CaseCreatedOut.model_validate(out)

@router.get("", response_model=CaseListOut, summary="케이스 목록 조회")
def list_all_cases():
    items = list_cases()
    return {"items": items}

@router.get("/{case_id}", response_model=CaseDetailOut, summary="케이스 상세 조회")
def get_case_route(case_id: str):
    d = get_case_detail(case_id)
    if not d:
        raise HTTPException(status_code=404, detail="case not found")
    return d

@router.post("/{case_id}/conversations", response_model=ConversationCreatedOut, response_model_by_alias=True, summary="케이스 별 대화 생성")
def create_case_conversation_route(case_id: str, body: ConversationCreateInput):
    try:
        out = create_case_conversation(case_id, body.input)
    except ValueError as e:
        msg = str(e)
        if msg == "case not found":
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=400, detail=msg)

    return ConversationCreatedOut.model_validate(out)

@router.get("/{case_id}/conversations", response_model=CaseConversationListOut, summary="케이스 별 대화 목록 조회")
def list_case_conversations_route(case_id: str):
    try:
        out = list_case_conversations(case_id)
        return out
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{case_id}/conversations/{conversation_id}", response_model=ConversationDetailOut, summary="케이스 내 특정 대화 상세 조회")
def get_case_conversation_route(case_id: str, conversation_id: str):
    d = get_case_conversation_detail(case_id, conversation_id)
    if not d:
        raise HTTPException(status_code=404, detail="conversation not found in this case")
    return d