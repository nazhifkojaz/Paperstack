"""Auto-highlight routes: retrieve-then-extract paper analysis."""

import asyncio
from dataclasses import dataclass
import difflib
import logging
import re
from time import perf_counter
import unicodedata
import uuid
from typing import Awaitable, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
import httpx
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user, resolve_api_key_with_quota
from app.services.exceptions import IndexingError, LLMProviderError, LLMRateLimitError
from app.core.config import settings
from app.core.http_client import HTTPClientState
from app.db.engine import SessionLocal
from app.db.models import (
    User,
    Pdf,
    Annotation,
    AnnotationSet,
    AutoHighlightCache,
    PdfChunk,
)
from app.schemas.auto_highlight import (
    AutoHighlightRequest,
    AutoHighlightResponse,
    AutoHighlightCacheResponse,
    QuotaResponse,
)
from app.constants.colors import CATEGORY_COLORS
from app.services.api_key_service import api_key_service
from app.services.llm_service import LLMService
from app.services.highlight_shortlist_service import highlight_shortlist_service
from app.services.pdf_download_service import pdf_download_service
from app.services.indexing_service import IndexingService
from app.services.quota_service import quota_service

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_PAGES = 100
_BATCH_SIZE_THOROUGH = 5
# Hard cap on thorough-mode batch concurrency regardless of the configured
# setting. Protects against exhausting provider rate limits or connections.
_MAX_THOROUGH_CONCURRENCY = 4
_LLM_RETRY_DELAYS_SECONDS = (1.0, 2.0)
# When a provider 429 is observed, serialize LLM calls (effective concurrency
# drops to 1) for this long so concurrent batches stop arriving in a burst.
# The window refreshes on every subsequent 429 and lets full concurrency
# resume once it expires, so it self-heals without thrashing.
_RATE_LIMIT_COOLDOWN_SECONDS = 15.0
_TRANSIENT_LLM_STATUS_CODES = {0, 408, 409, 425, 429, 500, 502, 503, 504, 524}


async def _run_logged_step(
    step: str,
    cache_id: uuid.UUID,
    pdf_id: uuid.UUID,
    user_id: uuid.UUID,
    tier: str,
    operation,
):
    started = perf_counter()
    log_context = {
        "auto_highlight_step": step,
        "cache_id": str(cache_id),
        "pdf_id": str(pdf_id),
        "user_id": str(user_id),
        "tier": tier,
    }
    logger.info(
        "Auto-highlight step started: step=%s cache_id=%s pdf_id=%s user_id=%s tier=%s",
        step,
        cache_id,
        pdf_id,
        user_id,
        tier,
        extra=log_context,
    )
    try:
        result = await operation()
    except Exception:
        duration_ms = int((perf_counter() - started) * 1000)
        logger.exception(
            "Auto-highlight step failed: step=%s cache_id=%s duration_ms=%d",
            step,
            cache_id,
            duration_ms,
            extra={**log_context, "duration_ms": duration_ms},
        )
        raise

    duration_ms = int((perf_counter() - started) * 1000)
    logger.info(
        "Auto-highlight step completed: step=%s cache_id=%s duration_ms=%d",
        step,
        cache_id,
        duration_ms,
        extra={**log_context, "duration_ms": duration_ms},
    )
    return result


def _log_background_stop(
    cache_id: uuid.UUID,
    pdf_id: uuid.UUID,
    user_id: uuid.UUID,
    tier: str,
    run_started: float,
    status: str,
    reason: str,
) -> None:
    duration_ms = int((perf_counter() - run_started) * 1000)
    logger.info(
        "Background analysis stopped: cache_id=%s tier=%s status=%s "
        "reason=%s duration_ms=%d",
        cache_id,
        tier,
        status,
        reason,
        duration_ms,
        extra={
            "cache_id": str(cache_id),
            "pdf_id": str(pdf_id),
            "user_id": str(user_id),
            "tier": tier,
            "duration_ms": duration_ms,
            "auto_highlight_status": status,
            "stop_reason": reason,
        },
    )


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


