"""Auto-highlight routes: LLM-powered paper analysis."""
import asyncio
import logging
import uuid
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user, resolve_api_key_with_quota
from app.core.config import settings
from app.core.http_client import HTTPClientState
from app.db.engine import SessionLocal
from app.db.models import (
    User, Pdf, Annotation, AnnotationSet, AutoHighlightCache,
    UserUsageQuota, UserApiKey,
)
from app.middleware.rate_limit import limiter
from app.schemas.auto_highlight import (
    AutoHighlightRequest, AutoHighlightResponse,
    AutoHighlightCacheResponse, QuotaResponse,
)
from app.services.llm_service import LLMService, CATEGORY_COLORS
from app.services.text_extractor import extract_text_with_pages, is_text_pdf

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_PAGES = 100
_CHUNK_SIZE = 5  # Pages per LLM call (conservative for free-tier models)


def _split_text_by_pages(
    full_text: str, chunk_pages: list[list[int]]
) -> list[str]:
    """Split extracted text into per-chunk strings using PAGE markers."""
    import re

    # Parse all page blocks from the full text
    pattern = re.compile(r"--- PAGE (\d+) ---\n")
    splits = list(pattern.finditer(full_text))

    # Map page number → its text block
    page_blocks: dict[int, str] = {}
    for i, match in enumerate(splits):
        page_num = int(match.group(1))
        start = match.start()
        end = splits[i + 1].start() if i + 1 < len(splits) else len(full_text)
        page_blocks[page_num] = full_text[start:end].strip()

    chunks: list[str] = []
    for pages in chunk_pages:
        parts = [page_blocks[p] for p in pages if p in page_blocks]
        chunks.append("\n\n".join(parts))

    return chunks


def _build_set_name(categories: list[str]) -> str:
    """Build annotation set name from categories."""
    display = {
        "findings": "Findings",
        "methods": "Methods",
        "definitions": "Definitions",
        "limitations": "Limitations",
        "background": "Background",
    }
    names = [display.get(c, c.title()) for c in categories]
    return "AI: " + ", ".join(names)


