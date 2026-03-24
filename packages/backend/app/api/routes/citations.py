from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import httpx

from app.api.deps import get_db, get_current_user
from app.db.models import User, Pdf, Citation
from app.schemas.citation import CitationResponse, CitationCreate, CitationUpdate, BulkExportRequest, LookupRequest, LookupResponse, ValidateRequest
from app.services import citation_extractor
from app.services.github_repo import download_pdf_from_github

router = APIRouter()
global_router = APIRouter()

@router.get("/{pdf_id}/citation", response_model=CitationResponse)
async def get_citation(
    pdf_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(Citation).where(Citation.pdf_id == pdf_id, Citation.user_id == current_user.id)
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

    stmt = select(Citation).where(Citation.pdf_id == pdf_id, Citation.user_id == current_user.id)
    result = await db.execute(stmt)
    citation = result.scalar_one_or_none()

    update_data = citation_in.model_dump(exclude_unset=True)

    if citation:
        # Update existing
        for field, value in update_data.items():
            setattr(citation, field, value)
    else:
        # Create new - ensure bibtex is provided for new citations
        if not update_data.get("bibtex"):
            # Generate minimal bibtex if not provided
            title = update_data.get("title", "Unknown")
            authors = update_data.get("authors", "Unknown")
            update_data["bibtex"] = f"@misc{{auto,\n  title = {{{title}}},\n  author = {{{authors}}},\n}}"

        citation = Citation(
            id=uuid4(),
            pdf_id=pdf_id,
            user_id=current_user.id,
            **update_data
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
    # 1. Fetch PDF metadata from DB
    stmt_pdf = select(Pdf).where(Pdf.id == pdf_id, Pdf.user_id == current_user.id)
    pdf = (await db.execute(stmt_pdf)).scalar_one_or_none()
    if not pdf:
        raise HTTPException(status_code=404, detail="PDF not found")

    # 2. Download raw PDF bytes (GitHub for stored PDFs, direct URL for linked PDFs)
    try:
        if pdf.source_url and not pdf.github_sha:
            async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
                response = await client.get(pdf.source_url)
                response.raise_for_status()
                pdf_bytes = response.content
        else:
            pdf_bytes = await download_pdf_from_github(
                access_token=current_user.access_token,
                github_login=current_user.github_login,
                filepath=pdf.filename,
            )
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Could not fetch linked PDF: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not fetch PDF: {e}")

    # 3. Run the citation extraction pipeline
    extracted = await citation_extractor.auto_extract_citation(
        pdf_bytes=pdf_bytes,
        doi_hint=pdf.doi,
    )

    # 4. Upsert in DB
    stmt = select(Citation).where(Citation.pdf_id == pdf_id, Citation.user_id == current_user.id)
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

@global_router.post("/export")
async def export_citations(
    export_req: BulkExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(Citation).where(
        Citation.pdf_id.in_(export_req.pdf_ids), 
        Citation.user_id == current_user.id
    )
    result = await db.execute(stmt)
    citations = result.scalars().all()
    
    if not citations:
        raise HTTPException(status_code=404, detail="No citations found for the provided PDFs")
        
    if export_req.format.lower() == "bibtex":
        export_text = "\n\n".join([c.bibtex for c in citations if c.bibtex])
        return Response(content=export_text, media_type="text/plain", headers={"Content-Disposition": "attachment; filename=export.bib"})
    
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
        Citation.pdf_id.in_(validate_req.pdf_ids),
        Citation.user_id == current_user.id
    )
    result = await db.execute(stmt)
    citations = result.scalars().all()

    # Separate PDFs with and without citations
    has_citation_ids = {c.pdf_id for c in citations}
    has_citation = [str(pid) for pid in validate_req.pdf_ids if pid in has_citation_ids]
    missing = [str(pid) for pid in validate_req.pdf_ids if pid not in has_citation_ids]

    return {
        "has_citation": has_citation,
        "missing": missing
    }

@global_router.post("/lookup", response_model=LookupResponse)
async def lookup_citation(
    lookup_req: LookupRequest,
    current_user: User = Depends(get_current_user)
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
            raise HTTPException(status_code=502, detail="Open Library service unavailable")
