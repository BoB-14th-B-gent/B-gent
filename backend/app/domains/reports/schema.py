from pydantic import BaseModel
from typing import List, Optional

class ReportIdOut(BaseModel):
    _id: str

class ReportDetailOut(BaseModel):
    _id: str
    report: str
    conversation_id: Optional[str] = None
    stage_id: Optional[int] = None
    trigger_id: Optional[str] = None
    created_at: str

class ReportListOut(BaseModel):
    total: int
    items: List[ReportDetailOut]