async def _run_analysis_background(
    cache_id: uuid.UUID,
    pdf_id: uuid.UUID,
    user_id: uuid.UUID,
    categories: list[str],
    pages: list[int],
    provider: str,
    api_key: str,
    model: Optional[str],
    llm_client: httpx.AsyncClient,
) -> None:
    """Background task: download PDF, call LLM, create annotations.

    Creates its own DB session. Updates cache status to 'complete' or 'failed'.
    """
    tmp_path: Path | None = None
    async with SessionLocal() as db:
        try:

            user_result = await db.execute(
                select(User).where(User.id == user_id)
            )
            user = user_result.scalar_one_or_none()
            if not user:
                raise ValueError("User not found")

            pdf_result = await db.execute(
                select(Pdf).where(Pdf.id == pdf_id, Pdf.user_id == user_id)
            )
            pdf_row = pdf_result.scalar_one_or_none()
            if not pdf_row:
                raise ValueError("PDF not found")


            from app.services.pdf_download_service import pdf_download_service
            from app.services.indexing_service import IndexingService

            idx_service = IndexingService(download_service=pdf_download_service)
            tmp_path = await idx_service.download_pdf_for_row(pdf_row, user, db)

            with open(tmp_path, "rb") as f:
                paper_text, total_pages, pages_analyzed = extract_text_with_pages(
                    f, pages=pages
                )

            if not is_text_pdf(paper_text):
                raise ValueError(
                    "This PDF doesn't contain selectable text. "
                    "Auto-highlight requires text-based PDFs."
                )

            # Split pages into chunks to avoid upstream LLM timeouts
            sorted_pages = sorted(pages)
            page_chunks = [
                sorted_pages[i : i + _CHUNK_SIZE]
                for i in range(0, len(sorted_pages), _CHUNK_SIZE)
            ]

            llm_svc = LLMService(http_client=llm_client)

            if len(page_chunks) <= 1:
                highlights = await llm_svc.analyze_paper(
                    paper_text, categories, provider, api_key, model=model,
                )
            else:
                text_chunks = _split_text_by_pages(paper_text, page_chunks)
                tasks = [
                    llm_svc.analyze_paper(
                        chunk, categories, provider, api_key, model=model,
                    )
                    for chunk in text_chunks
                ]
                chunk_results = await asyncio.gather(*tasks, return_exceptions=True)

                highlights = []
                for i, result in enumerate(chunk_results):
                    if isinstance(result, Exception):
                        logger.warning(
                            "Chunk %d (pages %s) failed: %s",
                            i, page_chunks[i], result,
                        )
                    else:
                        highlights.extend(result)

                if not highlights:
                    raise ValueError(
                        "All analysis chunks failed. Try fewer pages or a different model."
                    )

            annotation_set = AnnotationSet(
                pdf_id=pdf_id,
                user_id=user_id,
                name=_build_set_name(categories),
                color="#a855f7",
                source="auto_highlight",
            )
            db.add(annotation_set)
            await db.flush()

            for h in highlights:
                ann = Annotation(
                    set_id=annotation_set.id,
                    page_number=max(1, h["page"]),
                    type="highlight",
                    rects=[],
                    selected_text=h["text"],
                    note_content=h["reason"],
                    color=CATEGORY_COLORS.get(h["category"], "#a855f7"),
                    ann_metadata={"category": h["category"]},
                )
                db.add(ann)

            cache_result = await db.execute(
                select(AutoHighlightCache).where(AutoHighlightCache.id == cache_id)
            )
            cache_row = cache_result.scalar_one()
            cache_row.status = "complete"
            cache_row.llm_response = highlights
            cache_row.annotation_set_id = annotation_set.id

            await db.commit()
            logger.info("Background analysis complete: cache_id=%s", cache_id)

        except Exception as e:
            logger.exception("Background analysis failed: cache_id=%s", cache_id)
            try:

                await db.rollback()
                cache_result = await db.execute(
                    select(AutoHighlightCache).where(AutoHighlightCache.id == cache_id)
                )
                cache_row = cache_result.scalar_one_or_none()
                if cache_row:
                    cache_row.status = "failed"
                    cache_row.llm_response = {"error": str(e)}
                    await db.commit()
            except Exception:
                logger.exception(
                    "Failed to update cache status for cache_id=%s", cache_id
                )
        finally:
            if tmp_path:
                tmp_path.unlink(missing_ok=True)


