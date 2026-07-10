"""Per-paper structured summary routes (B1)."""

import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user, resolve_api_key_with_quota
from app.core.http_client import HTTPClientState
from app.db.models import Pdf, PdfSummary, User
from app.schemas.summary import PdfSummaryResponse, PdfSummaryUpdate
from app.services import summary_service

router = APIRouter()
logger = logging.getLogger(__name__)


async def _get_owned_pdf(
    db: AsyncSession, pdf_id: uuid.UUID, user_id: uuid.UUID
) -> Pdf:
    """Load a PDF owned by the user or raise 404."""
    result = await db.execute(
        select(Pdf).where(Pdf.id == pdf_id, Pdf.user_id == user_id)
    )
    pdf = result.scalar_one_or_none()
    if not pdf:
        raise HTTPException(status_code=404, detail="PDF not found")
    return pdf


@router.post(
    "/{pdf_id}/summary",
    response_model=PdfSummaryResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_summary(
    pdf_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PdfSummaryResponse:
    """Trigger (or re-trigger) summary generation for one PDF."""
    await _get_owned_pdf(db, pdf_id, current_user.id)

    existing = await summary_service._get_summary_row(db, pdf_id, current_user.id)
    if existing and existing.status == "generating":
        raise HTTPException(
            status_code=409, detail="Summary generation already in progress."
        )

    resolution, _ = await resolve_api_key_with_quota(current_user, db, "summary")

    if existing:
        existing.status = "generating"
        existing.progress_pct = 0
        existing.error_message = None
        row = existing
    else:
        row = PdfSummary(
            pdf_id=pdf_id,
            user_id=current_user.id,
            status="generating",
        )
        db.add(row)

    await db.commit()
    await db.refresh(row)

    llm_client = HTTPClientState.get_llm_client(request.app)
    asyncio.create_task(
        summary_service.run_generation(
            pdf_id=pdf_id,
            user_id=current_user.id,
            provider=resolution.provider,
            api_key=resolution.api_key,
            model=resolution.model,
            llm_client=llm_client,
        )
    )
    return row


@router.get("/{pdf_id}/summary", response_model=PdfSummaryResponse)
async def get_summary(
    pdf_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PdfSummaryResponse:
    """Fetch the summary row for a PDF (404 when none exists yet)."""
    await _get_owned_pdf(db, pdf_id, current_user.id)

    row = await summary_service._get_summary_row(db, pdf_id, current_user.id)
    if not row:
        raise HTTPException(status_code=404, detail="No summary for this PDF")
    return row


@router.patch("/{pdf_id}/summary", response_model=PdfSummaryResponse)
async def update_summary(
    pdf_id: uuid.UUID,
    update: PdfSummaryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PdfSummaryResponse:
    """Apply manual edits to summary fields (upserts a row when missing)."""
    await _get_owned_pdf(db, pdf_id, current_user.id)

    row = await summary_service._get_summary_row(db, pdf_id, current_user.id)
    if row and row.status == "generating":
        raise HTTPException(
            status_code=409,
            detail="Cannot edit a summary while it is generating.",
        )
    if not row:
        row = PdfSummary(
            pdf_id=pdf_id,
            user_id=current_user.id,
            status="not_generated",
        )
        db.add(row)

    update_data = update.model_dump(exclude_unset=True)
    edited = set(row.edited_fields or [])
    for field, value in update_data.items():
        setattr(row, field, value)
        edited.add(field)
    row.edited_fields = sorted(edited)

    await db.commit()
    await db.refresh(row)
    return row
