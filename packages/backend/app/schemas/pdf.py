import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, HttpUrl, ConfigDict

class PdfBase(BaseModel):
    title: str
    filename: str
    doi: Optional[str] = None
    isbn: Optional[str] = None

class PdfCreate(PdfBase):
    pass

class PdfLinkCreate(BaseModel):
    title: str
    source_url: HttpUrl
    project_ids: Optional[List[uuid.UUID]] = None
    doi: Optional[str] = None
    isbn: Optional[str] = None

class PdfUpdate(BaseModel):
    title: Optional[str] = None
    source_url: Optional[str] = None
    doi: Optional[str] = None
    isbn: Optional[str] = None

class PdfResponse(PdfBase):
    id: uuid.UUID
    user_id: uuid.UUID
    source_url: Optional[str] = None
    github_sha: Optional[str] = None
    drive_file_id: Optional[str] = None
    file_size: Optional[int] = None
    page_count: Optional[int] = None
    uploaded_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

class PdfListParams(BaseModel):
    collection_id: Optional[uuid.UUID] = None
    tag_id: Optional[uuid.UUID] = None
    q: Optional[str] = None
    sort: str = "-uploaded_at"
    page: int = 1
    per_page: int = 50
