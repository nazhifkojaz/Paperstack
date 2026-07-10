import logging
import re
from typing import Optional
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.db.models import User, Pdf, Citation
from app.schemas.citation import (
    CitationResponse,
    CitationUpdate,
    BulkExportRequest,
    LookupRequest,
    LookupResponse,
    ValidateRequest,
)
from app.services import citation_extractor

logger = logging.getLogger(__name__)

router = APIRouter()
global_router = APIRouter()

# Fields whose manual edit should trigger bibtex regeneration (when no
# explicit bibtex is provided in the same request).
_META_FIELDS = {"title", "authors", "year", "doi"}


def _regenerate_bibtex_skeleton(
    title: Optional[str],
    authors: Optional[str],
    year: Optional[int],
    doi: Optional[str],
) -> str:
    """Build a clean skeleton BibTeX entry from merged citation fields.

    Used when the user edits title/authors/year/doi without touching bibtex,
    so the stored bibtex (what export emits) stays in sync with the fields.
    """
    first_author_last = authors.split(",")[0].split()[-1] if authors else "unknown"
    key = re.sub(r"[^a-zA-Z0-9]", "", first_author_last)
    if year:
        key = f"{key}{year}"
    entry = f"@article{{{key},\n"
    if title:
        entry += f"  title  = {{{title}}},\n"
    if authors:
        entry += f"  author = {{{authors}}},\n"
    if year:
        entry += f"  year   = {{{year}}},\n"
    if doi:
        entry += f"  doi    = {{{doi}}},\n"
    entry += "}"
    return entry


