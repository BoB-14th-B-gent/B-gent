from fastapi import APIRouter, BackgroundTasks, WebSocket, WebSocketDisconnect, HTTPException
from typing import Dict
from .schema import AgentExecuteRequest, AgentExecuteResponse, AgentState
from .service import execute_agent_sync, get_agent_state_from_db

router = APIRouter()
active_connections: Dict[str, WebSocket] = {}

@router.post("", response_model=AgentExecuteResponse, summary="Agent 실행")
async def execute_agent(body: AgentExecuteRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(execute_agent_sync, body.trigger_id)
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

@router.get("/state/{trigger_id}", response_model=AgentState)
async def get_agent_state(trigger_id: str):
    doc = get_agent_state_from_db(trigger_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Agent state not found")

    return AgentState(
        trigger_id=str(doc.get("trigger_id", trigger_id)),
        conversation_id=doc.get("conversation_id"),
        stage_id=doc.get("stage_id"),
        status=doc.get("status", "unknown"),
        plan=doc.get("plan") or [],
        updated_at=str(doc.get("updated_at")) if doc.get("updated_at") else None,
    )