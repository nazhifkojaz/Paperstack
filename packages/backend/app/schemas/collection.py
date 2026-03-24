import uuid
from typing import Optional
from pydantic import BaseModel

class CollectionBase(BaseModel):
    name: str
    parent_id: Optional[uuid.UUID] = None
    position: int = 0

class CollectionCreate(CollectionBase):
    pass

class CollectionUpdate(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[uuid.UUID] = None
    position: Optional[int] = None

class CollectionResponse(CollectionBase):
    id: uuid.UUID
    user_id: uuid.UUID

    class Config:
        from_attributes = True

class PdfCollectionCreate(BaseModel):
    pdf_id: uuid.UUID
