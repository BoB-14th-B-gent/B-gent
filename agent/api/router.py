from fastapi import APIRouter, BackgroundTasks, WebSocket, WebSocketDisconnect
from typing import Dict
from .schema import AgentExecuteRequest, AgentExecuteResponse
from .service import execute_agent_sync

router = APIRouter()

active_connections: Dict[str, WebSocket] = {}

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


@router.websocket("/ws/{trigger_id}")
async def agent_websocket(websocket: WebSocket, trigger_id: str):
    await websocket.accept()

    active_connections[trigger_id] = websocket
    print(f"WebSocket connected for trigger: {trigger_id}")

    try:
        while True:
            data = await websocket.receive_text()

    except WebSocketDisconnect:
        active_connections.pop(trigger_id, None)
        print(f"WebSocket disconnected for trigger: {trigger_id}")


async def send_log_to_client(trigger_id: str, log_message: str):
    if trigger_id in active_connections:
        try:
            await active_connections[trigger_id].send_text(log_message)
        except Exception as e:
            print(f"Error sending log to trigger {trigger_id}: {e}")
            active_connections.pop(trigger_id, None)
