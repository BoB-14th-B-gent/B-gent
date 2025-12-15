from datetime import datetime
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field

class EvidenceFromConversationIn(BaseModel):
    conversation_id: str
    mode: Optional[str] = Field("auto")
    inline_threshold: int = 10 * 1024 * 1024
    stage_id: int

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
    id: str = Field(alias="_id")
    conversation_id: Optional[str] = None
    stage_id: Optional[int] = None
    filename: Optional[str] = None
    size: Optional[int] = None
    created_at: Optional[datetime] = None

class EvidenceListOut(BaseModel):
    items: List[EvidenceListItem]

class EvidenceInputDetail(BaseModel):
    id: str = Field(alias="_id")
    conversation_id: Optional[str] = None
    stage_id: Optional[int] = None
    filename: Optional[str] = None
    size: Optional[int] = None
    data: Optional[Any] = None
    data_gridfs_id: Optional[str] = None
    ingested_at: Optional[datetime] = None

class McpEvidenceListItem(BaseModel):
    id: str = Field(alias="_id")
    trigger_id: Optional[str] = None
    conversation_id: Optional[str] = None
    stage_id: Optional[int] = None
    mcp_name: Optional[str] = None
    tool_name: Optional[str] = None
    created_at: Optional[datetime] = None

class McpEvidenceListOut(BaseModel):
    items: List[McpEvidenceListItem]

class McpEvidenceDetailOut(BaseModel):
    id: str = Field(alias="_id")
    trigger_id: Optional[str] = None
    conversation_id: Optional[str] = None
    stage_id: Optional[int] = None
    mcp_name: Optional[str] = None
    tool_name: Optional[str] = None
    agent_id: Optional[str] = None
    success: Optional[bool] = None
    created_at: Optional[datetime] = None
    request: Optional[Dict[str, Any]] = None
    response: Optional[Dict[str, Any]] = None