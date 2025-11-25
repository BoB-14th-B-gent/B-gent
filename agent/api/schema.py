from pydantic import BaseModel
from typing import List, Optional


class AgentExecuteRequest(BaseModel):
    conversation_id: str
    stage_id: int
    trigger_id: str
    prompt: str
    unprocessed_filename: List[str]


class AgentExecuteResponse(BaseModel):
    ok: bool