async def _extract_abstract_text(
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


_HIGHLIGHT_MIN_TEXT_LEN = 10
_HIGHLIGHT_MIN_RATIO = 0.75

_re_whitespace = re.compile(r"\s+")


def _norm_for_match(text: str) -> str:
    """Normalize text for fuzzy comparison: lowercase, collapse whitespace,
    NFKC unicode normalization, strip non-alphanumeric edges."""
    text = text.lower()
    text = unicodedata.normalize("NFKC", text)
    text = _re_whitespace.sub(" ", text).strip()
    return text


def _validate_highlights_against_chunks(
    highlights: list[dict],
    passages: list,
) -> list[dict]:
    """Filter highlights to only those textually present in source passages.

    Uses difflib longest-contiguous-match to verify each quote appears
    as a near-substring of the passages fed to the LLM. Quotes below the
    minimum ratio threshold are logged and dropped.
    """
    if not highlights or not passages:
        return []

    norm_passages = [_norm_for_match(p.content) for p in passages]

    valid: list[dict] = []
    for h in highlights:
        norm_quote = _norm_for_match(h["text"])
        if len(norm_quote) < _HIGHLIGHT_MIN_TEXT_LEN:
            continue

        # Try exact substring across all passages (fast path)
        found = any(norm_quote in np for np in norm_passages)
        if found:
            valid.append(h)
            continue

        # Fuzzy: find longest contiguous match in each passage
        best_size = 0
        for np in norm_passages:
            if len(np) == 0:
                continue
            match = difflib.SequenceMatcher(
                None,
                np,
                norm_quote,
                autojunk=False,
            ).find_longest_match(0, len(np), 0, len(norm_quote))
            if match.size > best_size:
                best_size = match.size

        ratio = best_size / len(norm_quote) if norm_quote else 0.0
        if ratio >= _HIGHLIGHT_MIN_RATIO:
            valid.append(h)
        else:
            logger.warning(
                "Dropped highlight not found in source passages (ratio=%.2f): %s",
                ratio,
                h["text"][:120],
            )

    if len(valid) < len(highlights):
        logger.info(
            "Validated highlights: %d/%d passed (dropped %d)",
            len(valid),
            len(highlights),
            len(highlights) - len(valid),
        )

    return valid


def _combine_batch_reasoning_traces(
    traces: list[tuple[int, int, str]],
) -> str | None:
    """Combine non-empty thorough-mode reasoning traces with batch headers."""
    parts = []
    for idx, total, trace in traces:
        cleaned = trace.strip()
        if cleaned:
            parts.append(f"## Batch {idx}/{total}\n{cleaned}")
    return "\n\n".join(parts) if parts else None


async def _get_cache_row(
    db: AsyncSession,
    cache_id: uuid.UUID,
) -> AutoHighlightCache:
    """Fetch the AutoHighlightCache row, raising if not found."""
    result = await db.execute(
        select(AutoHighlightCache).where(AutoHighlightCache.id == cache_id)
    )
    return result.scalar_one()


async def _mark_cache_running(cache_id: uuid.UUID) -> bool:
    """Update the cache row status to 'running' in a short-lived session."""
    try:
        async with SessionLocal() as db:
            result = await db.execute(
                select(AutoHighlightCache).where(AutoHighlightCache.id == cache_id)
            )
            cache_row = result.scalar_one_or_none()
            if not cache_row:
                return False
            if cache_row.status == "cancelled":
                return False
            if cache_row.status in {"pending", "running"}:
                cache_row.status = "running"
                cache_row.progress_pct = max(cache_row.progress_pct or 0, 1)
                await db.commit()
                return True
            return False
    except Exception:
        logger.exception(
            "Failed to mark cache as running for cache_id=%s",
            cache_id,
        )
        return False


async def _set_cache_cancelled(
    db: AsyncSession,
    cache_row: AutoHighlightCache,
) -> AutoHighlightCache:
    if cache_row.status in {"pending", "running"}:
        if cache_row.annotation_set_id:
            await db.execute(
                delete(AnnotationSet).where(
                    AnnotationSet.id == cache_row.annotation_set_id
                )
            )
        cache_row.status = "cancelled"
        cache_row.progress_pct = 100
        cache_row.llm_response = {"error": "Analysis cancelled."}
        cache_row.annotation_set_id = None
        await db.commit()
        await db.refresh(cache_row)
        logger.info(
            "Auto-highlight cancelled: cache_id=%s",
            cache_row.id,
            extra={
                "cache_id": str(cache_row.id),
                "auto_highlight_status": "cancelled",
            },
        )
    return cache_row


async def _mark_cache_cancelled(cache_id: uuid.UUID) -> AutoHighlightCache | None:
    """Mark a running or pending analysis as cancelled."""
    try:
        async with SessionLocal() as db:
            result = await db.execute(
                select(AutoHighlightCache).where(AutoHighlightCache.id == cache_id)
            )
            cache_row = result.scalar_one_or_none()
            if not cache_row:
                return None

            return await _set_cache_cancelled(db, cache_row)
    except Exception:
        logger.exception(
            "Failed to mark cache as cancelled for cache_id=%s",
            cache_id,
        )
        return None


async def _is_cache_cancelled(cache_id: uuid.UUID) -> bool:
    """Return true when cancellation was requested or the cache row disappeared."""
    try:
        async with SessionLocal() as db:
            result = await db.execute(
                select(AutoHighlightCache.status).where(
                    AutoHighlightCache.id == cache_id
                )
            )
            status = result.scalar_one_or_none()
            return status is None or status == "cancelled"
    except Exception:
        logger.exception(
            "Failed to check cancellation status for cache_id=%s",
            cache_id,
        )
        return False


async def _stop_if_cancelled(cache_id: uuid.UUID, step: str) -> bool:
    if not await _is_cache_cancelled(cache_id):
        return False

    logger.info(
        "Auto-highlight cancellation observed: cache_id=%s step=%s",
        cache_id,
        step,
        extra={
            "cache_id": str(cache_id),
            "auto_highlight_status": "cancelled",
            "auto_highlight_step": step,
        },
    )
    return True


async def _mark_cache_failed(cache_id: uuid.UUID, error_msg: str) -> None:
    """Update the cache row status to 'failed' in a short-lived session."""
    try:
        async with SessionLocal() as db:
            result = await db.execute(
                select(AutoHighlightCache).where(AutoHighlightCache.id == cache_id)
            )
            cache_row = result.scalar_one_or_none()
            if cache_row:
                if cache_row.status == "cancelled":
                    return
                if cache_row.annotation_set_id:
                    await db.execute(
                        delete(AnnotationSet).where(
                            AnnotationSet.id == cache_row.annotation_set_id
                        )
                    )
                cache_row.status = "failed"
                cache_row.progress_pct = 100
                cache_row.llm_response = {"error": error_msg}
                cache_row.annotation_set_id = None
                await db.commit()
                logger.info(
                    "Auto-highlight failed: cache_id=%s error=%s",
                    cache_id,
                    error_msg,
                    extra={
                        "cache_id": str(cache_id),
                        "auto_highlight_status": "failed",
                        "error_message": error_msg,
                    },
                )
    except Exception:
        logger.exception(
            "Failed to mark cache as failed for cache_id=%s",
            cache_id,
        )


@dataclass(slots=True)
class _AnalysisSetup:
    pdf_title: str
    abstract_text: str
    shortlist: list


async def _chunk_for_analysis(
    pdf_id: uuid.UUID,
    user_id: uuid.UUID,
    categories: list[str],
    pages: list[int],
    tier: str,
    db: AsyncSession,
    custom_queries: dict[str, str] | None = None,
) -> list:
    """Return candidate chunks for LLM analysis."""
    user_openrouter_key = (
        await api_key_service.get_user_openrouter_key_for_embeddings_by_id(
            user_id,
            db,
        )
    )
    return await highlight_shortlist_service.shortlist_chunks(
        pdf_id=str(pdf_id),
        user_id=str(user_id),
        categories=categories,
        pages=pages,
        tier=tier,
        db=db,
        custom_queries=custom_queries,
        user_api_key=user_openrouter_key,
    )


async def _fetch_paper_content(
    pdf_id: uuid.UUID,
    user_id: uuid.UUID,
    categories: list[str],
    pages: list[int],
    tier: str,
) -> _AnalysisSetup:
    """Validate the paper, ensure indexing, and gather text for analysis."""
    async with SessionLocal() as db:
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            raise IndexingError("User not found.")

        pdf_result = await db.execute(
            select(Pdf).where(Pdf.id == pdf_id, Pdf.user_id == user_id)
        )
        pdf_row = pdf_result.scalar_one_or_none()
        if not pdf_row:
            raise IndexingError("PDF not found.")

        idx_service = IndexingService(download_service=pdf_download_service)
        idx_status = await idx_service.get_or_create_status(
            str(pdf_id),
            str(user_id),
            db,
        )
        await db.commit()
        await idx_service.ensure_indexed(pdf_row, user, idx_status, db)
        await db.commit()

        abstract_text = await _extract_abstract_text(pdf_id, user_id, db)
        shortlist = await _chunk_for_analysis(
            pdf_id,
            user_id,
            categories,
            pages,
            tier,
            db,
        )
        if not shortlist:
            raise IndexingError(
                "No indexed text found for the selected pages. "
                "Make sure the PDF is indexed and the pages contain text."
            )

        return _AnalysisSetup(
            pdf_title=pdf_row.title,
            abstract_text=abstract_text,
            shortlist=shortlist,
        )


async def _prepare_analysis_setup(
    cache_id: uuid.UUID,
    pdf_id: uuid.UUID,
    user_id: uuid.UUID,
    categories: list[str],
    pages: list[int],
    tier: str,
) -> _AnalysisSetup | None:
    try:
        return await _fetch_paper_content(pdf_id, user_id, categories, pages, tier)
    except IndexingError as exc:
        logger.exception(
            "Setup phase failed (IndexingError): cache_id=%s",
            cache_id,
        )
        await _mark_cache_failed(cache_id, str(exc))
        return None
    except Exception:
        logger.exception("Setup phase failed: cache_id=%s", cache_id)

    await _mark_cache_failed(cache_id, "Setup failed")
    return None


async def _generate_custom_queries(
    llm_svc: LLMService,
    setup: _AnalysisSetup,
    categories: list[str],
    provider: str,
    api_key: str,
    model: Optional[str],
) -> dict[str, str] | None:
    """Ask the LLM for paper-specific retrieval queries when enough context exists."""
    if not setup.pdf_title or len(setup.abstract_text) < 50:
        return None

    try:
        custom_queries = await llm_svc.generate_paper_queries(
            title=setup.pdf_title,
            abstract=setup.abstract_text,
            categories=categories,
            provider=provider,
            api_key=api_key,
            model=model,
        )
        if custom_queries:
            logger.info(
                "Generated paper-specific queries for %d categories",
                len(custom_queries),
            )
        return custom_queries
    except Exception:
        logger.exception(
            "Failed to generate paper-specific queries, falling back to canned queries"
        )
        return None


async def _augment_shortlist_with_custom_queries(
    pdf_id: uuid.UUID,
    user_id: uuid.UUID,
    categories: list[str],
    pages: list[int],
    tier: str,
    shortlist: list,
    custom_queries: dict[str, str] | None,
) -> list:
    """Re-run shortlisting with generated queries, falling back to the original list."""
    if not custom_queries:
        return shortlist

    try:
        async with SessionLocal() as db:
            augmented = await _chunk_for_analysis(
                pdf_id,
                user_id,
                categories,
                pages,
                tier,
                db,
                custom_queries=custom_queries,
            )
            return augmented or shortlist
    except Exception:
        logger.exception("Re-shortlist with custom queries failed, using original")
        return shortlist


def _is_transient_llm_error(exc: Exception) -> bool:
    if isinstance(exc, LLMRateLimitError):
        return True
    if isinstance(exc, LLMProviderError):
        return exc.status_code in _TRANSIENT_LLM_STATUS_CODES
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    return False


def _llm_user_error_message(exc: Exception) -> str:
    if isinstance(exc, LLMRateLimitError):
        return str(exc)
    if isinstance(exc, LLMProviderError):
        if exc.status_code in (401, 403):
            return "LLM authentication failed. Check the configured API key."
        if exc.status_code == 402:
            return "LLM quota or billing is unavailable. Check the configured API key."
        if exc.status_code == 429:
            return "LLM rate limit exceeded. Please try again shortly."
        if exc.status_code >= 500 or exc.status_code in (0, 408, 524):
            return "LLM provider is temporarily unavailable. Please try again."
    return "LLM extraction failed"


def _passage_char_count(passages: list) -> int:
    return sum(len(getattr(passage, "content", "")) for passage in passages)


async def _run_llm_analysis(
    llm_svc: LLMService,
    passages: list,
    categories: list[str],
    provider: str,
    api_key: str,
    model: Optional[str],
    cache_id: uuid.UUID,
    label: str,
    on_rate_limit: Optional[Callable[[], Awaitable[None]]] = None,
) -> list[dict] | None:
    """Run extraction for a passage batch and validate quotes against the source.

    ``on_rate_limit`` (optional) is awaited when a provider rate-limit (429)
    error is observed, so callers running concurrent batches can back off
    before the retry lands.
    """
    max_attempts = len(_LLM_RETRY_DELAYS_SECONDS) + 1
    started = perf_counter()
    highlights = None
    for attempt in range(1, max_attempts + 1):
        attempt_started = perf_counter()
        passage_chars = _passage_char_count(passages)
        try:
            logger.info(
                "LLM extraction started: cache_id=%s label=%s attempt=%d/%d "
                "provider=%s model=%s passages=%d chars=%d",
                cache_id,
                label,
                attempt,
                max_attempts,
                provider,
                model or "default",
                len(passages),
                passage_chars,
                extra={
                    "cache_id": str(cache_id),
                    "auto_highlight_step": "llm_extract",
                    "analysis_label": label,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "provider": provider,
                    "model": model or "default",
                    "passage_count": len(passages),
                    "passage_chars": passage_chars,
                },
            )
            highlights = await llm_svc.extract_highlights_from_passages(
                passages,
                categories,
                provider,
                api_key,
                model=model,
            )
            latency_ms = int((perf_counter() - attempt_started) * 1000)
            reasoning_trace = llm_svc.last_reasoning_trace
            reasoning_chars = (
                len(reasoning_trace) if isinstance(reasoning_trace, str) else 0
            )
            logger.info(
                "LLM extraction completed: cache_id=%s label=%s attempt=%d "
                "latency_ms=%d highlights=%d reasoning_chars=%d",
                cache_id,
                label,
                attempt,
                latency_ms,
                len(highlights),
                reasoning_chars,
                extra={
                    "cache_id": str(cache_id),
                    "auto_highlight_step": "llm_extract",
                    "analysis_label": label,
                    "attempt": attempt,
                    "latency_ms": latency_ms,
                    "provider": provider,
                    "model": model or "default",
                    "highlight_count": len(highlights),
                    "reasoning_chars": reasoning_chars,
                },
            )
            break
        except Exception as exc:
            latency_ms = int((perf_counter() - attempt_started) * 1000)
            if isinstance(exc, LLMRateLimitError) and on_rate_limit is not None:
                # Signal the orchestrator before the retry so concurrent
                # batches back off immediately, not after this call finishes.
                await on_rate_limit()
            retryable = _is_transient_llm_error(exc)
            if retryable and attempt < max_attempts:
                delay = _LLM_RETRY_DELAYS_SECONDS[attempt - 1]
                logger.warning(
                    "Transient LLM extraction failure: cache_id=%s label=%s "
                    "attempt=%d/%d latency_ms=%d retry_delay=%.1f error=%s",
                    cache_id,
                    label,
                    attempt,
                    max_attempts,
                    latency_ms,
                    delay,
                    exc,
                    extra={
                        "cache_id": str(cache_id),
                        "auto_highlight_step": "llm_extract",
                        "analysis_label": label,
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "latency_ms": latency_ms,
                        "retry_delay_seconds": delay,
                        "provider": provider,
                        "model": model or "default",
                        "error_type": type(exc).__name__,
                    },
                )
                await asyncio.sleep(delay)
                continue

            logger.exception(
                "LLM extraction failed: cache_id=%s label=%s attempt=%d/%d "
                "latency_ms=%d retryable=%s",
                cache_id,
                label,
                attempt,
                max_attempts,
                latency_ms,
                retryable,
                extra={
                    "cache_id": str(cache_id),
                    "auto_highlight_step": "llm_extract",
                    "analysis_label": label,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "latency_ms": latency_ms,
                    "provider": provider,
                    "model": model or "default",
                    "error_type": type(exc).__name__,
                    "retryable": retryable,
                },
            )
            await _mark_cache_failed(cache_id, _llm_user_error_message(exc))
            return None

    total_latency_ms = int((perf_counter() - started) * 1000)
    valid_highlights = _validate_highlights_against_chunks(highlights or [], passages)
    logger.info(
        "LLM extraction validated: cache_id=%s label=%s latency_ms=%d "
        "valid_highlights=%d raw_highlights=%d",
        cache_id,
        label,
        total_latency_ms,
        len(valid_highlights),
        len(highlights or []),
        extra={
            "cache_id": str(cache_id),
            "auto_highlight_step": "llm_extract_validate",
            "analysis_label": label,
            "latency_ms": total_latency_ms,
            "valid_highlight_count": len(valid_highlights),
            "raw_highlight_count": len(highlights or []),
            "provider": provider,
            "model": model or "default",
        },
    )
    return valid_highlights


def _build_auto_highlight_annotation_set(
    pdf_id: uuid.UUID,
    user_id: uuid.UUID,
    categories: list[str],
) -> AnnotationSet:
    return AnnotationSet(
        pdf_id=pdf_id,
        user_id=user_id,
        name=_build_set_name(categories),
        color="#a855f7",
        source="auto_highlight",
    )


def _add_highlight_annotations(
    db: AsyncSession,
    set_id: uuid.UUID,
    highlights: list[dict],
) -> None:
    for highlight in highlights:
        db.add(
            Annotation(
                set_id=set_id,
                page_number=max(1, highlight["page"]),
                type="highlight",
                rects=[],
                selected_text=highlight["text"],
                note_content=highlight["reason"],
                color=CATEGORY_COLORS.get(highlight["category"], "#a855f7"),
                ann_metadata={"category": highlight["category"]},
            )
        )


def _set_no_highlights_failure(cache_row: AutoHighlightCache) -> None:
    cache_row.status = "failed"
    cache_row.progress_pct = 100
    cache_row.llm_response = {
        "error": "No highlight-worthy passages found. "
        "Try a wider page range or different categories.",
    }


async def _parse_and_store_results(
    cache_id: uuid.UUID,
    pdf_id: uuid.UUID,
    user_id: uuid.UUID,
    categories: list[str],
    highlights: list[dict],
    reasoning_trace: str | None,
) -> bool:
    """Persist the single-pass quick analysis result."""
    try:
        async with SessionLocal() as db:
            cache_row = await _get_cache_row(db, cache_id)
            if cache_row.status == "cancelled":
                return False
            if not highlights:
                _set_no_highlights_failure(cache_row)
                await db.commit()
                return False

            annotation_set = _build_auto_highlight_annotation_set(
                pdf_id,
                user_id,
                categories,
            )
            db.add(annotation_set)
            await db.flush()
            _add_highlight_annotations(db, annotation_set.id, highlights)

            cache_row.status = "complete"
            cache_row.progress_pct = 100
            cache_row.llm_response = highlights
            cache_row.reasoning_trace = reasoning_trace
            cache_row.annotation_set_id = annotation_set.id
            await db.commit()
            return True
    except Exception:
        logger.exception(
            "Failed to persist highlights (quick): cache_id=%s",
            cache_id,
        )
        await _mark_cache_failed(cache_id, "Persistence failed")
        return False


async def _ensure_thorough_annotation_set(
    cache_id: uuid.UUID,
    pdf_id: uuid.UUID,
    user_id: uuid.UUID,
    categories: list[str],
) -> uuid.UUID | None:
    """Pre-create the annotation set for thorough mode.

    Creating the set up front avoids a race between concurrent batches that
    would otherwise both try to lazily create it, and lets each batch simply
    append annotations to a known set.
    """
    try:
        async with SessionLocal() as db:
            cache_row = await _get_cache_row(db, cache_id)
            if cache_row.status == "cancelled":
                return None
            if cache_row.annotation_set_id:
                return cache_row.annotation_set_id
            annotation_set = _build_auto_highlight_annotation_set(
                pdf_id,
                user_id,
                categories,
            )
            db.add(annotation_set)
            await db.flush()
            cache_row.annotation_set_id = annotation_set.id
            await db.commit()
            return annotation_set.id
    except Exception:
        logger.exception(
            "Failed to pre-create annotation set: cache_id=%s",
            cache_id,
        )
        await _mark_cache_failed(cache_id, "Persistence failed")
        return None


async def _persist_thorough_batch(
    cache_id: uuid.UUID,
    set_id: uuid.UUID,
    batch_highlights: list[dict],
    completed_count: int,
    total_batches: int,
) -> bool:
    """Append one batch's annotations and advance progress.

    ``completed_count`` is a monotonically increasing ordinal (not the original
    batch index) so that out-of-order completion under concurrency cannot make
    progress jump backwards.
    """
    try:
        async with SessionLocal() as db:
            cache_row = await _get_cache_row(db, cache_id)
            if cache_row.status == "cancelled":
                return False

            if set_id:
                _add_highlight_annotations(db, set_id, batch_highlights)

            cache_row.progress_pct = int(completed_count / total_batches * 100)
            await db.commit()
            return True
    except Exception:
        logger.exception(
            "Failed to persist thorough batch %d/%d: cache_id=%s",
            completed_count,
            total_batches,
            cache_id,
        )
        await _mark_cache_failed(cache_id, "Persistence failed")
        return False


async def _finalize_thorough_results(
    cache_id: uuid.UUID,
    all_highlights: list[dict],
    batch_reasoning_traces: list[tuple[int, int, str]],
) -> bool:
    try:
        async with SessionLocal() as db:
            cache_row = await _get_cache_row(db, cache_id)
            if cache_row.status == "cancelled":
                return False
            if not all_highlights:
                _set_no_highlights_failure(cache_row)
                await db.commit()
                return False

            cache_row.status = "complete"
            cache_row.progress_pct = 100
            cache_row.llm_response = all_highlights
            cache_row.reasoning_trace = _combine_batch_reasoning_traces(
                batch_reasoning_traces
            )
            await db.commit()
            return True
    except Exception:
        logger.exception("Failed to finalize cache status: cache_id=%s", cache_id)
        return False


async def _run_quick_analysis(
    cache_id: uuid.UUID,
    pdf_id: uuid.UUID,
    user_id: uuid.UUID,
    categories: list[str],
    provider: str,
    api_key: str,
    model: Optional[str],
    llm_svc: LLMService,
    shortlist: list,
) -> bool:
    if await _stop_if_cancelled(cache_id, "quick_before_llm"):
        return False

    highlights = await _run_llm_analysis(
        llm_svc,
        shortlist,
        categories,
        provider,
        api_key,
        model,
        cache_id,
        "quick",
    )
    if highlights is None:
        return False
    if await _stop_if_cancelled(cache_id, "quick_after_llm"):
        return False

    return await _parse_and_store_results(
        cache_id,
        pdf_id,
        user_id,
        categories,
        highlights,
        llm_svc.last_reasoning_trace,
    )


async def _run_thorough_analysis(
    cache_id: uuid.UUID,
    pdf_id: uuid.UUID,
    user_id: uuid.UUID,
    categories: list[str],
    provider: str,
    api_key: str,
    model: Optional[str],
    llm_client,
    shortlist: list,
) -> bool:
    batches = [
        shortlist[i : i + _BATCH_SIZE_THOROUGH]
        for i in range(0, len(shortlist), _BATCH_SIZE_THOROUGH)
    ]
    total = len(batches)

    if total == 0:
        # Nothing to analyze. Finalize handles the no-highlights failure path
        # directly so we don't create an orphaned empty annotation set.
        return await _finalize_thorough_results(cache_id, [], [])

    # Pre-create the annotation set so concurrent batches never race on lazy
    # creation and progress stays monotonic.
    set_id = await _ensure_thorough_annotation_set(
        cache_id,
        pdf_id,
        user_id,
        categories,
    )
    if set_id is None:
        return False

    # Bounded concurrency: overlap slow LLM network calls across batches while
    # respecting provider/rate-limit constraints. 1 preserves the historic
    # sequential behavior; the cap protects against runaway parallelism.
    concurrency = max(
        1,
        min(
            _MAX_THOROUGH_CONCURRENCY,
            settings.AUTO_HIGHLIGHT_THOROUGH_CONCURRENCY,
        ),
    )
    semaphore = asyncio.Semaphore(concurrency)
    # Persistence is serialized so the shared cache-row progress write stays
    # monotonic and batches never contend on the same DB row. Persistence is a
    # cheap local-DB operation; the expensive LLM calls still overlap.
    persist_lock = asyncio.Lock()

    # Adaptive rate-limit backoff. When a 429 is observed we set a cooldown
    # deadline; any batch whose LLM call begins during the cooldown takes the
    # rl_lock first, so effective LLM concurrency drops to 1 until the window
    # expires. This stops concurrent batches from bursting into a provider that
    # is already rejecting us, without permanently lowering the configured
    # concurrency. Using a lock (rather than resizing the semaphore) avoids the
    # deadlock of a permit holder trying to drain its own semaphore.
    rate_limited_until = 0.0
    rl_lock = asyncio.Lock()

    async def _on_rate_limit() -> None:
        nonlocal rate_limited_until
        rate_limited_until = perf_counter() + _RATE_LIMIT_COOLDOWN_SECONDS
        logger.info(
            "Auto-highlight rate-limit backoff engaged: cache_id=%s "
            "cooldown_seconds=%.1f effective_concurrency=1",
            cache_id,
            _RATE_LIMIT_COOLDOWN_SECONDS,
            extra={
                "cache_id": str(cache_id),
                "auto_highlight_step": "rate_limit_backoff",
                "cooldown_seconds": _RATE_LIMIT_COOLDOWN_SECONDS,
            },
        )

    # Per-batch results, indexed by original batch position so the final
    # highlight list and reasoning-trace order is independent of completion
    # order.
    results: list[list[dict] | None] = [None] * total
    traces_by_index: dict[int, str] = {}
    completed = 0
    failed = False

    async def _run_batch(idx: int, batch: list) -> bool:
        nonlocal completed, failed
        try:
            async with semaphore:
                if failed or await _stop_if_cancelled(
                    cache_id, f"thorough_before_batch_{idx + 1}"
                ):
                    return False

                # Each batch gets its own LLMService so the
                # last_reasoning_trace attribute is never shared between
                # in-flight calls. The shared httpx client is reused for
                # connection pooling.
                batch_llm_svc = LLMService(http_client=llm_client)

                async def _extract() -> list[dict] | None:
                    return await _run_llm_analysis(
                        batch_llm_svc,
                        batch,
                        categories,
                        provider,
                        api_key,
                        model,
                        cache_id,
                        f"thorough, batch {idx + 1}/{total}",
                        on_rate_limit=_on_rate_limit,
                    )

                if perf_counter() < rate_limited_until:
                    # Inside a cooldown: serialize LLM calls so we stop
                    # arriving in a burst while the provider is 429-ing.
                    async with rl_lock:
                        batch_highlights = await _extract()
                else:
                    batch_highlights = await _extract()

                if batch_highlights is None:
                    failed = True
                    return False
                if await _stop_if_cancelled(
                    cache_id, f"thorough_after_batch_{idx + 1}_llm"
                ):
                    failed = True
                    return False

                reasoning = batch_llm_svc.last_reasoning_trace
                results[idx] = batch_highlights
                if reasoning:
                    traces_by_index[idx] = reasoning

                async with persist_lock:
                    if failed:
                        return False
                    completed += 1
                    persisted = await _persist_thorough_batch(
                        cache_id,
                        set_id,
                        batch_highlights,
                        completed,
                        total,
                    )
                    if not persisted:
                        failed = True
                        return False
                return True
        except Exception:
            logger.exception(
                "Unexpected error in thorough batch %d/%d: cache_id=%s",
                idx + 1,
                total,
                cache_id,
            )
            await _mark_cache_failed(cache_id, "Unexpected batch failure")
            failed = True
            return False

    tasks = [
        asyncio.create_task(_run_batch(idx, batch)) for idx, batch in enumerate(batches)
    ]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    if failed or await _stop_if_cancelled(cache_id, "thorough_before_finalize"):
        return False

    all_highlights: list[dict] = []
    batch_reasoning_traces: list[tuple[int, int, str]] = []
    for idx in range(total):
        batch_highlights = results[idx]
        if batch_highlights is None:
            return False
        all_highlights.extend(batch_highlights)
        if idx in traces_by_index:
            batch_reasoning_traces.append((idx + 1, total, traces_by_index[idx]))

    return await _finalize_thorough_results(
        cache_id,
        all_highlights,
        batch_reasoning_traces,
    )


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
    """Background task: ensure indexed -> shortlist -> LLM extract -> annotations."""
    run_started = perf_counter()
    logger.info(
        "Background analysis started: cache_id=%s pdf_id=%s user_id=%s "
        "tier=%s provider=%s model=%s categories=%s pages=%d",
        cache_id,
        pdf_id,
        user_id,
        tier,
        provider,
        model or "default",
        categories,
        len(pages),
        extra={
            "cache_id": str(cache_id),
            "pdf_id": str(pdf_id),
            "user_id": str(user_id),
            "tier": tier,
            "provider": provider,
            "model": model or "default",
            "categories": categories,
            "page_count": len(pages),
        },
    )
    if not await _mark_cache_running(cache_id):
        status = "cancelled" if await _is_cache_cancelled(cache_id) else "stopped"
        _log_background_stop(
            cache_id,
            pdf_id,
            user_id,
            tier,
            run_started,
            status,
            "not_started",
        )
        return
    llm_svc = LLMService(http_client=llm_client)

    try:
        if await _stop_if_cancelled(cache_id, "before_prepare_setup"):
            _log_background_stop(
                cache_id,
                pdf_id,
                user_id,
                tier,
                run_started,
                "cancelled",
                "before_prepare_setup",
            )
            return

        setup = await _run_logged_step(
            "prepare_setup",
            cache_id,
            pdf_id,
            user_id,
            tier,
            lambda: _prepare_analysis_setup(
                cache_id,
                pdf_id,
                user_id,
                categories,
                pages,
                tier,
            ),
        )
        if not setup:
            _log_background_stop(
                cache_id,
                pdf_id,
                user_id,
                tier,
                run_started,
                "failed",
                "setup_failed",
            )
            return
        if await _stop_if_cancelled(cache_id, "after_prepare_setup"):
            _log_background_stop(
                cache_id,
                pdf_id,
                user_id,
                tier,
                run_started,
                "cancelled",
                "after_prepare_setup",
            )
            return

        custom_queries = await _run_logged_step(
            "generate_custom_queries",
            cache_id,
            pdf_id,
            user_id,
            tier,
            lambda: _generate_custom_queries(
                llm_svc,
                setup,
                categories,
                provider,
                api_key,
                model,
            ),
        )
        if await _stop_if_cancelled(cache_id, "after_generate_custom_queries"):
            _log_background_stop(
                cache_id,
                pdf_id,
                user_id,
                tier,
                run_started,
                "cancelled",
                "after_generate_custom_queries",
            )
            return
        shortlist = await _run_logged_step(
            "shortlist_with_custom_queries",
            cache_id,
            pdf_id,
            user_id,
            tier,
            lambda: _augment_shortlist_with_custom_queries(
                pdf_id,
                user_id,
                categories,
                pages,
                tier,
                setup.shortlist,
                custom_queries,
            ),
        )
        if await _stop_if_cancelled(cache_id, "after_shortlist"):
            _log_background_stop(
                cache_id,
                pdf_id,
                user_id,
                tier,
                run_started,
                "cancelled",
                "after_shortlist",
            )
            return
        if tier == "quick":
            completed = await _run_logged_step(
                "quick_analysis",
                cache_id,
                pdf_id,
                user_id,
                tier,
                lambda: _run_quick_analysis(
                    cache_id,
                    pdf_id,
                    user_id,
                    categories,
                    provider,
                    api_key,
                    model,
                    llm_svc,
                    shortlist,
                ),
            )
        else:
            completed = await _run_logged_step(
                "thorough_analysis",
                cache_id,
                pdf_id,
                user_id,
                tier,
                lambda: _run_thorough_analysis(
                    cache_id,
                    pdf_id,
                    user_id,
                    categories,
                    provider,
                    api_key,
                    model,
                    llm_client,
                    shortlist,
                ),
            )
    except Exception:
        logger.exception(
            "Background analysis crashed: cache_id=%s pdf_id=%s user_id=%s tier=%s",
            cache_id,
            pdf_id,
            user_id,
            tier,
            extra={
                "cache_id": str(cache_id),
                "pdf_id": str(pdf_id),
                "user_id": str(user_id),
                "tier": tier,
            },
        )
        await _mark_cache_failed(cache_id, "Unexpected analysis failure")
        return

    duration_ms = int((perf_counter() - run_started) * 1000)
    if completed:
        logger.info(
            "Background analysis complete: cache_id=%s tier=%s duration_ms=%d",
            cache_id,
            tier,
            duration_ms,
            extra={
                "cache_id": str(cache_id),
                "pdf_id": str(pdf_id),
                "user_id": str(user_id),
                "tier": tier,
                "duration_ms": duration_ms,
                "auto_highlight_status": "complete",
            },
        )
    else:
        status = "cancelled" if await _is_cache_cancelled(cache_id) else "failed"
        logger.info(
            "Background analysis ended without completion: cache_id=%s "
            "tier=%s status=%s duration_ms=%d",
            cache_id,
            tier,
            status,
            duration_ms,
            extra={
                "cache_id": str(cache_id),
                "pdf_id": str(pdf_id),
                "user_id": str(user_id),
                "tier": tier,
                "duration_ms": duration_ms,
                "auto_highlight_status": status,
            },
        )


@router.post("/analyze", response_model=AutoHighlightResponse, status_code=202)
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
        if pending_cache.status in {"pending", "running"}:
            raise HTTPException(status_code=409, detail="Analysis already in progress.")

    feature = (
        "auto_highlight_thorough" if data.tier == "thorough" else "auto_highlight_quick"
    )
    resolution, _quota_result = await resolve_api_key_with_quota(
        current_user,
        db,
        feature,
    )
    provider = resolution.provider
    api_key = resolution.api_key
    model = resolution.model
    logger.info(
        "Resolved provider=%s for background analysis, user=%s",
        provider,
        current_user.id,
    )

    if pending_cache:
        if pending_cache.annotation_set_id:
            await db.execute(
                delete(AnnotationSet).where(
                    AnnotationSet.id == pending_cache.annotation_set_id
                )
            )
        pending_cache.status = "pending"
        pending_cache.provider = provider
        pending_cache.llm_response = None
        pending_cache.reasoning_trace = None
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


@router.post(
    "/cache/entry/{cache_id}/cancel",
    response_model=AutoHighlightCacheResponse,
)
async def cancel_cache_entry(
    cache_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel a pending or running analysis."""
    result = await db.execute(
        select(AutoHighlightCache).where(
            AutoHighlightCache.id == cache_id,
            AutoHighlightCache.user_id == current_user.id,
        )
    )
    cache_row = result.scalar_one_or_none()
    if not cache_row:
        raise HTTPException(status_code=404, detail="Cache entry not found")
    return await _set_cache_cancelled(db, cache_row)


@router.get("/cache/{pdf_id}", response_model=list[AutoHighlightCacheResponse])
async def list_cache(
    pdf_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all cached analyses for a PDF (including pending and failed)."""
    result = await db.execute(
        select(AutoHighlightCache)
        .where(
            AutoHighlightCache.pdf_id == pdf_id,
            AutoHighlightCache.user_id == current_user.id,
        )
        .order_by(AutoHighlightCache.created_at.desc())
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
    snapshot = await quota_service.get_all_quotas(current_user.id, db)

    return QuotaResponse(
        chat_remaining=snapshot.chat_remaining,
        chat_total=snapshot.chat_total,
        explain_paraphrase_remaining=snapshot.explain_paraphrase_remaining,
        explain_paraphrase_total=snapshot.explain_paraphrase_total,
        auto_highlight_quick_remaining=snapshot.auto_highlight_quick_remaining,
        auto_highlight_quick_total=snapshot.auto_highlight_quick_total,
        auto_highlight_thorough_remaining=snapshot.auto_highlight_thorough_remaining,
        auto_highlight_thorough_total=snapshot.auto_highlight_thorough_total,
        reset_at=snapshot.reset_at,
        has_own_key=snapshot.has_own_key,
        providers=snapshot.providers,
        openrouter_key_mode=snapshot.openrouter_key_mode,
        global_warning=snapshot.global_warning,
    )
