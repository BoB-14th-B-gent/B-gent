from pydantic import BaseModel, Field

class TriggerAnalyzeIn(BaseModel):
    trigger_id: str

class TriggerAnalyzeOut(BaseModel):
    ok: bool = True
    report_id: str