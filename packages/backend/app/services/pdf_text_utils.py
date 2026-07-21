"""Shared helpers for pulling representative text out of indexed PDF chunks."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PdfChunk


async def extract_abstract_text(
    pdf_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> str:
    """Extract abstract text from indexed chunks.

    First tries chunks tagged with section_title="Abstract", then falls back
    to the first 3 chunks (which typically cover abstract + introduction).
    """
    # Try chunks with explicit "Abstract" section heading
    result = await db.execute(
        select(PdfChunk)
        .where(
            PdfChunk.pdf_id == pdf_id,
            PdfChunk.user_id == user_id,
            PdfChunk.section_title.ilike("abstract"),
        )
        .order_by(PdfChunk.chunk_index)
        .limit(3)
    )
    abstract_chunks = result.scalars().all()

    if abstract_chunks:
        return " ".join(c.content for c in abstract_chunks)[:3000]

    # Fall back to first chunks by index (usually cover abstract + introduction)
    result = await db.execute(
        select(PdfChunk)
        .where(
            PdfChunk.pdf_id == pdf_id,
            PdfChunk.user_id == user_id,
        )
        .order_by(PdfChunk.chunk_index)
        .limit(3)
    )
    first_chunks = result.scalars().all()

    if first_chunks:
        return " ".join(c.content for c in first_chunks)[:3000]

    return ""


async def extract_summary_source_text(
    pdf_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> str:
    """Abstract + (when present) conclusion text, for summary generation.

    The conclusion often carries the result/contribution facts the abstract
    omits. Capped so the combined prompt stays small.
    """
    abstract = await extract_abstract_text(pdf_id, user_id, db)

    result = await db.execute(
        select(PdfChunk)
        .where(
            PdfChunk.pdf_id == pdf_id,
            PdfChunk.user_id == user_id,
            PdfChunk.section_title.ilike("%conclusion%"),
        )
        .order_by(PdfChunk.chunk_index)
        .limit(2)
    )
    conclusion_chunks = result.scalars().all()
    conclusion = " ".join(c.content for c in conclusion_chunks)[:2500]

    if conclusion:
        return f"{abstract}\n\n[Conclusion]\n{conclusion}"
    return abstract
