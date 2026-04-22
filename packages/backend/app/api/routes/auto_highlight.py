"""Auto-highlight routes: LLM-powered paper analysis."""
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user, get_llm_http_client
from app.core.config import settings
from app.db.models import (
    User, Pdf, Annotation, AnnotationSet, AutoHighlightCache,
    UserUsageQuota, UserApiKey,
)
from app.middleware.rate_limit import limiter
from app.schemas.auto_highlight import (
    AutoHighlightRequest, AutoHighlightResponse,
    AutoHighlightCacheResponse, QuotaResponse,
)
from app.services.api_key_service import QuotaType, api_key_service
from app.services.exceptions import (
    ApiKeyNotFoundError,
    LLMRateLimitError,
    LLMProviderError,
    QuotaExhaustedError,
)
from app.services.llm_service import LLMService, CATEGORY_COLORS
from app.services.pdf_download_service import PdfSource
from app.services.text_extractor import extract_text_with_pages, is_text_pdf

logger = logging.getLogger(__name__)

router = APIRouter()


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


@asynccontextmanager
async def _cleanup_pending_cache_on_error(db: AsyncSession, cache_id: uuid.UUID):
    """Context manager that cleans up pending cache entry on error.

    On any exception, this will:
    1. Rollback the database transaction
    2. Delete the pending cache entry
    3. Commit the deletion
    4. Re-raise with appropriate HTTP status code

    HTTPException is re-raised as-is (preserves status code).
    LLMRateLimitError becomes 429.
    LLMProviderError becomes 502.
    Other exceptions become 500.
    """
    try:
        yield
    except HTTPException:
        await db.rollback()
        await db.execute(
            delete(AutoHighlightCache).where(AutoHighlightCache.id == cache_id)
        )
        await db.commit()
        raise
    except LLMRateLimitError as e:
        await db.rollback()
        await db.execute(
            delete(AutoHighlightCache).where(AutoHighlightCache.id == cache_id)
        )
        await db.commit()
        raise HTTPException(status_code=429, detail=str(e))
    except LLMProviderError as e:
        await db.rollback()
        await db.execute(
            delete(AutoHighlightCache).where(AutoHighlightCache.id == cache_id)
        )
        await db.commit()
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        await db.rollback()
        await db.execute(
            delete(AutoHighlightCache).where(AutoHighlightCache.id == cache_id)
        )
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.post("/analyze", response_model=AutoHighlightResponse)
@limiter.limit(settings.RATE_LIMIT_AUTO_HIGHLIGHT_ANALYZE)
async def analyze_paper(
    request: Request,
    data: AutoHighlightRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    llm_client: httpx.AsyncClient = Depends(get_llm_http_client),
):
    """Analyze a paper with LLM and create auto-highlight annotations."""
    sorted_categories = sorted(data.categories)

    # Check cache
    cache_result = await db.execute(
        select(AutoHighlightCache).where(
            AutoHighlightCache.pdf_id == data.pdf_id,
            AutoHighlightCache.user_id == current_user.id,
            AutoHighlightCache.categories == sorted_categories,
        )
    )
    cache_row = cache_result.scalar_one_or_none()

    if cache_row:
        if cache_row.status == "pending":
            raise HTTPException(status_code=409, detail="Analysis already in progress.")
        if cache_row.status == "complete" and cache_row.annotation_set_id:
            # Count annotations
            count_result = await db.execute(
                select(func.count()).where(Annotation.set_id == cache_row.annotation_set_id)
            )
            count = count_result.scalar() or 0
            return AutoHighlightResponse(
                annotation_set_id=cache_row.annotation_set_id,
                from_cache=True,
                highlights_count=count,
            )

    try:
        resolution = await api_key_service.resolve_for_auto_highlight(current_user, db)
    except (QuotaExhaustedError, ApiKeyNotFoundError) as e:
        raise HTTPException(status_code=402, detail=str(e))
    provider = resolution.provider
    api_key = resolution.api_key
    is_in_house = resolution.is_in_house
    logger.info(
        "Resolved provider=%s, is_in_house=%s for user %s",
        provider, is_in_house, current_user.id,
    )

    # Create pending cache entry (atomic dedup)
    try:
        pending_cache = AutoHighlightCache(
            pdf_id=data.pdf_id,
            user_id=current_user.id,
            categories=sorted_categories,
            status="pending",
            provider=provider,
        )
        db.add(pending_cache)
        await db.flush()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Analysis already in progress.")

    tmp_path: Path | None = None
    try:
        async with _cleanup_pending_cache_on_error(db, pending_cache.id):
            pdf_result = await db.execute(
                select(Pdf).where(Pdf.id == data.pdf_id, Pdf.user_id == current_user.id)
            )
            pdf_row = pdf_result.scalar_one_or_none()
            if not pdf_row:
                raise HTTPException(status_code=404, detail="PDF not found")

            # Download PDF using the unified download service
            from app.services.pdf_download_service import pdf_download_service

            if pdf_row.source_url and not pdf_row.github_sha and not pdf_row.drive_file_id:
                download_result = await pdf_download_service.download_to_tempfile(
                    source=PdfSource.EXTERNAL_URL,
                    external_url=pdf_row.source_url,
                )
                tmp_path = download_result.file_path
            else:
                from app.services.storage.factory import get_storage_backend
                backend = await get_storage_backend(current_user, db)
                file_id = pdf_row.drive_file_id or pdf_row.github_sha
                tmp_path = await backend.download_to_tempfile(file_id, pdf_row.filename)

            with open(tmp_path, "rb") as f:
                paper_text, total_pages, pages_analyzed = extract_text_with_pages(f)

            if not is_text_pdf(paper_text):
                raise HTTPException(
                    status_code=422,
                    detail="This PDF doesn't contain selectable text. Auto-highlight requires text-based PDFs.",
                )

            # Call LLM (with OpenRouter fallback on 429)
            llm_svc = LLMService(http_client=llm_client)
            provider_fallback = False

            try:
                highlights = await llm_svc.analyze_paper(
                    paper_text, sorted_categories, provider, api_key
                )
            except LLMRateLimitError:
                # Only retry if primary was OpenRouter
                if provider != "openrouter":
                    raise  # Let context manager handle → 429

                logger.warning(
                    "OpenRouter rate limited for auto-highlight, falling back for user %s",
                    current_user.id,
                )

                try:
                    paid_resolution = await api_key_service.resolve_paid_fallback(
                        current_user,
                        db,
                        quota_field=QuotaType.FREE.value,
                        feature_priority=api_key_service.AUTO_HIGHLIGHT_PRIORITY,
                    )
                except (QuotaExhaustedError, ApiKeyNotFoundError) as e:
                    raise HTTPException(status_code=402, detail=str(e))

                provider = paid_resolution.provider
                api_key = paid_resolution.api_key
                is_in_house = True
                provider_fallback = True

                highlights = await llm_svc.analyze_paper(
                    paper_text, sorted_categories, provider, api_key
                )

            annotation_set = AnnotationSet(
                pdf_id=data.pdf_id,
                user_id=current_user.id,
                name=_build_set_name(sorted_categories),
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
                    rects=[],  # Resolved by frontend TextLayer matching
                    selected_text=h["text"],
                    note_content=h["reason"],
                    color=CATEGORY_COLORS.get(h["category"], "#a855f7"),
                    metadata={"category": h["category"]},
                )
                db.add(ann)

            pending_cache.status = "complete"
            pending_cache.llm_response = highlights
            pending_cache.annotation_set_id = annotation_set.id

            # Decrement quota if in-house AND paid (not free OpenRouter)
            if is_in_house and provider != "openrouter":
                await api_key_service.decrement_quota(
                    str(current_user.id), QuotaType.FREE, db
                )

            await db.commit()

            return AutoHighlightResponse(
                annotation_set_id=annotation_set.id,
                from_cache=False,
                highlights_count=len(highlights),
                pages_analyzed=pages_analyzed,
                provider_fallback=provider_fallback,
            )
    finally:
        if tmp_path:
            tmp_path.unlink(missing_ok=True)


@router.get("/cache/{pdf_id}", response_model=list[AutoHighlightCacheResponse])
async def list_cache(
    pdf_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List cached analyses for a PDF."""
    result = await db.execute(
        select(AutoHighlightCache).where(
            AutoHighlightCache.pdf_id == pdf_id,
            AutoHighlightCache.user_id == current_user.id,
            AutoHighlightCache.status == "complete",
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

    # Delete the annotation set first (cascades to annotations + cache via FK)
    if cache_row.annotation_set_id:
        await db.execute(
            delete(AnnotationSet).where(AnnotationSet.id == cache_row.annotation_set_id)
        )
    else:
        # No annotation set — just delete the cache row
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
