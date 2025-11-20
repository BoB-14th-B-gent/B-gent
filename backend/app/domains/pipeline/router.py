from fastapi import APIRouter
from .service import run_pipeline_service
from .schema import RunPipelineReq, PipelineResult

router = APIRouter()

@router.post("/run", response_model=PipelineResult, summary="통합 실행 파이프라인")
async def run_pipeline(body: RunPipelineReq):
    result = await run_pipeline_service(
        input_text=body.input,
        stage_id=body.stage_id,
        inline_threshold=body.inline_threshold,
        mode=body.mode,
        conversation_id=body.conversation_id,
    )
    return PipelineResult(**result)