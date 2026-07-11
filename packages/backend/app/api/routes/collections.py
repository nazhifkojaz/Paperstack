import asyncio
import logging
import re
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import List, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select, func, text as sql_text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.deps import resolve_api_key_with_quota
from app.core.http_client import HTTPClientState
from app.db.models import (
    Collection,
    CollectionInsight,
    Pdf,
    PdfCollection,
    PdfSummary,
    User,
    Citation,
    PdfIndexStatus,
)
from app.schemas.collection import (
    CollectionCreate,
    CollectionInsightResponse,
    CollectionResponse,
    CollectionUpdate,
)
from app.schemas.summary import (
    BulkSummarizeResponse,
    ComparisonResponse,
    ComparisonRow,
    PdfSummaryResponse,
)
from app.services import insight_service, summary_service
from app.services.exceptions import QuotaExhaustedError
from app.services.quota_service import quota_service
from app.utils.db_utils import handle_unique_violation
from app.api.routes.citations import build_bibtex_export

router = APIRouter()
logger = logging.getLogger(__name__)


async def _is_descendant(
    db: AsyncSession, ancestor_id: uuid.UUID, target_id: uuid.UUID
) -> bool:
    """Check whether target_id is a descendant of ancestor_id (cycle guard)."""
    current_parent = target_id
    visited = set()
    while current_parent:
        if current_parent == ancestor_id:
            return True
        if current_parent in visited:
            return False
        visited.add(current_parent)
        result = await db.execute(
            select(Collection.parent_id).where(Collection.id == current_parent)
        )
        parent = result.scalar_one_or_none()
        current_parent = parent
    return False


