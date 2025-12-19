from fastapi import APIRouter
from .service import run_pipeline_prepare_service, run_after_agent_and_create_report, run_pipeline_full_service
from .schema import RunPipelineReq, PipelinePrepareResult, PipelineFullResult, RunAfterAgentReq

router = APIRouter()

@router.post("/run", response_model=PipelinePrepareResult, summary="Agent 실행까지 진행되는 파이프라인")
async def run_pipeline(body: RunPipelineReq):
    result = await run_pipeline_prepare_service(
        input_text=body.input,
        stage_id=body.stage_id,
        inline_threshold=body.inline_threshold,
        mode=body.mode,
        conversation_id=body.conversation_id,
        case_id=body.case_id,
    )
    return PipelinePrepareResult(**result)

@router.post("/run/after-agent", response_model=PipelineFullResult, summary="Agent 완료 후 보고서 생성 파이프라인")
async def run_after_agent(body: RunAfterAgentReq):
    result = await run_after_agent_and_create_report(trigger_id=body.trigger_id)
    return PipelineFullResult(**result)

@router.post("/run/full", response_model=PipelineFullResult, summary="통합 실행 파이프라인 (Agent + MCP + sLLM 보고서까지)")
async def run_pipeline_full(body: RunPipelineReq):
    result = await run_pipeline_full_service(
        input_text=body.input,
        stage_id=body.stage_id,
        inline_threshold=body.inline_threshold,
        mode=body.mode,
        conversation_id=body.conversation_id,
        case_id=body.case_id,
    )
    return PipelineFullResult(**result)