@router.get("/{pdf_id}/citation", response_model=CitationResponse)
async def get_citation(
    pdf_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(Citation).where(
        Citation.pdf_id == pdf_id, Citation.user_id == current_user.id
    )
    result = await db.execute(stmt)
    citation = result.scalar_one_or_none()
    if not citation:
        raise HTTPException(status_code=404, detail="Citation not found")
    return citation


@router.put("/{pdf_id}/citation", response_model=CitationResponse)
async def create_or_update_citation(
    pdf_id: UUID,
    citation_in: CitationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Verify PDF exists and belongs to user
    stmt_pdf = select(Pdf).where(Pdf.id == pdf_id, Pdf.user_id == current_user.id)
    if not (await db.execute(stmt_pdf)).scalar_one_or_none():
        raise HTTPException(status_code=404, detail="PDF not found")

    stmt = select(Citation).where(
        Citation.pdf_id == pdf_id, Citation.user_id == current_user.id
    )
    result = await db.execute(stmt)
    citation = result.scalar_one_or_none()

    update_data = citation_in.model_dump(exclude_unset=True)

    if citation:
        # Update existing
        for field, value in update_data.items():
            setattr(citation, field, value)

        # When meta fields changed but no explicit bibtex was provided,
        # regenerate a skeleton bibtex entry from the merged fields so the
        # stored bibtex (used by export) stays consistent. If the user
        # provided explicit bibtex, it is always respected as-is.
        if "bibtex" not in update_data and (_META_FIELDS & update_data.keys()):
            citation.bibtex = _regenerate_bibtex_skeleton(
                title=citation.title,
                authors=citation.authors,
                year=citation.year,
                doi=citation.doi,
            )
            citation.source = "manual"
    else:
        # Create new - ensure bibtex is provided for new citations
        if not update_data.get("bibtex"):
            update_data["bibtex"] = _regenerate_bibtex_skeleton(
                title=update_data.get("title"),
                authors=update_data.get("authors"),
                year=update_data.get("year"),
                doi=update_data.get("doi"),
            )

        citation = Citation(
            id=uuid4(), pdf_id=pdf_id, user_id=current_user.id, **update_data
        )
        db.add(citation)

    await db.commit()
    await db.refresh(citation)
    return citation


@router.post("/{pdf_id}/citation/auto", response_model=CitationResponse)
async def auto_extract_citation(
    pdf_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt_pdf = select(Pdf).where(Pdf.id == pdf_id, Pdf.user_id == current_user.id)
    pdf = (await db.execute(stmt_pdf)).scalar_one_or_none()
    if not pdf:
        raise HTTPException(status_code=404, detail="PDF not found")

    # Download raw PDF bytes (storage backend for stored PDFs, direct URL for linked PDFs)
    try:
        if pdf.source_url and not pdf.github_sha and not pdf.drive_file_id:
            async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
                response = await client.get(pdf.source_url)
                response.raise_for_status()
                pdf_bytes = response.content
        else:
            from app.services.storage.factory import get_storage_backend

            backend = await get_storage_backend(current_user, db)
            file_id = pdf.drive_file_id or pdf.github_sha
            pdf_bytes = await backend.download_bytes(file_id, pdf.filename)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Could not fetch linked PDF: {e}")
    except Exception:
        logger.exception(
            "Failed to fetch PDF bytes for citation extraction, pdf_id=%s", pdf_id
        )
        raise HTTPException(status_code=502, detail="Could not fetch PDF")

    extracted = await citation_extractor.auto_extract_citation(
        pdf_bytes=pdf_bytes,
        doi_hint=pdf.doi,
    )

    stmt = select(Citation).where(
        Citation.pdf_id == pdf_id, Citation.user_id == current_user.id
    )
    citation = (await db.execute(stmt)).scalar_one_or_none()

    if citation:
        for field, value in extracted.items():
            setattr(citation, field, value)
    else:
        citation = Citation(
            pdf_id=pdf_id,
            user_id=current_user.id,
            **extracted,
        )
        db.add(citation)

    await db.commit()
    await db.refresh(citation)
    return citation


def _build_bibtex_export(citations: list[Citation]) -> str:
    """Build a BibTeX export string from a list of Citation objects.

    Shared by the bulk export route and the collection export route.
    """
    return "\n\n".join([c.bibtex for c in citations if c.bibtex])


@global_router.post("/export")
async def export_citations(
    export_req: BulkExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(Citation).where(
        Citation.pdf_id.in_(export_req.pdf_ids), Citation.user_id == current_user.id
    )
    result = await db.execute(stmt)
    citations = result.scalars().all()

    if not citations:
        raise HTTPException(
            status_code=404, detail="No citations found for the provided PDFs"
        )

    if export_req.format.lower() == "bibtex":
        export_text = _build_bibtex_export(citations)
        return Response(
            content=export_text,
            media_type="text/plain",
            headers={"Content-Disposition": "attachment; filename=export.bib"},
        )

    # Optional extensions for JSON etc.
    raise HTTPException(status_code=400, detail="Unsupported format")


@global_router.post("/validate")
async def validate_citations(
    validate_req: ValidateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Find all citations for the requested PDFs
    stmt = select(Citation).where(
        Citation.pdf_id.in_(validate_req.pdf_ids), Citation.user_id == current_user.id
    )
    result = await db.execute(stmt)
    citations = result.scalars().all()

    # Separate PDFs with and without citations
    has_citation_ids = {c.pdf_id for c in citations}
    has_citation = [str(pid) for pid in validate_req.pdf_ids if pid in has_citation_ids]
    missing = [str(pid) for pid in validate_req.pdf_ids if pid not in has_citation_ids]

    return {"has_citation": has_citation, "missing": missing}


@global_router.post("/lookup", response_model=LookupResponse)
async def lookup_citation(
    lookup_req: LookupRequest, current_user: User = Depends(get_current_user)
) -> LookupResponse:
    """Lookup citation by DOI or ISBN.

    Returns citation metadata without storing to database.
    Use PUT /pdfs/{pdf_id}/citation to save the result.
    """
    # Strip and validate input
    doi = (lookup_req.doi or "").strip()
    isbn = (lookup_req.isbn or "").strip()

    if not doi and not isbn:
        raise HTTPException(status_code=400, detail="Must provide doi or isbn")

    if doi and isbn:
        raise HTTPException(status_code=400, detail="Provide only one: doi or isbn")

    # Route to appropriate lookup
    if doi:
        try:
            result = await citation_extractor.lookup_doi_crossref(doi)
            # Ensure isbn is None for DOI lookups
            result.setdefault("isbn", None)
            result.setdefault("doi", doi)
            return LookupResponse(**result)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise HTTPException(status_code=404, detail="DOI not found")
            raise HTTPException(status_code=502, detail="CrossRef service unavailable")

    if isbn:
        try:
            result = await citation_extractor.lookup_isbn_openlibrary(isbn)
            # Ensure doi is None for ISBN lookups
            result.setdefault("doi", None)
            result.setdefault("isbn", isbn)
            return LookupResponse(**result)
        except citation_extractor.CitationNotFoundError:
            raise HTTPException(status_code=404, detail="ISBN not found")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except httpx.HTTPStatusError:
            raise HTTPException(
                status_code=502, detail="Open Library service unavailable"
            )
