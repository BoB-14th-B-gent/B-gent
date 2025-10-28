from typing import List, Literal, Optional
from datetime import datetime
from pydantic import BaseModel, Field

Status = Literal["initial", "collecting", "ready", "processing", "done"]

class TriggerCreate(BaseModel):
    conversation_id: str
    stage_id: int

class EvidenceRef(BaseModel):
    collection: Literal["input_evidences", "mcp_evidences"]
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

class TriggerPatchPrompt(BaseModel):
    prompt_id: str

class TriggerPatchEvidences(BaseModel):
    evidences: List[EvidenceRef]

class TriggerPatchReport(BaseModel):
    report_id: str