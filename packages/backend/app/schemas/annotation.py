from datetime import datetime
from typing import Any, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

# --- Annotation Sets ---

class AnnotationSetBase(BaseModel):
    name: str = Field(..., max_length=255)
    color: Optional[str] = Field(default='#FFFF00', max_length=7)

class AnnotationSetCreate(AnnotationSetBase):
    pdf_id: UUID
    source: Optional[str] = Field(default='manual', max_length=20)

class AnnotationSetUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    color: Optional[str] = Field(None, max_length=7)

class AnnotationSetResponse(AnnotationSetBase):
    id: UUID
    pdf_id: UUID
    user_id: UUID
    source: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

# --- Annotations ---

class AnnotationBase(BaseModel):
    page_number: int
    type: str = Field(..., max_length=20) # 'highlight', 'rect', 'note'
    rects: Any # JSON array of normalized device coordinates
    selected_text: Optional[str] = None
    note_content: Optional[str] = None
    color: Optional[str] = Field(None, max_length=7)

class AnnotationCreate(AnnotationBase):
    set_id: UUID

class AnnotationUpdate(BaseModel):
    rects: Optional[Any] = None
    selected_text: Optional[str] = None
    note_content: Optional[str] = None
    color: Optional[str] = Field(None, max_length=7)

class AnnotationResponse(AnnotationBase):
    id: UUID
    set_id: UUID
    # ann_metadata maps to the ORM attribute name; serialized as 'metadata' in JSON output
    ann_metadata: Optional[Any] = Field(None, serialization_alias='metadata')
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
