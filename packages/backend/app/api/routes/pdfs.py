import uuid
from typing import List, Optional
import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Response, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, asc

from app.api import deps
from app.core.config import settings
from app.db.models import User, Pdf, PdfCollection, PdfTag, Collection, Annotation, AnnotationSet
from app.middleware.rate_limit import limiter
from app.schemas.pdf import PdfResponse, PdfUpdate, PdfListParams, PdfLinkCreate, PdfUrlCheckRequest, PdfUrlCheckResponse
from app.services import pdf_metadata
from app.services.storage.factory import get_storage_backend

router = APIRouter()


def _has_stored_content(pdf: Pdf) -> bool:
    """Return True if the PDF has content stored in a backend (GitHub or Drive)."""
    return bool(pdf.github_sha or pdf.drive_file_id)


def _storage_file_id(pdf: Pdf) -> Optional[str]:
    """Return the opaque file identifier for the PDF's storage backend."""
    return pdf.drive_file_id or pdf.github_sha


def _etag(pdf: Pdf) -> str:
    return f'"{_storage_file_id(pdf)}"'


@router.post("/upload", response_model=PdfResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    title: str = Form(...),
    doi: str = Form(None),
    isbn: str = Form(None),
    project_ids: str = Form(None),
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> PdfResponse:
    """Upload a new PDF to the user's active storage backend."""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    file_bytes = await file.read()
    filename = f"pdfs/{uuid.uuid4()}_{file.filename}"

    file_size = pdf_metadata.get_pdf_file_size(file_bytes)
    page_count = pdf_metadata.extract_page_count(file_bytes)

    backend = await get_storage_backend(current_user, db)
    await backend.ensure_container()
    result = await backend.upload(filename, file_bytes, title)

    pdf = Pdf(
        user_id=current_user.id,
        title=title,
        filename=filename,
        github_sha=result.file_id if result.provider == "github" else None,
        drive_file_id=result.file_id if result.provider == "google" else None,
        file_size=file_size,
        page_count=page_count,
        doi=doi,
        isbn=isbn,
    )
    db.add(pdf)

    if project_ids:
        try:
            parsed_ids = [uuid.UUID(pid.strip()) for pid in project_ids.split(",") if pid.strip()]
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid project_id format")
        if parsed_ids:
            stmt = select(Collection).where(
                Collection.id.in_(parsed_ids),
                Collection.user_id == current_user.id,
            )
            valid_collections = (await db.execute(stmt)).scalars().all()
            for collection in valid_collections:
                db.add(PdfCollection(pdf_id=pdf.id, collection_id=collection.id))

    await db.commit()
    await db.refresh(pdf)
    return pdf


@router.post("/check-url", response_model=PdfUrlCheckResponse)
@limiter.limit(settings.RATE_LIMIT_PDF_CHECK_URL)
async def check_pdf_url(
    request: Request,
    data: PdfUrlCheckRequest,
    current_user: User = Depends(deps.get_current_user),
) -> PdfUrlCheckResponse:
    """Validate a URL points to a viewable PDF before adding it."""
    url_str = str(data.url)

    # Phase 1: HEAD request to check reachability and content-type
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        try:
            head_resp = await client.head(url_str)
        except httpx.TimeoutException:
            return PdfUrlCheckResponse(valid=False, error="Server took too long to respond (timed out after 30 seconds).")
        except httpx.ConnectError:
            return PdfUrlCheckResponse(valid=False, error="Could not reach the server. Check the URL and try again.")
        except httpx.HTTPError as exc:
            return PdfUrlCheckResponse(valid=False, error=f"Failed to connect: {exc}")

        if head_resp.status_code != 200:
            return PdfUrlCheckResponse(valid=False, error=f"Server returned HTTP {head_resp.status_code}. The file may not exist at this URL.")

        content_type = head_resp.headers.get("content-type", "").lower()
        if "application/pdf" not in content_type and "application/x-pdf" not in content_type:
            return PdfUrlCheckResponse(
                valid=False,
                error=f"URL does not point to a PDF file (Content-Type: {content_type or 'unknown'})",
            )

        # Phase 2: GET to check CORS and extract metadata
        try:
            get_resp = await client.get(url_str)
        except httpx.HTTPError:
            return PdfUrlCheckResponse(valid=False, error="Failed to download the PDF content.")

        file_bytes = get_resp.content
        if not file_bytes.startswith(b"%PDF-"):
            return PdfUrlCheckResponse(valid=False, error="Content is not a valid PDF file.")

        # CORS check
        acao = get_resp.headers.get("access-control-allow-origin", "")
        cors_ok = acao == "*" or (acao and settings.FRONTEND_URL in acao)
        if not cors_ok:
            return PdfUrlCheckResponse(
                valid=False,
                cors_blocked=True,
                error="This PDF cannot be loaded directly in the browser due to server restrictions (CORS).",
                suggestions=[
                    "Download the PDF and upload it manually using the Upload tab",
                    "Find an alternative URL that allows cross-origin access",
                ],
            )

        # Extract metadata
        page_count = pdf_metadata.extract_page_count(file_bytes)
        file_size = len(file_bytes)
        title = pdf_metadata.extract_title_from_bytes(file_bytes)

        return PdfUrlCheckResponse(
            valid=True,
            page_count=page_count,
            file_size=file_size,
            title=title,
            cors_blocked=False,
        )


@router.post("/link", response_model=PdfResponse)
async def link_pdf(
    data: PdfLinkCreate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> PdfResponse:
    """Create a PDF entry from an external URL (no file upload/storage)."""
    pdf_id = uuid.uuid4()
    filename = f"linked/{pdf_id}"

    pdf = Pdf(
        id=pdf_id,
        user_id=current_user.id,
        title=data.title,
        filename=filename,
        source_url=str(data.source_url),
        github_sha=None,
        drive_file_id=None,
        file_size=None,
        page_count=None,
        doi=data.doi,
        isbn=data.isbn,
    )
    db.add(pdf)

    if data.project_ids:
        stmt = select(Collection).where(
            Collection.id.in_(data.project_ids),
            Collection.user_id == current_user.id,
        )
        valid_collections = (await db.execute(stmt)).scalars().all()
        for collection in valid_collections:
            db.add(PdfCollection(pdf_id=pdf_id, collection_id=collection.id))

    await db.commit()
    await db.refresh(pdf)
    return pdf


@router.get("", response_model=List[PdfResponse])
async def list_pdfs(
    params: PdfListParams = Depends(),
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> List[PdfResponse]:
    """List PDFs with filtering, sorting, and pagination."""
    query = select(Pdf).where(Pdf.user_id == current_user.id)

    if params.collection_id:
        query = query.join(PdfCollection).where(PdfCollection.collection_id == params.collection_id)

    if params.tag_id:
        query = query.join(PdfTag).where(PdfTag.tag_id == params.tag_id)

    if params.q:
        search = f"%{params.q}%"
        query = query.where(Pdf.title.ilike(search))

    sortable_cols = {'uploaded_at', 'updated_at', 'title', 'file_size', 'page_count'}
    col_name = params.sort.lstrip('-')
    if col_name not in sortable_cols:
        raise HTTPException(status_code=400, detail=f"Invalid sort field: {col_name}")
    order_col = desc(getattr(Pdf, col_name)) if params.sort.startswith("-") else asc(getattr(Pdf, col_name))

    query = query.order_by(order_col)
    offset = (params.page - 1) * params.per_page
    query = query.offset(offset).limit(params.per_page)

    return (await db.execute(query)).scalars().all()


@router.get("/{pdf_id}", response_model=PdfResponse)
async def get_pdf(
    pdf_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> PdfResponse:
    """Get a specific PDF by ID."""
    pdf = await db.get(Pdf, pdf_id)
    if not pdf or pdf.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="PDF not found")
    return pdf


@router.patch("/{pdf_id}", response_model=PdfResponse)
async def update_pdf(
    pdf_id: uuid.UUID,
    pdf_in: PdfUpdate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> PdfResponse:
    """Update a PDF's metadata."""
    pdf = await db.get(Pdf, pdf_id)
    if not pdf or pdf.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="PDF not found")

    for field, value in pdf_in.model_dump(exclude_unset=True).items():
        setattr(pdf, field, value)

    db.add(pdf)
    await db.commit()
    await db.refresh(pdf)
    return pdf


@router.delete("/{pdf_id}")
async def delete_pdf(
    pdf_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> dict[str, str]:
    """Delete a PDF from both the database and its storage backend."""
    pdf = await db.get(Pdf, pdf_id)
    if not pdf or pdf.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="PDF not found")

    if _has_stored_content(pdf):
        backend = await get_storage_backend(current_user, db)
        await backend.delete(_storage_file_id(pdf), pdf.filename)

    await db.delete(pdf)
    await db.commit()
    return {"message": "PDF successfully deleted"}


@router.get("/{pdf_id}/content")
async def get_pdf_content(
    pdf_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Response:
    """Fetch raw PDF content from the user's storage backend.

    Uses ETag caching based on the storage file identifier.
    """
    pdf = await db.get(Pdf, pdf_id)
    if not pdf or pdf.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="PDF not found")

    if not _has_stored_content(pdf):
        raise HTTPException(status_code=400, detail="This PDF is URL-linked and has no stored content")

    etag = _etag(pdf)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)

    backend = await get_storage_backend(current_user, db)
    pdf_bytes = await backend.download_bytes(_storage_file_id(pdf), pdf.filename)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"ETag": etag, "Cache-Control": "private, max-age=3600"},
    )


