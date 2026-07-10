import logging
import re
import uuid
from collections import Counter
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.db.models import Collection, Pdf, PdfCollection, User, Citation, PdfIndexStatus
from app.schemas.collection import (
    CollectionCreate,
    CollectionResponse,
    CollectionUpdate,
)
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

    if pdf_ids:
        citation_rows = await db.execute(
            select(Citation).where(Citation.pdf_id.in_(pdf_ids))
        )
        citations = citation_rows.scalars().all()

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

    return {
        "paper_count": paper_count,
        "indexed_count": indexed_count,
        "year_distribution": year_distribution,
        "top_authors": top_authors,
        "recent_papers": recent_papers,
    }
