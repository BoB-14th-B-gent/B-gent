from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, ConfigDict

from app.domains.conversations.schema import ConversationDetailOut

class CaseCreateInput(BaseModel):
    name: str
    description: Optional[str] = None
    analyst: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("name must not be empty")
        return v

    @field_validator("description")
    @classmethod
    def strip_desc(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if isinstance(v, str) else v

    @field_validator("analyst")
    @classmethod
    def strip_analyst(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if isinstance(v, str) else v


class CaseCreatedOut(BaseModel):
    case_id: str = Field(alias="_id")
    created_at: datetime

    model_config = ConfigDict(populate_by_name=True)


class CaseDetailOut(BaseModel):
    id: str = Field(..., alias="_id", serialization_alias="_id")
    name: str
    description: Optional[str] = None
    analyst: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(populate_by_name=True)


class CaseListOut(BaseModel):
    items: List[CaseDetailOut]


class CaseConversationListOut(BaseModel):
    case_id: str
    items: List[ConversationDetailOut]