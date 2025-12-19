from typing import List, Literal, Optional, Any, Dict
from datetime import datetime
from pydantic import BaseModel, Field

Status = Literal["initial", "collecting", "ready", "processing", "done"]

class TriggerCreate(BaseModel):
    conversation_id: str
    stage_id: int

class EvidenceRef(BaseModel):
    collection: Literal["INPUT_EVIDENCES", "MCP_EVIDENCES"]
    id: str

class TriggerIdOut(BaseModel):
    trigger_id: str
    status: Status
    created_at: datetime

class TriggerDetailOut(BaseModel):
    _id: str
    conversation_id: str
    stage_id: int
    evidences: List[EvidenceRef]
    prompt_id: Optional[str] = None
    status: Status
    report_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class TriggerListOut(BaseModel):
    conversation_id: str
    items: List[TriggerDetailOut]

class TriggerPatchPrompt(BaseModel):
    prompt_id: str

class TriggerPatchEvidences(BaseModel):
    evidences: List[EvidenceRef]

class TriggerPatchReport(BaseModel):
    report_id: str

class MCPEvidenceItemOut(BaseModel):
    id: str = Field(alias="_id")
    trigger_id: str
    conversation_id: str
    agent_id: Optional[str] = None
    stage_id: int
    mcp_name: str
    tool_name: Optional[str] = None
    success: bool = True
    created_at: Optional[datetime] = None
    request: Dict[str, Any] = {}
    response: Dict[str, Any] = {}

class MCPEvidenceListOut(BaseModel):
    trigger_id: str
    stage_id: int
    mcp_name: str
    items: List[MCPEvidenceItemOut]

class MCPSummaryItemOut(BaseModel):
    mcp_name: str
    total: int
    success: int
    failed: int
    last_at: Optional[datetime] = None

class MCPSummaryOut(BaseModel):
    trigger_id: str
    stage_id: int
    items: List[MCPSummaryItemOut]