from pydantic import BaseModel, Field

class TriggerAnalyzeIn(BaseModel):
    trigger_id: str = Field(..., description="TRIGGERS._id (hex string)")

class TriggerAnalyzeOut(BaseModel):
    ok: bool = True
    report_id: str