import uuid
from typing import Optional
from pydantic import BaseModel, ConfigDict

class TagBase(BaseModel):
    name: str
    color: str = "#808080"

class TagCreate(TagBase):
    pass

class TagUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None

class TagResponse(TagBase):
    id: uuid.UUID
    user_id: uuid.UUID
    model_config = ConfigDict(from_attributes=True)

class PdfTagCreate(BaseModel):
    tag_id: uuid.UUID