@router.post("/analyze", response_model=AutoHighlightResponse, status_code=202)
@limiter.limit(settings.RATE_LIMIT_AUTO_HIGHLIGHT_ANALYZE)
async def analyze_paper(
    request: Request,
    data: AutoHighlightRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Kick off background paper analysis. Returns 202 immediately."""
    sorted_categories = sorted(data.categories)

    resolved_pages = sorted(data.pages) if data.pages else list(range(1, 11))
    if any(p < 1 for p in resolved_pages):
        raise HTTPException(status_code=400, detail="Page numbers must be >= 1")
    if len(resolved_pages) > _MAX_PAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot analyze more than {_MAX_PAGES} pages at once",
        )


    # Resolve API key (fail fast on quota/auth errors)
    resolution = await resolve_api_key_with_quota(
        current_user, db, "auto_highlight", check_openrouter_quota=False,
    )
    provider = resolution.provider
    api_key = resolution.api_key
    model = resolution.model
    logger.info(
        "Resolved provider=%s for background analysis, user=%s",
        provider, current_user.id,
    )

    # Reuse existing failed entry or create new cache entry
    existing_result = await db.execute(
        select(AutoHighlightCache).where(
            AutoHighlightCache.pdf_id == data.pdf_id,
            AutoHighlightCache.user_id == current_user.id,
            AutoHighlightCache.categories == sorted_categories,
            AutoHighlightCache.pages == resolved_pages,
        )
    )
    pending_cache = existing_result.scalar_one_or_none()

    if pending_cache:
        if pending_cache.status == "pending":
            raise HTTPException(status_code=409, detail="Analysis already in progress.")
        # Reuse failed/complete entry
        pending_cache.status = "pending"
        pending_cache.provider = provider
        pending_cache.llm_response = None
        pending_cache.annotation_set_id = None
    else:
        pending_cache = AutoHighlightCache(
            pdf_id=data.pdf_id,
            user_id=current_user.id,
            categories=sorted_categories,
            pages=resolved_pages,
            status="pending",
            provider=provider,
        )
        db.add(pending_cache)

    await db.commit()
    await db.refresh(pending_cache)

    # Get the shared HTTP client for the background task
    llm_client = HTTPClientState.get_llm_client(request.app)

    # Spawn background task
    asyncio.create_task(
        _run_analysis_background(
            cache_id=pending_cache.id,
            pdf_id=data.pdf_id,
            user_id=current_user.id,
            categories=sorted_categories,
            pages=resolved_pages,
            provider=provider,
            api_key=api_key,
            model=model,
            llm_client=llm_client,
        )
    )

    return AutoHighlightResponse(
        cache_id=pending_cache.id,
        from_cache=False,
        highlights_count=0,
    )


@router.get("/cache/entry/{cache_id}", response_model=AutoHighlightCacheResponse)
async def get_cache_entry(
    cache_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get status of a specific cache entry (for polling)."""
    result = await db.execute(
        select(AutoHighlightCache).where(
            AutoHighlightCache.id == cache_id,
            AutoHighlightCache.user_id == current_user.id,
        )
    )
    cache_row = result.scalar_one_or_none()
    if not cache_row:
        raise HTTPException(status_code=404, detail="Cache entry not found")
    return cache_row


@router.get("/cache/{pdf_id}", response_model=list[AutoHighlightCacheResponse])
async def list_cache(
    pdf_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all cached analyses for a PDF (including pending and failed)."""
    result = await db.execute(
        select(AutoHighlightCache).where(
            AutoHighlightCache.pdf_id == pdf_id,
            AutoHighlightCache.user_id == current_user.id,
        ).order_by(AutoHighlightCache.created_at.desc())
    )
    return result.scalars().all()


@router.delete("/cache/{cache_id}", status_code=204)
async def delete_cache(
    cache_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a cached result and its annotation set."""
    result = await db.execute(
        select(AutoHighlightCache).where(
            AutoHighlightCache.id == cache_id,
            AutoHighlightCache.user_id == current_user.id,
        )
    )
    cache_row = result.scalar_one_or_none()
    if not cache_row:
        raise HTTPException(status_code=404, detail="Cache entry not found")

    if cache_row.annotation_set_id:
        await db.execute(
            delete(AnnotationSet).where(AnnotationSet.id == cache_row.annotation_set_id)
        )
    else:
        await db.execute(
            delete(AutoHighlightCache).where(AutoHighlightCache.id == cache_id)
        )

    await db.commit()


@router.get("/quota", response_model=QuotaResponse)
async def get_quota(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current usage quota and API key status."""
    quota_result = await db.execute(
        select(UserUsageQuota).where(UserUsageQuota.user_id == current_user.id)
    )
    quota_row = quota_result.scalar_one_or_none()
    free_remaining = quota_row.free_uses_remaining if quota_row else 5

    keys_result = await db.execute(
        select(UserApiKey.provider).where(UserApiKey.user_id == current_user.id)
    )
    providers = [row[0] for row in keys_result.all()]

    return QuotaResponse(
        free_uses_remaining=free_remaining,
        has_own_key=len(providers) > 0,
        providers=providers,
    )
