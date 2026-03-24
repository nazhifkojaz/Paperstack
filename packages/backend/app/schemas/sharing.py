from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel


class ShareCreate(BaseModel):
    shared_with_github_login: Optional[str] = None  # None = public link
    permission: str = 'view'  # 'view' | 'comment'


class ShareResponse(BaseModel):
    id: UUID
    annotation_set_id: UUID
    shared_by: UUID
    shared_with: Optional[UUID] = None
    share_token: str
    permission: str
    created_at: datetime

    class Config:
        from_attributes = True


class AnnotationData(BaseModel):
    id: str
    set_id: str
    page_number: int
    type: str
    rects: list
    selected_text: Optional[str] = None
    note_content: Optional[str] = None
    color: Optional[str] = None


class AnnotationSetData(BaseModel):
    id: str
    pdf_id: str
    name: str
    color: str
    annotations: list[AnnotationData]


class SharedAnnotationsResponse(BaseModel):
    """Public response for /shared/annotations/{token} — no auth required."""
    shared_by_login: str
    shared_by_avatar: Optional[str]
    permission: str
    annotation_set: AnnotationSetData
    pdf_id: str
    pdf_title: str
