"""Collection-level insight generation (Phase 3: synthesis + gaps)."""

import logging
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import SessionLocal
from app.db.models import CollectionInsight, PdfSummary
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

# Cap the bundle at 20 papers and ~1200 chars per paper block.
MAX_BUNDLE_PAPERS = 20
_MAX_BLOCK_CHARS = 1200


async def _get_insight_row(
    db: AsyncSession, collection_id: uuid.UUID, kind: str
) -> CollectionInsight | None:
    result = await db.execute(
        select(CollectionInsight).where(
            CollectionInsight.collection_id == collection_id,
            CollectionInsight.kind == kind,
        )
    )
    return result.scalar_one_or_none()


async def _mark_failed(collection_id: uuid.UUID, kind: str, error: str) -> None:
    try:
        async with SessionLocal() as db:
            row = await _get_insight_row(db, collection_id, kind)
            if row and row.status == "generating":
                row.status = "failed"
                row.progress_pct = 100
                row.error_message = error
                await db.commit()
    except Exception:
        logger.exception(
            "Failed to mark insight failed: collection_id=%s kind=%s",
            collection_id,
            kind,
        )


def _build_papers_bundle(
    paper_refs: list[tuple[uuid.UUID, str, int | None]],
    summaries: dict[uuid.UUID, PdfSummary],
) -> str:
    """Build the numbered papers bundle string for the LLM prompt.

    paper_refs is the stable ordered list of (pdf_id, title, year).
    summaries maps pdf_id -> complete PdfSummary. Papers without a summary
    are dropped here (they were already filtered out by the caller, but we
    guard defensively).
    """
    blocks: list[str] = []
    for idx, (pdf_id, title, year) in enumerate(paper_refs, 1):
        s = summaries.get(pdf_id)
        if s is None:
            continue
        year_str = str(year) if year else ""
        title_line = f"[{idx}] {title}"
        if year_str:
            title_line += f" ({year_str})"
        key_claims = "; ".join((s.key_claims or [])[:5])
        block = (
            f"{title_line}\n"
            f"TL;DR: {s.tldr or ''}\n"
            f"Method: {s.method or ''}\n"
            f"Result: {s.result or ''}\n"
            f"Key claims: {key_claims}"
        )
        if len(block) > _MAX_BLOCK_CHARS:
            block = block[:_MAX_BLOCK_CHARS]
        blocks.append(block)
    return "\n\n".join(blocks)


def _resolve_chips(
    items: list[dict], paper_refs: list[tuple[uuid.UUID, str, int | None]]
) -> list[dict]:
    """Map 1-based paper_indexes in each item to paper chip objects.

    Preserves all keys from the parsed item except ``paper_indexes``,
    which is replaced by the resolved ``papers`` chip list. Works for
    both themes (which carry ``name``) and gap items (which carry ``title``).
    """
    resolved = []
    for item in items:
        chips = []
        for idx in item.get("paper_indexes", []):
            if 1 <= idx <= len(paper_refs):
                pdf_id, title, _ = paper_refs[idx - 1]
                chips.append({"pdf_id": str(pdf_id), "title": title})
        resolved_item = {k: v for k, v in item.items() if k != "paper_indexes"}
        resolved_item["papers"] = chips
        resolved.append(resolved_item)
    return resolved


async def run_insight(
    collection_id: uuid.UUID,
    user_id: uuid.UUID,
    collection_name: str,
    kind: str,
    paper_refs: list[tuple[uuid.UUID, str, int | None]],
    total_members: int,
    provider: str,
    api_key: str,
    model: str | None,
    llm_client: httpx.AsyncClient,
) -> None:
    """Background task for one collection insight. The route has already set
    status='generating' and committed."""
    try:
        # Phase 1: reload complete summaries, build the bundle.
        async with SessionLocal() as db:
            row = await _get_insight_row(db, collection_id, kind)
            if not row or row.status != "generating":
                return  # deleted or superseded; stop quietly

            # Cap the bundle at MAX_BUNDLE_PAPERS papers.
            capped_refs = paper_refs[:MAX_BUNDLE_PAPERS]
            pdf_ids = [ref[0] for ref in capped_refs]
            summary_rows = await db.execute(
                select(PdfSummary).where(
                    PdfSummary.pdf_id.in_(pdf_ids),
                    PdfSummary.user_id == user_id,
                    PdfSummary.status == "complete",
                )
            )
            summaries = {s.pdf_id: s for s in summary_rows.scalars().all()}
            # Only include papers that still have a complete summary, so
            # bundle numbering stays contiguous with chip resolution.
            effective_refs = [ref for ref in capped_refs if ref[0] in summaries]
            bundle = _build_papers_bundle(effective_refs, summaries)
            paper_count = len(effective_refs)

            row.progress_pct = 30
            row.payload = {"paper_count": paper_count}
            await db.commit()

        # Phase 2: LLM call (no DB session held across the network call).
        llm_svc = LLMService(http_client=llm_client)
        if kind == "synthesis":
            raw = await llm_svc.generate_collection_synthesis(
                collection_name=collection_name,
                papers_bundle=bundle,
                paper_count=paper_count,
                provider=provider,
                api_key=api_key,
                model=model,
            )
        elif kind == "gaps":
            raw = await llm_svc.generate_collection_gaps(
                collection_name=collection_name,
                papers_bundle=bundle,
                paper_count=paper_count,
                provider=provider,
                api_key=api_key,
                model=model,
            )
        else:
            raise ValueError(f"Unknown insight kind: {kind}")

        # Phase 3: resolve chips and persist.
        async with SessionLocal() as db:
            row = await _get_insight_row(db, collection_id, kind)
            if not row or row.status != "generating":
                return

            skipped_no_summary = max(total_members - len(paper_refs), 0)
            if kind == "synthesis":
                payload = {
                    "synthesis": raw["synthesis"],
                    "themes": _resolve_chips(raw["themes"], effective_refs),
                    "paper_count": paper_count,
                    "skipped_no_summary": skipped_no_summary,
                }
            else:
                payload = {
                    "contradictions": _resolve_chips(
                        raw["contradictions"], effective_refs
                    ),
                    "gaps": _resolve_chips(raw["gaps"], effective_refs),
                    "lineages": _resolve_chips(raw["lineages"], effective_refs),
                    "paper_count": paper_count,
                    "skipped_no_summary": skipped_no_summary,
                }

            row.status = "complete"
            row.progress_pct = 100
            row.payload = payload
            row.error_message = None
            row.model = model
            row.generated_at = datetime.now(timezone.utc)
            await db.commit()
    except ValueError as exc:
        await _mark_failed(collection_id, kind, f"Insight parsing failed: {exc}")
    except Exception:
        logger.exception(
            "Insight generation crashed: collection_id=%s kind=%s",
            collection_id,
            kind,
        )
        await _mark_failed(collection_id, kind, "Unexpected insight failure")
