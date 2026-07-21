from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class PdfSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pdf_id: UUID
    status: str
    progress_pct: int = 0
    error_message: Optional[str] = None
    tldr: Optional[str] = None
    problem: Optional[str] = None
    method: Optional[str] = None
    dataset: Optional[str] = None
    result: Optional[str] = None
    contribution: Optional[str] = None
    key_claims: Optional[list[str]] = None
    edited_fields: list[str] = []
    model: Optional[str] = None
    generated_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PdfSummaryUpdate(BaseModel):
    """Manual cell/field edits. Only provided fields are touched."""

    tldr: Optional[str] = None
    problem: Optional[str] = None
    method: Optional[str] = None
    dataset: Optional[str] = None
    result: Optional[str] = None
    contribution: Optional[str] = None
    key_claims: Optional[list[str]] = None


class BulkSummarizeResponse(BaseModel):
    queued: list[UUID]
    skipped_complete: int
    skipped_quota: int
    total_papers: int


class ComparisonRow(BaseModel):
    pdf_id: UUID
    title: str
    year: Optional[int] = None
    summary: Optional[PdfSummaryResponse] = None


class ComparisonResponse(BaseModel):
    rows: list[ComparisonRow]
    missing_count: int = Field(description="Members without a complete summary")