@router.post("", response_model=CollectionResponse)
async def create_collection(
    collection_in: CollectionCreate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> CollectionResponse:
    """Create a new collection."""
    if collection_in.parent_id:
        parent = await db.get(Collection, collection_in.parent_id)
        if not parent or parent.user_id != current_user.id:
            raise HTTPException(status_code=400, detail="Invalid parent collection")

    collection = Collection(
        user_id=current_user.id,
        name=collection_in.name,
        parent_id=collection_in.parent_id,
        position=collection_in.position,
    )
    db.add(collection)
    await db.commit()
    await db.refresh(collection)
    return collection


@router.get("", response_model=List[CollectionResponse])
async def list_collections(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> List[CollectionResponse]:
    """List all collections for the user."""
    query = (
        select(Collection)
        .where(Collection.user_id == current_user.id)
        .order_by(Collection.position)
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.patch("/{collection_id}", response_model=CollectionResponse)
async def update_collection(
    collection_id: uuid.UUID,
    collection_in: CollectionUpdate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> CollectionResponse:
    """Update a collection."""
    collection = await db.get(Collection, collection_id)
    if not collection or collection.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Collection not found")

    if (
        collection_in.parent_id is not None
        and collection_in.parent_id != collection.parent_id
    ):
        if collection_in.parent_id == collection_id:
            raise HTTPException(
                status_code=400, detail="Cannot set a collection as its own parent"
            )
        parent = await db.get(Collection, collection_in.parent_id)
        if not parent or parent.user_id != current_user.id:
            raise HTTPException(status_code=400, detail="Invalid parent collection")

        # Check for cycles: the new parent must not be a descendant of this collection
        if await _is_descendant(db, collection_id, collection_in.parent_id):
            raise HTTPException(
                status_code=400,
                detail="Cannot move a collection under its own descendant",
            )

    update_data = collection_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(collection, field, value)

    db.add(collection)
    await db.commit()
    await db.refresh(collection)
    return collection


@router.delete("/{collection_id}")
async def delete_collection(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> dict[str, str]:
    """Delete a collection. Child collections are reparented to the parent."""
    collection = await db.get(Collection, collection_id)
    if not collection or collection.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Collection not found")

    children_result = await db.execute(
        select(Collection).where(Collection.parent_id == collection_id)
    )
    children = children_result.scalars().all()
    for child in children:
        child.parent_id = collection.parent_id
        db.add(child)

    await db.delete(collection)
    await db.commit()
    return {"message": "Collection successfully deleted"}


@router.post("/{collection_id}/pdfs")
async def add_pdf_to_collection(
    collection_id: uuid.UUID,
    pdf_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> dict[str, str]:
    """Add a PDF to a collection."""
    collection = await db.get(Collection, collection_id)
    if not collection or collection.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Collection not found")

    pdf = await db.get(Pdf, pdf_id)
    if not pdf or pdf.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="PDF not found")

    pdf_collection = PdfCollection(pdf_id=pdf_id, collection_id=collection_id)
    db.add(pdf_collection)

    async with handle_unique_violation(
        db,
        "PDF is already in this collection",
        logger,
        {
            "user_id": str(current_user.id),
            "pdf_id": str(pdf_id),
            "collection_id": str(collection_id),
        },
    ):
        await db.execute(
            update(CollectionInsight)
            .where(CollectionInsight.collection_id == collection_id)
            .values(is_stale=True)
        )
        await db.commit()

    return {"message": "PDF added to collection"}


@router.delete("/{collection_id}/pdfs/{pdf_id}")
async def remove_pdf_from_collection(
    collection_id: uuid.UUID,
    pdf_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> dict[str, str]:
    """Remove a PDF from a collection."""
    collection = await db.get(Collection, collection_id)
    if not collection or collection.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Collection not found")

    pdf_collection = await db.get(PdfCollection, (pdf_id, collection_id))
    if not pdf_collection:
        raise HTTPException(status_code=404, detail="PDF is not in this collection")

    await db.delete(pdf_collection)
    await db.execute(
        update(CollectionInsight)
        .where(CollectionInsight.collection_id == collection_id)
        .values(is_stale=True)
    )
    await db.commit()
    return {"message": "PDF removed from collection"}


@router.get("/{collection_id}/export")
async def export_collection(
    collection_id: uuid.UUID,
    format: str = "bibtex",
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Export a collection's citations as BibTeX or Markdown."""
    collection = await db.get(Collection, collection_id)
    if not collection or collection.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Collection not found")

    rows = await db.execute(
        select(Pdf, Citation)
        .join(PdfCollection, PdfCollection.pdf_id == Pdf.id)
        .outerjoin(Citation, Citation.pdf_id == Pdf.id)
        .where(
            PdfCollection.collection_id == collection_id,
            Pdf.user_id == current_user.id,
        )
    )
    pairs = rows.all()

    if not pairs:
        raise HTTPException(
            status_code=404, detail="No papers found in this collection"
        )

    citations = [c for _, c in pairs if c is not None]
    total = len(pairs)
    missing = total - len(citations)

    safe_name = re.sub(r"[^a-zA-Z0-9_\- ]", "", collection.name).strip() or "collection"

    if format.lower() == "bibtex":
        lines = []
        if missing > 0:
            lines.append(f"% {missing} of {total} papers had no citation")
        body = build_bibtex_export(citations)
        if body:
            lines.append(body)
        export_text = "\n".join(lines)
        return Response(
            content=export_text,
            media_type="text/plain",
            headers={"Content-Disposition": f"attachment; filename={safe_name}.bib"},
        )

    elif format.lower() == "markdown":
        lines = [f"# {collection.name}", ""]
        if missing > 0:
            lines.append(f"{missing} of {total} papers had no citation.")
            lines.append("")
        for pdf, citation in pairs:
            if citation:
                title = citation.title or pdf.title
                authors = citation.authors or ""
                year_str = str(citation.year) if citation.year else ""
                doi_str = ""
                if citation.doi:
                    doi_str = f". [doi](https://doi.org/{citation.doi})"
                lines.append(f"- **{title}** — {authors} ({year_str}){doi_str}")
            else:
                lines.append(f"- {pdf.title}")
        export_text = "\n".join(lines)
        return Response(
            content=export_text,
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename={safe_name}.md"},
        )

    raise HTTPException(status_code=400, detail="Unsupported format")


@router.get("/{collection_id}/overview")
async def get_collection_overview(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> dict:
    """Return aggregate stats for a collection."""
    collection = await db.get(Collection, collection_id)
    if not collection or collection.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Collection not found")

    pdf_rows = await db.execute(
        select(Pdf)
        .join(PdfCollection, PdfCollection.pdf_id == Pdf.id)
        .where(
            PdfCollection.collection_id == collection_id,
            Pdf.user_id == current_user.id,
        )
    )
    pdfs = pdf_rows.scalars().all()
    paper_count = len(pdfs)
    pdf_ids = [p.id for p in pdfs]

    indexed_count = 0
    if pdf_ids:
        idx_result = await db.execute(
            select(func.count(PdfIndexStatus.pdf_id)).where(
                PdfIndexStatus.pdf_id.in_(pdf_ids),
                PdfIndexStatus.status == "indexed",
            )
        )
        indexed_count = idx_result.scalar() or 0

    year_distribution: dict[int, int] = {}
    top_authors: list[dict] = []
    recent_papers: list[dict] = []
    papers: list[dict] = []

    if pdf_ids:
        citation_rows = await db.execute(
            select(Citation).where(Citation.pdf_id.in_(pdf_ids))
        )
        citations = citation_rows.scalars().all()

        citation_by_pdf_id = {c.pdf_id: c for c in citations}

        year_counts = Counter()
        author_counts = Counter()
        for c in citations:
            if c.year:
                year_counts[c.year] += 1
            if c.authors:
                for author in c.authors.split(","):
                    cleaned = author.strip()
                    if cleaned:
                        author_counts[cleaned] += 1

        year_distribution = dict(sorted(year_counts.items()))

        top_authors = [
            {"name": name, "count": cnt} for name, cnt in author_counts.most_common(10)
        ]

        recent_result = await db.execute(
            select(Pdf, PdfCollection)
            .join(PdfCollection, PdfCollection.pdf_id == Pdf.id)
            .where(
                PdfCollection.collection_id == collection_id,
                Pdf.user_id == current_user.id,
            )
            .order_by(PdfCollection.added_at.desc())
            .limit(5)
        )
        recent = recent_result.all()
        recent_papers = [
            {"id": str(p.id), "title": p.title, "filename": p.filename}
            for p, _ in recent
        ]

        for p in pdfs:
            c = citation_by_pdf_id.get(p.id)
            year = c.year if c else None
            first_author = None
            if c and c.authors:
                first_seg = c.authors.split(",")[0].strip()
                first_author = first_seg or None
            papers.append(
                {
                    "id": str(p.id),
                    "title": p.title,
                    "year": year,
                    "first_author": first_author,
                }
            )

    return {
        "paper_count": paper_count,
        "indexed_count": indexed_count,
        "year_distribution": year_distribution,
        "top_authors": top_authors,
        "recent_papers": recent_papers,
        "papers": papers,
    }


async def _load_owned_collection(
    db: AsyncSession, collection_id: uuid.UUID, user_id: uuid.UUID
) -> Collection:
    collection = await db.get(Collection, collection_id)
    if not collection or collection.user_id != user_id:
        raise HTTPException(status_code=404, detail="Collection not found")
    return collection


@router.post(
    "/{collection_id}/summaries",
    response_model=BulkSummarizeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def bulk_summarize_collection(
    collection_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> BulkSummarizeResponse:
    """Queue summary generation for every member paper missing one."""
    await _load_owned_collection(db, collection_id, current_user.id)

    pdf_rows = await db.execute(
        select(Pdf.id)
        .join(PdfCollection, PdfCollection.pdf_id == Pdf.id)
        .where(
            PdfCollection.collection_id == collection_id,
            Pdf.user_id == current_user.id,
        )
        .order_by(Pdf.title)
    )
    member_ids = [row[0] for row in pdf_rows.all()]
    total_papers = len(member_ids)

    if not member_ids:
        return BulkSummarizeResponse(
            queued=[],
            skipped_complete=0,
            skipped_quota=0,
            total_papers=0,
        )

    summary_rows = await db.execute(
        select(PdfSummary).where(PdfSummary.pdf_id.in_(member_ids))
    )
    summaries = {s.pdf_id: s for s in summary_rows.scalars().all()}

    candidates: list[uuid.UUID] = []
    skipped_complete = 0
    for pid in member_ids:
        row = summaries.get(pid)
        if row is None or row.status in ("not_generated", "failed"):
            candidates.append(pid)
        elif row.status == "complete":
            skipped_complete += 1
        # 'generating' is silently skipped (neither queued nor an error).

    if not candidates:
        return BulkSummarizeResponse(
            queued=[],
            skipped_complete=skipped_complete,
            skipped_quota=0,
            total_papers=total_papers,
        )

    # Resolve the key once (covers the first candidate). When the result is
    # unlimited (BYOK), no quota is consumed for any candidate.
    resolution, quota_result = await resolve_api_key_with_quota(
        current_user, db, "summary"
    )
    queued: list[uuid.UUID] = []
    skipped_quota = 0

    if quota_result.unlimited:
        queued.extend(candidates)
    else:
        # First candidate already paid via resolve_api_key_with_quota.
        queued.append(candidates[0])
        for pid in candidates[1:]:
            try:
                await quota_service.check_and_decrement(current_user.id, db, "summary")
            except QuotaExhaustedError:
                skipped_quota = len(candidates) - len(queued)
                break
            queued.append(pid)

    # Upsert queued rows to 'generating' in the request session, commit, then
    # spawn ONE background task for the whole collection.
    for pid in queued:
        row = summaries.get(pid)
        if row:
            row.status = "generating"
            row.progress_pct = 0
            row.error_message = None
        else:
            db.add(
                PdfSummary(
                    pdf_id=pid,
                    user_id=current_user.id,
                    status="generating",
                )
            )
    await db.commit()

    llm_client = HTTPClientState.get_llm_client(request.app)
    asyncio.create_task(
        summary_service.run_bulk_generation(
            pdf_ids=queued,
            user_id=current_user.id,
            provider=resolution.provider,
            api_key=resolution.api_key,
            model=resolution.model,
            llm_client=llm_client,
        )
    )

    return BulkSummarizeResponse(
        queued=queued,
        skipped_complete=skipped_complete,
        skipped_quota=skipped_quota,
        total_papers=total_papers,
    )


@router.get("/{collection_id}/summaries", response_model=List[PdfSummaryResponse])
async def get_collection_summaries(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> List[PdfSummaryResponse]:
    """Return all summary rows for members of a collection."""
    await _load_owned_collection(db, collection_id, current_user.id)

    result = await db.execute(
        select(PdfSummary)
        .join(PdfCollection, PdfCollection.pdf_id == PdfSummary.pdf_id)
        .where(
            PdfCollection.collection_id == collection_id,
            PdfSummary.user_id == current_user.id,
        )
    )
    return result.scalars().all()


@router.get("/{collection_id}/comparison", response_model=ComparisonResponse)
async def get_collection_comparison(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> ComparisonResponse:
    """Comparison matrix rows: one per member paper, with optional summary."""
    await _load_owned_collection(db, collection_id, current_user.id)

    rows = await db.execute(
        select(Pdf, Citation, PdfSummary)
        .join(PdfCollection, PdfCollection.pdf_id == Pdf.id)
        .outerjoin(Citation, Citation.pdf_id == Pdf.id)
        .outerjoin(
            PdfSummary,
            (PdfSummary.pdf_id == Pdf.id) & (PdfSummary.user_id == current_user.id),
        )
        .where(
            PdfCollection.collection_id == collection_id,
            Pdf.user_id == current_user.id,
        )
    )
    pairs = rows.all()

    comparison_rows: list[ComparisonRow] = []
    missing_count = 0
    for pdf, citation, summary in pairs:
        title = (citation.title if citation and citation.title else None) or pdf.title
        year = citation.year if citation else None
        summary_resp = PdfSummaryResponse.model_validate(summary) if summary else None
        if not summary or summary.status != "complete":
            missing_count += 1
        comparison_rows.append(
            ComparisonRow(
                pdf_id=pdf.id,
                title=title,
                year=year,
                summary=summary_resp,
            )
        )

    # Order by Citation.year (nulls last), then title.
    comparison_rows.sort(key=lambda r: (r.year is None, r.year or 0, r.title.lower()))

    return ComparisonResponse(rows=comparison_rows, missing_count=missing_count)


# --- Phase 3: Collection insights (synthesis + gaps) ---

_INSIGHT_STALE_THRESHOLD = timedelta(minutes=10)


async def _trigger_insight(
    collection_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
    request: Request,
    kind: str,
) -> CollectionInsightResponse:
    """Shared implementation for POST synthesize / gaps."""
    collection = await _load_owned_collection(db, collection_id, current_user.id)

    # Step 1: load complete member summaries ordered by title (stable index).
    rows = await db.execute(
        select(Pdf, Citation, PdfSummary)
        .join(PdfCollection, PdfCollection.pdf_id == Pdf.id)
        .outerjoin(Citation, Citation.pdf_id == Pdf.id)
        .join(
            PdfSummary,
            (PdfSummary.pdf_id == Pdf.id) & (PdfSummary.user_id == current_user.id),
        )
        .where(
            PdfCollection.collection_id == collection_id,
            Pdf.user_id == current_user.id,
            PdfSummary.status == "complete",
        )
        .order_by(Pdf.title)
    )
    complete_members = rows.all()
    if len(complete_members) < 2:
        raise HTTPException(
            status_code=400,
            detail="Generate summaries for at least 2 papers first.",
        )

    paper_refs = [
        (pdf.id, pdf.title, citation.year if citation else None)
        for pdf, citation, _ in complete_members
    ]

    # Total member count (for skipped_no_summary in the payload).
    total_result = await db.execute(
        select(func.count(PdfCollection.pdf_id)).where(
            PdfCollection.collection_id == collection_id
        )
    )
    total_members = total_result.scalar() or 0

    # Step 2: staleness / in-flight guard.
    existing = await insight_service._get_insight_row(db, collection_id, kind)
    if existing and existing.status == "generating":
        if existing.updated_at and existing.updated_at < (
            datetime.now(timezone.utc) - _INSIGHT_STALE_THRESHOLD
        ):
            pass  # stale generating row — allow re-trigger
        else:
            raise HTTPException(
                status_code=409,
                detail="Insight generation already in progress.",
            )

    # Step 3: resolve API key (reuse the "summary" quota bucket).
    resolution, _ = await resolve_api_key_with_quota(current_user, db, "summary")

    # Step 4: upsert the row to 'generating'.
    if existing:
        existing.status = "generating"
        existing.progress_pct = 0
        existing.is_stale = False
        existing.error_message = None
        existing.payload = None
        row = existing
    else:
        row = CollectionInsight(
            collection_id=collection_id,
            user_id=current_user.id,
            kind=kind,
            status="generating",
        )
        db.add(row)
    await db.commit()
    await db.refresh(row)

    # Step 5: spawn background task.
    llm_client = HTTPClientState.get_llm_client(request.app)
    asyncio.create_task(
        insight_service.run_insight(
            collection_id=collection_id,
            user_id=current_user.id,
            collection_name=collection.name,
            kind=kind,
            paper_refs=paper_refs,
            total_members=total_members,
            provider=resolution.provider,
            api_key=resolution.api_key,
            model=resolution.model,
            llm_client=llm_client,
        )
    )
    return row


@router.post(
    "/{collection_id}/synthesize",
    response_model=CollectionInsightResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def synthesize_collection(
    collection_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> CollectionInsightResponse:
    """Trigger (or re-trigger) cross-paper synthesis generation."""
    return await _trigger_insight(
        collection_id, current_user, db, request, kind="synthesis"
    )


@router.post(
    "/{collection_id}/insights/gaps",
    response_model=CollectionInsightResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_collection_gaps(
    collection_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> CollectionInsightResponse:
    """Trigger (or re-trigger) gap/contradiction/lineage analysis."""
    return await _trigger_insight(collection_id, current_user, db, request, kind="gaps")


@router.get(
    "/{collection_id}/insights/{kind}", response_model=CollectionInsightResponse
)
async def get_collection_insight(
    collection_id: uuid.UUID,
    kind: Literal["synthesis", "gaps"],
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> CollectionInsightResponse:
    """Fetch the insight row for a collection (404 when none exists)."""
    await _load_owned_collection(db, collection_id, current_user.id)
    row = await insight_service._get_insight_row(db, collection_id, kind)
    if not row:
        raise HTTPException(status_code=404, detail="No insight for this collection")
    return row


_DUPLICATES_SQL = sql_text(
    """
    SELECT a.pdf_id AS pdf_a_id, b.pdf_id AS pdf_b_id,
           pa.title AS pdf_a_title, pb.title AS pdf_b_title,
           1 - (a.paper_embedding <=> b.paper_embedding) AS similarity
    FROM pdf_summaries a
    JOIN pdf_collections pca ON pca.pdf_id = a.pdf_id
        AND pca.collection_id = :cid
    JOIN pdf_summaries b ON b.user_id = a.user_id
        AND a.pdf_id < b.pdf_id
    JOIN pdf_collections pcb ON pcb.pdf_id = b.pdf_id
        AND pcb.collection_id = :cid
    JOIN pdfs pa ON pa.id = a.pdf_id
    JOIN pdfs pb ON pb.id = b.pdf_id
    WHERE a.user_id = :uid
      AND a.paper_embedding IS NOT NULL
      AND b.paper_embedding IS NOT NULL
      AND 1 - (a.paper_embedding <=> b.paper_embedding) >= :threshold
    ORDER BY similarity DESC
    LIMIT 20
    """
)


@router.get("/{collection_id}/duplicates")
async def get_collection_duplicates(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> dict:
    """Return near-duplicate paper pairs within a collection."""
    await _load_owned_collection(db, collection_id, current_user.id)

    from app.core.config import settings

    result = await db.execute(
        _DUPLICATES_SQL,
        {
            "cid": str(collection_id),
            "uid": str(current_user.id),
            "threshold": settings.DUPLICATE_SIMILARITY_THRESHOLD,
        },
    )
    pairs = [
        {
            "pdf_a": {"id": str(r.pdf_a_id), "title": r.pdf_a_title},
            "pdf_b": {"id": str(r.pdf_b_id), "title": r.pdf_b_title},
            "similarity": float(r.similarity),
        }
        for r in result.all()
    ]
    return {"pairs": pairs}


_OPENALEX_NOT_FOUND = "!"  # sentinel: DOI checked against OpenAlex, no match


@router.get("/{collection_id}/recommendations")
async def get_collection_recommendations(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> dict:
    """Suggest works frequently cited by this collection but not in it."""
    import httpx

    from app.core.config import settings
    from app.services import openalex_client

    await _load_owned_collection(db, collection_id, current_user.id)

    # 1. Members with their DOI (Citation.doi, falling back to Pdf.doi when
    #    citation extraction hasn't been run) and PdfSummary row. One query
    #    over pdf_collections -> pdfs.
    rows = (
        await db.execute(
            select(Pdf.id, func.coalesce(Citation.doi, Pdf.doi), PdfSummary)
            .join(PdfCollection, PdfCollection.pdf_id == Pdf.id)
            .outerjoin(
                Citation,
                (Citation.pdf_id == Pdf.id) & (Citation.user_id == current_user.id),
            )
            .outerjoin(
                PdfSummary,
                (PdfSummary.pdf_id == Pdf.id) & (PdfSummary.user_id == current_user.id),
            )
            .where(
                PdfCollection.collection_id == collection_id,
                Pdf.user_id == current_user.id,
            )
        )
    ).all()

    paper_count = len(rows)
    members: list[tuple] = [(r[0], r[1], r[2]) for r in rows]
    summaries: dict[uuid.UUID, PdfSummary | None] = {pid: s for pid, _, s in members}

    # 2. Backfill: resolve DOIs that have no openalex_id yet (real id or
    #    sentinel), capped per request. Get-or-create the PdfSummary row so
    #    the result is cached across requests; status stays 'not_generated'.
    backfill_count = 0
    for pdf_id, doi, summary in members:
        if backfill_count >= settings.RECOMMENDATIONS_MAX_BACKFILL:
            break
        if not doi:
            continue
        if summary is not None and summary.openalex_id is not None:
            continue
        backfill_count += 1
        if summary is None:
            summary = PdfSummary(
                pdf_id=pdf_id,
                user_id=current_user.id,
                status="not_generated",
            )
            db.add(summary)
            summaries[pdf_id] = summary
        try:
            work = await openalex_client.fetch_work_by_doi(doi)
        except httpx.HTTPError:
            logger.warning(
                "OpenAlex lookup failed for pdf %s (doi %s); skipping",
                pdf_id,
                doi,
            )
            continue
        if work is None:
            summary.openalex_id = _OPENALEX_NOT_FOUND
        else:
            summary.openalex_id = work.openalex_id
            summary.referenced_openalex_ids = work.referenced_works
        await db.flush()
    await db.commit()

    # 3. Frequency map over referenced_works of every member, excluding works
    #    that are themselves members (by openalex_id or DOI) and below the
    #    min-citing threshold.
    member_openalex_ids = {
        s.openalex_id
        for s in summaries.values()
        if s and s.openalex_id and s.openalex_id != _OPENALEX_NOT_FOUND
    }
    member_dois = {doi.lower() for _, doi, _ in members if doi}

    counter: Counter = Counter()
    with_refs_count = 0
    no_doi_count = 0
    for pdf_id, doi, _ in members:
        if not doi:
            no_doi_count += 1
            continue
        summary = summaries.get(pdf_id)
        refs = (summary.referenced_openalex_ids if summary else None) or []
        if refs:
            with_refs_count += 1
        for ref in refs:
            if ref in member_openalex_ids:
                continue
            counter[ref] += 1

    top = [
        (wid, k)
        for wid, k in counter.most_common()
        if k >= settings.RECOMMENDATIONS_MIN_CITING
    ][: settings.RECOMMENDATIONS_MAX_RESULTS]

    # 4. Batch-resolve display metadata for the top suggested ids, ordered by
    #    the counter ranking; drop any that fail to resolve or that match a
    #    member's DOI.
    works = await openalex_client.fetch_works_batch([wid for wid, _ in top])
    works_by_id = {w.openalex_id: w for w in works}
    ranked: list[tuple] = []
    for wid, k in top:
        w = works_by_id.get(wid)
        if w is None:
            continue
        if w.doi and w.doi.lower() in member_dois:
            continue
        ranked.append((w, k))

    # 5. Response — EXACTLY this shape (frontend types depend on it).
    return {
        "suggestions": [
            {
                "openalex_id": w.openalex_id,
                "title": w.title,
                "authors": w.authors,
                "year": w.year,
                "doi": w.doi,
                "cited_by_count": k,
            }
            for w, k in ranked
        ],
        "papers_total": paper_count,
        "papers_with_refs": with_refs_count,
        "papers_without_doi": no_doi_count,
    }
