from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime

class ConversationCreateInput(BaseModel):
    input: str = Field(...)

    @field_validator("input")
    @classmethod
    def validate_input(cls, v: str):
        if not v or not v.strip():
            raise ValueError("input must not be empty")
        return v.strip()

class ConversationCreatedOut(BaseModel):
    _id: str
    title: str
    created_at: datetime

class ConversationDetailOut(BaseModel):
    _id: str
    title: str
    last_stage_id: int
    created_at: datetime
    updated_at: datetime