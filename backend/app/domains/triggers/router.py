from fastapi import APIRouter, HTTPException
from .schema import TriggerCreate, TriggerIdOut, TriggerDetailOut, TriggerPatchPrompt, TriggerPatchEvidences, TriggerPatchReport
from .service import create_trigger_with_conversation_id, get_trigger_with_trigger_id, add_prompt_to_trigger, add_evidences_to_trigger, add_report_to_trigger

router = APIRouter()

@router.post("", response_model=TriggerIdOut, summary="트리거 생성")
def create_trigger(body: TriggerCreate):
    try:
        return create_trigger_with_conversation_id(body.conversation_id, body.stage_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{trigger_id}", response_model=TriggerDetailOut, summary="트리거 조회")
def get_trigger(trigger_id: str):
    d = get_trigger_with_trigger_id(trigger_id)
    if not d:
        raise HTTPException(status_code=404, detail="trigger not found")
    return d

@router.patch("/{trigger_id}/prompt", response_model=TriggerDetailOut, summary="트리거에 prompt 추가")
def add_prompt(trigger_id: str, body: TriggerPatchPrompt):
    try:
        return add_prompt_to_trigger(trigger_id, body.prompt_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.patch("/{trigger_id}/evidences", response_model=TriggerDetailOut, summary="트리거에 evidences 추가")
def add_evidences(trigger_id: str, body: TriggerPatchEvidences):
    try:
        return add_evidences_to_trigger(trigger_id, [e.model_dump() for e in body.evidences])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.patch("/{trigger_id}/report", response_model=TriggerDetailOut, summary="트리거에 report 추가")
def add_report(trigger_id: str, body: TriggerPatchReport):
    try:
        return add_report_to_trigger(trigger_id, body.report_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))