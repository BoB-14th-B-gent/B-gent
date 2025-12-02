from typing import Any, Dict, List
from datetime import datetime
from pydantic import BaseModel, Field

class RFPosition(BaseModel):
    x: float
    y: float

class RFNode(BaseModel):
    id: str
    type: str
    position: RFPosition
    data: Dict[str, Any] = Field(default_factory=dict)

class RFEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str = "dotted"
    data: Dict[str, Any] = Field(default_factory=dict)

class UILayoutBase(BaseModel):
    nodes: List[RFNode] = Field(default_factory=list)
    edges: List[RFEdge] = Field(default_factory=list)

class UILayoutOut(UILayoutBase):
    conversation_id: str
    stage_id: int
    created_at: datetime
    updated_at: datetime

class UILayoutUpsertIn(UILayoutBase):
    pass