from pydantic import BaseModel, Field, field_validator
from pydantic import ConfigDict
from datetime import datetime
from typing import List

class ConversationCreateInput(BaseModel):
    input: str = Field(...)

    @field_validator("input")
    @classmethod
    def validate_input(cls, v: str):
        if not v or not v.strip():
            raise ValueError("input must not be empty")
        return v.strip()

class ConversationCreatedOut(BaseModel):
    conversation_id: str = Field(alias="_id")
    title: str
    created_at: datetime

    model_config = ConfigDict(populate_by_name=True)

class ConversationDetailOut(BaseModel):
    id: str = Field(..., alias="_id", serialization_alias="_id")
    title: str
    last_stage_id: int
    created_at: datetime
    updated_at: datetime

class ConversationListOut(BaseModel):
    items: List[ConversationDetailOut]

class ReportItemOut(BaseModel):
    report_id: str = Field(alias="_id")
    stage_id: int
    report: str
    created_at: datetime

    model_config = ConfigDict(populate_by_name=True)

class ConversationReportsOut(BaseModel):
    conversation_id: str
    items: List[ReportItemOut]