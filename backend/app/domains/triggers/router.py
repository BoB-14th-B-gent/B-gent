from fastapi import APIRouter

router = APIRouter()

@router.post("", summary="트리거 생성")
def create_trigger():
    return

@router.get("/{trigger_id}", summary="트리거 조회")
def get_trigger():
    return

@router.patch("/{trigger_id}/prompt", summary="트리거에 prompt 추가")
def add_prompt():
    return

@router.patch("/{trigger_id}/evidences", rsummary="트리거에 evidences 추가")
def add_evidences():
    return

@router.patch("/{trigger_id}/report", summary="트리거에 report 추가")
def add_report():
    return