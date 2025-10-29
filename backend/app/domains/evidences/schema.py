from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field

class EvidenceFromConversationIn(BaseModel):
    conversation_id: str
    mode: Optional[str] = Field("auto")
    inline_threshold: int = 10 * 1024 * 1024

class EvidenceCreatedItem(BaseModel):
    evidence_id: str
    type: Optional[str] = None
    strategy: Literal["inline", "gridfs"]
    data_gridfs_id: Optional[str] = None
    filename: str
    size: int

class EvidenceCreatedOut(BaseModel):
    prompt_id: Optional[str] = None
    items: List[EvidenceCreatedItem]

class EvidenceListItem(BaseModel):
    _id: str
    conversation_id: Optional[str] = None
    stage_id: Optional[int] = None
    filename: Optional[str] = None
    size: Optional[int] = None
    created_at: Optional[datetime] = None

class EvidenceListOut(BaseModel):
    items: List[EvidenceListItem]

class EvidenceInputDetail(BaseModel):
    _id: str
    conversation_id: Optional[str] = None
    stage_id: Optional[int] = None
    filename: Optional[str] = None
    size: Optional[int] = None
    data: Optional[dict] = None
    data_gridfs_id: Optional[str] = None
    ingested_at: Optional[datetime] = None