from pydantic import BaseModel
from typing import Any, Dict, List, Optional

class AgentExecuteRequest(BaseModel):
    trigger_id: str
    
class AgentExecuteResponse(BaseModel):
    ok: bool

class AgentState(BaseModel):
    trigger_id: str
    conversation_id: Optional[str] = None
    stage_id: Optional[int] = None
    status: str
    plan: List[Dict[str, Any]] = []
    updated_at: Optional[str] = None