@router.get("/{pdf_id}/collections")
async def get_pdf_collections(
    pdf_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> dict[str, list[str]]:
    """Get all collections a PDF belongs to."""
    pdf = await db.get(Pdf, pdf_id)
    if not pdf or pdf.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="PDF not found")

    result = await db.execute(
        select(PdfCollection.collection_id).where(PdfCollection.pdf_id == pdf_id)
    )
    return {"collection_ids": [str(row[0]) for row in result.fetchall()]}


@router.get("/{pdf_id}/export-annotated")
async def export_annotated_pdf(
    pdf_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Response:
    """Fetch the PDF, overlay annotations, and return the baked PDF."""
    pdf = await db.get(Pdf, pdf_id)
    if not pdf or pdf.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="PDF not found")

    if not _has_stored_content(pdf):
        raise HTTPException(status_code=400, detail="Cannot export annotated PDF for URL-linked documents")

    result = await db.execute(
        select(Annotation.page_number, Annotation.type, Annotation.rects, Annotation.color, AnnotationSet.color.label('set_color'))
        .join(AnnotationSet)
        .where(AnnotationSet.pdf_id == pdf_id, AnnotationSet.user_id == current_user.id)
    )
    db_annotations = result.fetchall()

    annotations_list = [
        {'page_number': ann.page_number, 'type': ann.type, 'rects': ann.rects, 'color': ann.color or ann.set_color}
        for ann in db_annotations
    ]

    backend = await get_storage_backend(current_user, db)
    pdf_bytes = await backend.download_bytes(_storage_file_id(pdf), pdf.filename)

    if not annotations_list:
        return Response(content=pdf_bytes, media_type="application/pdf")

    from app.services import pdf_annotator
    try:
        annotated_bytes = pdf_annotator.export_annotated_pdf(pdf_bytes, annotations_list)
        return Response(
            content=annotated_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="annotated_{pdf.filename.split("/")[-1]}"'},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export annotated PDF: {str(e)}")
