from fastapi import APIRouter, HTTPException

router = APIRouter()

@router.post("", summary="대화 생성")
def create_conversation_api():
    return

@router.get("/{conversation_id}", summary="대화 상세 조회")
def get_conversation_api():
    return 