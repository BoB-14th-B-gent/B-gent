from fastapi import APIRouter

router = APIRouter()

@router.post("/{conversation_id}/messages", summary="메시지 저장")
def add_message():
    return

@router.get("/{conversation_id}/messages", summary="메시지 전체 조회")
def get_all_messages():
    return

@router.get("/{conversation_id}/messages/{message_id}", summary="개별 메시지 조회")
def get_single_message():
    return