"""Per-paper structured summary generation (B1)."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.engine import SessionLocal
from app.db.models import Pdf, PdfChunk, PdfSummary, User
from app.services.exceptions import IndexingError
from app.services.indexing_service import IndexingService
from app.services.llm_service import LLMService, SUMMARY_FIELDS
from app.services.pdf_download_service import pdf_download_service
from app.services.pdf_text_utils import extract_summary_source_text

logger = logging.getLogger(__name__)

# Fields the LLM writes; used to respect edited_fields on regeneration.
_GENERATED_FIELDS = SUMMARY_FIELDS + ("key_claims",)


async def compute_paper_embedding(
    pdf_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> list[float] | None:
    """Mean of the PDF's chunk embeddings, in pure Python.

    Returns None when no embedded chunks exist. Never uses AVG(halfvec)
    (unverified in pgvector) and never loads more than one paper's chunks.
    """
    result = await db.execute(
        select(PdfChunk.embedding).where(
            PdfChunk.pdf_id == pdf_id,
            PdfChunk.user_id == user_id,
            PdfChunk.embedding.is_not(None),
        )
    )
    rows = result.scalars().all()
    if not rows:
        return None

    def _to_floats(emb) -> list[float]:
        # pgvector returns a HalfVector object (with .to_list); lists/numpy
        # are also tolerated for robustness.
        if hasattr(emb, "to_list"):
            return [float(v) for v in emb.to_list()]
        return [float(v) for v in emb]

    vectors = [_to_floats(emb) for emb in rows]
    dim = len(vectors[0])
    acc = [0.0] * dim
    for vec in vectors:
        for i, v in enumerate(vec):
            acc[i] += v
    n = len(vectors)
    return [v / n for v in acc]


async def _get_summary_row(
    db: AsyncSession, pdf_id: uuid.UUID, user_id: uuid.UUID
) -> PdfSummary | None:
    result = await db.execute(
        select(PdfSummary).where(
            PdfSummary.pdf_id == pdf_id, PdfSummary.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def _mark_failed(pdf_id: uuid.UUID, user_id: uuid.UUID, error: str) -> None:
    try:
        async with SessionLocal() as db:
            row = await _get_summary_row(db, pdf_id, user_id)
            if row and row.status == "generating":
                row.status = "failed"
                row.progress_pct = 100
                row.error_message = error
                await db.commit()
    except Exception:
        logger.exception("Failed to mark summary failed: pdf_id=%s", pdf_id)


async def run_generation(
    pdf_id: uuid.UUID,
    user_id: uuid.UUID,
    provider: str,
    api_key: str,
    model: str | None,
    llm_client: httpx.AsyncClient,
) -> None:
    """Background task for one paper. The route has already set
    status='generating' and committed."""
    try:
        # Phase 1: ensure indexed, gather source text, store the paper
        # embedding (cheap, no LLM — lands even if the LLM later fails).
        async with SessionLocal() as db:
            user = (
                await db.execute(select(User).where(User.id == user_id))
            ).scalar_one_or_none()
            pdf = (
                await db.execute(
                    select(Pdf).where(Pdf.id == pdf_id, Pdf.user_id == user_id)
                )
            ).scalar_one_or_none()
            if not user or not pdf:
                raise IndexingError("PDF not found.")

            idx_service = IndexingService(download_service=pdf_download_service)
            idx_status = await idx_service.get_or_create_status(
                str(pdf_id), str(user_id), db
            )
            await db.commit()
            await idx_service.ensure_indexed(pdf, user, idx_status, db)
            await db.commit()

            title = pdf.title
            source_text = await extract_summary_source_text(pdf_id, user_id, db)
            if len(source_text) < 50:
                raise IndexingError("Not enough indexed text to summarize this paper.")

            row = await _get_summary_row(db, pdf_id, user_id)
            if not row or row.status != "generating":
                return  # deleted or superseded; stop quietly
            if row.paper_embedding is None:
                row.paper_embedding = await compute_paper_embedding(pdf_id, user_id, db)
            row.progress_pct = 30
            await db.commit()

        # Phase 2: LLM call (no DB session held across the network call).
        llm_svc = LLMService(http_client=llm_client)
        summary = await llm_svc.generate_paper_summary(
            title=title,
            source_text=source_text,
            provider=provider,
            api_key=api_key,
            model=model,
        )

        # Phase 3: persist, respecting user edits.
        async with SessionLocal() as db:
            row = await _get_summary_row(db, pdf_id, user_id)
            if not row or row.status != "generating":
                return
            edited = set(row.edited_fields or [])
            for field in _GENERATED_FIELDS:
                if field not in edited:
                    setattr(row, field, summary.get(field))
            row.status = "complete"
            row.progress_pct = 100
            row.error_message = None
            row.model = model
            row.generated_at = datetime.now(timezone.utc)
            await db.commit()
    except IndexingError as exc:
        await _mark_failed(pdf_id, user_id, str(exc))
    except ValueError as exc:
        await _mark_failed(pdf_id, user_id, f"Summary parsing failed: {exc}")
    except Exception:
        logger.exception("Summary generation crashed: pdf_id=%s", pdf_id)
        await _mark_failed(pdf_id, user_id, "Unexpected summary failure")


async def run_bulk_generation(
    pdf_ids: list[uuid.UUID],
    user_id: uuid.UUID,
    provider: str,
    api_key: str,
    model: str | None,
    llm_client: httpx.AsyncClient,
) -> None:
    """Background task for a collection: bounded-concurrency fan-out."""
    semaphore = asyncio.Semaphore(max(1, settings.SUMMARY_BULK_CONCURRENCY))

    async def _one(pid: uuid.UUID) -> None:
        async with semaphore:
            await run_generation(pid, user_id, provider, api_key, model, llm_client)

    await asyncio.gather(*(_one(pid) for pid in pdf_ids), return_exceptions=True)
