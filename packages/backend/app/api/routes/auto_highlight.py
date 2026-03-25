"""Auto-highlight routes: LLM-powered paper analysis."""
import logging
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.core.config import settings
from app.db.models import (
    User, Pdf, Annotation, AnnotationSet, AutoHighlightCache,
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
from app.services.llm_service import llm_service, CATEGORY_COLORS
from app.services.pdf_download_service import PdfSource
from app.services.text_extractor import extract_text_with_pages, is_text_pdf

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


@router.post("/analyze", response_model=AutoHighlightResponse)
@limiter.limit(settings.RATE_LIMIT_AUTO_HIGHLIGHT_ANALYZE)
async def analyze_paper(
    request: Request,
    data: AutoHighlightRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Analyze a paper with LLM and create auto-highlight annotations."""
    sorted_categories = sorted(data.categories)

    # 1. Check cache
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

    # 2. Resolve API key using service
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

    # 3. Create pending cache entry (atomic dedup)
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
        # 4. Fetch PDF from GitHub or URL using download service
        pdf_result = await db.execute(
            select(Pdf).where(Pdf.id == data.pdf_id, Pdf.user_id == current_user.id)
        )
        pdf_row = pdf_result.scalar_one_or_none()
        if not pdf_row:
            raise HTTPException(status_code=404, detail="PDF not found")

        # Download PDF using the unified download service
        from app.services.pdf_download_service import pdf_download_service

        if pdf_row.source_url and not pdf_row.github_sha:
            download_result = await pdf_download_service.download_to_tempfile(
                source=PdfSource.EXTERNAL_URL,
                external_url=pdf_row.source_url,
            )
        else:
            download_result = await pdf_download_service.download_to_tempfile(
                source=PdfSource.GITHUB,
                github_access_token=current_user.access_token,
                github_login=current_user.github_login,
                github_filename=pdf_row.filename,
            )
        tmp_path = download_result.file_path

        # 5. Extract text
        with open(tmp_path, "rb") as f:
            paper_text, total_pages, pages_analyzed = extract_text_with_pages(f)

        if not is_text_pdf(paper_text):
            raise HTTPException(
                status_code=422,
                detail="This PDF doesn't contain selectable text. Auto-highlight requires text-based PDFs.",
            )

        # 6. Call LLM
        highlights = await llm_service.analyze_paper(
            paper_text, sorted_categories, provider, api_key
        )

        # 7. Create AnnotationSet
        annotation_set = AnnotationSet(
            pdf_id=data.pdf_id,
            user_id=current_user.id,
            name=_build_set_name(sorted_categories),
            color="#a855f7",
            source="auto_highlight",
        )
        db.add(annotation_set)
        await db.flush()

        # 8. Create Annotations
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

        # 9. Update cache
        pending_cache.status = "complete"
        pending_cache.llm_response = highlights
        pending_cache.annotation_set_id = annotation_set.id

        # 10. Decrement quota if in-house
        if is_in_house:
            await api_key_service.decrement_quota(
                str(current_user.id), QuotaType.FREE, db
            )

        await db.commit()

        return AutoHighlightResponse(
            annotation_set_id=annotation_set.id,
            from_cache=False,
            highlights_count=len(highlights),
            pages_analyzed=pages_analyzed,
        )

    except HTTPException:
        # Clean up pending cache on known errors
        await db.rollback()
        await db.execute(
            delete(AutoHighlightCache).where(AutoHighlightCache.id == pending_cache.id)
        )
        await db.commit()
        raise
    except LLMRateLimitError as e:
        await db.rollback()
        await db.execute(
            delete(AutoHighlightCache).where(AutoHighlightCache.id == pending_cache.id)
        )
        await db.commit()
        raise HTTPException(status_code=429, detail=str(e))
    except LLMProviderError as e:
        await db.rollback()
        await db.execute(
            delete(AutoHighlightCache).where(AutoHighlightCache.id == pending_cache.id)
        )
        await db.commit()
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        # Clean up pending cache on unexpected errors
        await db.rollback()
        await db.execute(
            delete(AutoHighlightCache).where(AutoHighlightCache.id == pending_cache.id)
        )
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")
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
    # Get quota
    quota_result = await db.execute(
        select(UserUsageQuota).where(UserUsageQuota.user_id == current_user.id)
    )
    quota_row = quota_result.scalar_one_or_none()
    free_remaining = quota_row.free_uses_remaining if quota_row else 5

    # Get user's stored providers
    keys_result = await db.execute(
        select(UserApiKey.provider).where(UserApiKey.user_id == current_user.id)
    )
    providers = [row[0] for row in keys_result.all()]

    return QuotaResponse(
        free_uses_remaining=free_remaining,
        has_own_key=len(providers) > 0,
        providers=providers,
    )
