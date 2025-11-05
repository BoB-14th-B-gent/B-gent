from fastapi import APIRouter, BackgroundTasks
from .schema import AgentExecuteRequest, AgentExecuteResponse
from .service import execute_agent_sync

router = APIRouter()


@router.post("", response_model=AgentExecuteResponse, summary="Agent 실행")
async def execute_agent(body: AgentExecuteRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(
        execute_agent_sync,
        body.conversation_id,
        body.stage_id,
        body.trigger_id,
        body.prompt,
        body.unprocessed_filename
    )

    return AgentExecuteResponse(ok=True)
