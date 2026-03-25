from datetime import datetime
from typing import Optional, Any, Literal
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict

class CitationBase(BaseModel):
    doi: Optional[str] = None
    title: Optional[str] = None
    authors: Optional[str] = None
    year: Optional[int] = None
    bibtex: str
    csl_json: Optional[Any] = None
    source: Optional[str] = 'manual'

class CitationCreate(CitationBase):
    pass

class CitationUpdate(BaseModel):
    doi: Optional[str] = None
    title: Optional[str] = None
    authors: Optional[str] = None
    year: Optional[int] = None
    bibtex: Optional[str] = None
    csl_json: Optional[Any] = None
    source: Optional[str] = None

class CitationResponse(CitationBase):
    id: UUID
    pdf_id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

class BulkExportRequest(BaseModel):
    pdf_ids: list[UUID]
    format: str = Field(default="bibtex", description="Format to export, e.g. bibtex or json")

class LookupRequest(BaseModel):
    doi: Optional[str] = None
    isbn: Optional[str] = None

class LookupResponse(BaseModel):
    doi: Optional[str] = None
    isbn: Optional[str] = None
    title: Optional[str] = None
    authors: Optional[str] = None
    year: Optional[int] = None
    bibtex: str
    csl_json: Optional[dict] = None
    source: Literal["crossref", "openlibrary"]

class ValidateRequest(BaseModel):
    pdf_ids: list[UUID]
