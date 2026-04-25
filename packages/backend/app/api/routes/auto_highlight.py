"""Auto-highlight routes: retrieve-then-extract paper analysis."""
import asyncio
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user, resolve_api_key_with_quota
from app.services.exceptions import IndexingError
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
from app.services.highlight_shortlist_service import highlight_shortlist_service
from app.services.pdf_download_service import pdf_download_service
from app.services.indexing_service import IndexingService

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_PAGES = 100
_BATCH_SIZE_THOROUGH = 5


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
    tier: str,
    llm_client,
) -> None:
    """Background task: ensure indexed → shortlist → LLM extract → annotations."""
    async with SessionLocal() as db:
        try:
            user_result = await db.execute(
                select(User).where(User.id == user_id)
            )
            user = user_result.scalar_one_or_none()
            if not user:
                raise IndexingError("User not found.")

            pdf_result = await db.execute(
                select(Pdf).where(Pdf.id == pdf_id, Pdf.user_id == user_id)
            )
            pdf_row = pdf_result.scalar_one_or_none()
            if not pdf_row:
                raise IndexingError("PDF not found.")

            # Step 1: ensure indexed
            idx_service = IndexingService(download_service=pdf_download_service)
            idx_status = await idx_service.get_or_create_status(
                str(pdf_id), str(user_id), db,
            )
            await db.commit()
            await idx_service.ensure_indexed(pdf_row, user, idx_status, db)
            await db.commit()

            # Step 2: shortlist candidate chunks
            shortlist = await highlight_shortlist_service.shortlist_chunks(
                pdf_id=str(pdf_id),
                user_id=str(user_id),
                categories=categories,
                pages=pages,
                tier=tier,
                db=db,
            )

            if not shortlist:
                raise IndexingError(
                    "No indexed text found for the selected pages. "
                    "Make sure the PDF is indexed and the pages contain text."
                )

            # Fetch cache row for progress updates
            cache_result = await db.execute(
                select(AutoHighlightCache).where(AutoHighlightCache.id == cache_id)
            )
            cache_row = cache_result.scalar_one()

            llm_svc = LLMService(http_client=llm_client)

            if tier == "quick":
                # Quick: single call, all at once
                highlights = await llm_svc.extract_highlights_from_passages(
                    shortlist, categories, provider, api_key, model=model, db=db,
                )

                if not highlights:
                    cache_row.status = "failed"
                    cache_row.progress_pct = 100
                    cache_row.llm_response = {
                        "error": "No highlight-worthy passages found. "
                                 "Try a wider page range or different categories.",
                    }
                    await db.commit()
                    return

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
                    db.add(Annotation(
                        set_id=annotation_set.id,
                        page_number=max(1, h["page"]),
                        type="highlight",
                        rects=[],
                        selected_text=h["text"],
                        note_content=h["reason"],
                        color=CATEGORY_COLORS.get(h["category"], "#a855f7"),
                        ann_metadata={"category": h["category"]},
                    ))

                cache_row.status = "complete"
                cache_row.progress_pct = 100
                cache_row.llm_response = highlights
                cache_row.annotation_set_id = annotation_set.id
                await db.commit()

            else:
                # Thorough: sequential batches with progressive saves
                batches = [
                    shortlist[i:i + _BATCH_SIZE_THOROUGH]
                    for i in range(0, len(shortlist), _BATCH_SIZE_THOROUGH)
                ]
                total = len(batches)
                all_highlights = []
                annotation_set = None

                for idx, batch in enumerate(batches, 1):
                    batch_highlights = await llm_svc.extract_highlights_from_passages(
                        batch, categories, provider, api_key, model=model, db=db,
                    )
                    all_highlights.extend(batch_highlights)

                    if annotation_set is None and batch_highlights:
                        annotation_set = AnnotationSet(
                            pdf_id=pdf_id,
                            user_id=user_id,
                            name=_build_set_name(categories),
                            color="#a855f7",
                            source="auto_highlight",
                        )
                        db.add(annotation_set)
                        await db.flush()

                    for h in batch_highlights:
                        db.add(Annotation(
                            set_id=annotation_set.id,
                            page_number=max(1, h["page"]),
                            type="highlight",
                            rects=[],
                            selected_text=h["text"],
                            note_content=h["reason"],
                            color=CATEGORY_COLORS.get(h["category"], "#a855f7"),
                            ann_metadata={"category": h["category"]},
                        ))

                    cache_row.progress_pct = int(idx / total * 100)
                    if annotation_set:
                        cache_row.annotation_set_id = annotation_set.id
                    await db.commit()

                if not all_highlights:
                    cache_row.status = "failed"
                    cache_row.progress_pct = 100
                    cache_row.llm_response = {
                        "error": "No highlight-worthy passages found. "
                                 "Try a wider page range or different categories.",
                    }
                    await db.commit()
                    return

                cache_row.status = "complete"
                cache_row.progress_pct = 100
                cache_row.llm_response = all_highlights
                if annotation_set:
                    cache_row.annotation_set_id = annotation_set.id
                await db.commit()

            logger.info(
                "Background analysis complete: cache_id=%s, tier=%s",
                cache_id, tier,
            )

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
        pending_cache.status = "pending"
        pending_cache.provider = provider
        pending_cache.llm_response = None
        pending_cache.annotation_set_id = None
        pending_cache.progress_pct = 0
        pending_cache.tier = data.tier
    else:
        pending_cache = AutoHighlightCache(
            pdf_id=data.pdf_id,
            user_id=current_user.id,
            categories=sorted_categories,
            pages=resolved_pages,
            status="pending",
            provider=provider,
            tier=data.tier,
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
            tier=data.tier,
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
        await db.execute(delete(AnnotationSet).where(AnnotationSet.id == cache_row.annotation_set_id))
    await db.execute(delete(AutoHighlightCache).where(AutoHighlightCache.id == cache_id))
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
