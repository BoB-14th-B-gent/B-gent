from typing import Optional
from pydantic import BaseModel

DEFAULT_INLINE_THRESHOLD: int = 10 * 1024 * 1024

class RunPipelineReq(BaseModel):
    input: str
    stage_id: int = 0
    inline_threshold: int = DEFAULT_INLINE_THRESHOLD
    mode: str = "auto"
    conversation_id: Optional[str] = None
    case_id: Optional[str] = None

class PipelinePrepareResult(BaseModel):
    conversation_id: str
    trigger_id: str
    prompt_id: Optional[str] = None

class PipelineFullResult(BaseModel):
    conversation_id: str
    trigger_id: str
    prompt_id: Optional[str] = None
    report_id: str
    report: str

class RunAfterAgentReq(BaseModel):
    trigger_id: str

__all__ = [
    "DEFAULT_INLINE_THRESHOLD",
    "RunPipelineReq",
    "PipelinePrepareResult",
    "PipelineFullResult",
]