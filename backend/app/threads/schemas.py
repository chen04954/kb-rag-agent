from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ThreadCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    knowledge_base_id: UUID


class ThreadUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class ThreadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    knowledge_base_id: UUID
    title: str
