from typing import Literal, List
from datetime import datetime
from pydantic import BaseModel, Field

class MessageCreate(BaseModel):
    role: Literal["USER", "B-GENT"]
    stage_id: int
    content: str

class MessageIdOut(BaseModel):
    _id: str

class MessageItem(BaseModel):
    _id: str
    role: Literal["USER", "B-GENT"]
    stage_id: int
    content: str
    created_at: datetime

class MessageListOut(BaseModel):
    conversation_id: str
    items: List[MessageItem]

class MessageDetailOut(BaseModel):
    conversation_id: str
    role: Literal["USER", "B-GENT"]
    content: str