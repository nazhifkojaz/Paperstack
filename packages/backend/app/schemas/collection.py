import uuid
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict


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
    model_config = ConfigDict(from_attributes=True)


class PdfCollectionCreate(BaseModel):
    pdf_id: uuid.UUID


class CollectionInsightResponse(BaseModel):
    collection_id: uuid.UUID
    kind: str
    status: str
    progress_pct: int
    is_stale: bool
    payload: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    model: Optional[str] = None
    generated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)
