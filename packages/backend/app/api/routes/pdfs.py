import uuid
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Response, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, asc

from app.api import deps
from app.db.models import User, Pdf, PdfCollection, PdfTag, Collection
from app.schemas.pdf import PdfResponse, PdfUpdate, PdfListParams, PdfLinkCreate
from app.services import github_repo, pdf_metadata

router = APIRouter()

@router.post("/upload", response_model=PdfResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    title: str = Form(...),
    doi: str = Form(None),
    isbn: str = Form(None),
    project_ids: str = Form(None),
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Upload a new PDF.
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    file_bytes = await file.read()

    # Check if we have the github repo created
    if not current_user.repo_created:
        await github_repo.ensure_user_repo(current_user.access_token, current_user.github_login)
        current_user.repo_created = True
        db.add(current_user)
        # We will commit this down below

    # Check for existing filename in DB to avoid Github conflicts
    filename = f"pdfs/{uuid.uuid4()}_{file.filename}"

    # Extract metadata
    file_size = pdf_metadata.get_pdf_file_size(file_bytes)
    page_count = pdf_metadata.extract_page_count(file_bytes)

    # Upload to GitHub
    gh_resp = await github_repo.upload_pdf_to_github(
        current_user.access_token,
        current_user.github_login,
        filename,
        file_bytes,
        f"Add {title}"
    )

    github_sha = gh_resp.get("content", {}).get("sha")

    # Save to database
    pdf = Pdf(
        id=uuid.uuid4(),
        user_id=current_user.id,
        title=title,
        filename=filename,
        github_sha=github_sha,
        file_size=file_size,
        page_count=page_count,
        doi=doi,
        isbn=isbn
    )

    db.add(pdf)

    # Add to projects if specified
    if project_ids:
        try:
            parsed_ids = [uuid.UUID(pid.strip()) for pid in project_ids.split(",") if pid.strip()]
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid project_id format")
        for pid in parsed_ids:
            collection = await db.get(Collection, pid)
            if collection and collection.user_id == current_user.id:
                db.add(PdfCollection(pdf_id=pdf.id, collection_id=pid))

    await db.commit()
    await db.refresh(pdf)

    return pdf

@router.post("/link", response_model=PdfResponse)
async def link_pdf(
    data: PdfLinkCreate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Create a PDF entry from an external URL (no file upload/storage).
    """
    pdf_id = uuid.uuid4()
    filename = f"linked/{pdf_id}"

    pdf = Pdf(
        id=pdf_id,
        user_id=current_user.id,
        title=data.title,
        filename=filename,
        source_url=str(data.source_url),
        github_sha=None,
        file_size=None,
        page_count=None,
        doi=data.doi,
        isbn=data.isbn
    )

    db.add(pdf)

    # Add to projects if specified
    if data.project_ids:
        for pid in data.project_ids:
            collection = await db.get(Collection, pid)
            if collection and collection.user_id == current_user.id:
                db.add(PdfCollection(pdf_id=pdf_id, collection_id=pid))

    await db.commit()
    await db.refresh(pdf)

    return pdf

@router.get("", response_model=List[PdfResponse])
async def list_pdfs(
    params: PdfListParams = Depends(),
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    List PDFs with filtering, sorting, and pagination.
    """
    query = select(Pdf).where(Pdf.user_id == current_user.id)

    if params.collection_id:
        query = query.join(PdfCollection).where(PdfCollection.collection_id == params.collection_id)

    if params.tag_id:
        query = query.join(PdfTag).where(PdfTag.tag_id == params.tag_id)

    if params.q:
        search = f"%{params.q}%"
        query = query.where(Pdf.title.ilike(search))

    # Sorting
    sortable_cols = {'uploaded_at', 'updated_at', 'title', 'file_size', 'page_count'}
    col_name = params.sort.lstrip('-')
    if col_name not in sortable_cols:
        raise HTTPException(status_code=400, detail=f"Invalid sort field: {col_name}")
    if params.sort.startswith("-"):
        order_col = desc(getattr(Pdf, col_name))
    else:
        order_col = asc(getattr(Pdf, col_name))

    query = query.order_by(order_col)

    # Pagination
    offset = (params.page - 1) * params.per_page
    query = query.offset(offset).limit(params.per_page)

    result = await db.execute(query)
    return result.scalars().all()

@router.get("/{pdf_id}", response_model=PdfResponse)
async def get_pdf(
    pdf_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get a specific PDF by ID.
    """
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
) -> Any:
    """
    Update a PDF's metadata.
    """
    pdf = await db.get(Pdf, pdf_id)
    if not pdf or pdf.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="PDF not found")

    update_data = pdf_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
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
) -> Any:
    """
    Delete a PDF (both from database and GitHub).
    """
    pdf = await db.get(Pdf, pdf_id)
    if not pdf or pdf.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="PDF not found")

    if pdf.github_sha:
        # Delete from GitHub
        await github_repo.delete_pdf_from_github(
            current_user.access_token,
            current_user.github_login,
            pdf.filename,
            pdf.github_sha,
            f"Delete {pdf.title}"
        )

    await db.delete(pdf)
    await db.commit()
    return {"message": "PDF successfully deleted"}

@router.get("/{pdf_id}/content")
async def get_pdf_content(
    pdf_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Fetch the raw PDF content from GitHub.
    Uses ETag for caching based on the PDF's GitHub SHA.
    """
    pdf = await db.get(Pdf, pdf_id)
    if not pdf or pdf.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="PDF not found")

    if not pdf.github_sha:
        raise HTTPException(status_code=400, detail="This PDF is URL-linked and has no stored content")

    # ETag Implementation
    etag = f'"{pdf.github_sha}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)

    pdf_bytes = await github_repo.download_pdf_from_github(
        current_user.access_token,
        current_user.github_login,
        pdf.filename
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "ETag": etag,
            "Cache-Control": "private, max-age=3600"
        }
    )


@router.get("/{pdf_id}/collections")
async def get_pdf_collections(
    pdf_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get all collections a PDF belongs to.
    """
    pdf = await db.get(Pdf, pdf_id)
    if not pdf or pdf.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="PDF not found")

    result = await db.execute(
        select(PdfCollection.collection_id).where(PdfCollection.pdf_id == pdf_id)
    )
    collection_ids = [str(row[0]) for row in result.fetchall()]
    return {"collection_ids": collection_ids}


@router.get("/{pdf_id}/export-annotated")
async def export_annotated_pdf(
    pdf_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Fetch the PDF, overlay annotations, and return the baked PDF.
    """
    pdf = await db.get(Pdf, pdf_id)
    if not pdf or pdf.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="PDF not found")

    if not pdf.github_sha:
        raise HTTPException(status_code=400, detail="Cannot export annotated PDF for URL-linked documents")

    # Get annotations
    from app.db.models import Annotation, AnnotationSet
    # Fetch all annotations for this PDF that belong to the current user
    result = await db.execute(
        select(Annotation.page_number, Annotation.type, Annotation.rects, Annotation.color, AnnotationSet.color.label('set_color'))
        .join(AnnotationSet)
        .where(AnnotationSet.pdf_id == pdf_id, AnnotationSet.user_id == current_user.id)
    )
    db_annotations = result.fetchall()

    # Format for service
    annotations_list = []
    for ann in db_annotations:
        annotations_list.append({
            'page_number': ann.page_number,
            'type': ann.type,
            'rects': ann.rects,
            'color': ann.color or ann.set_color
        })

    pdf_bytes = await github_repo.download_pdf_from_github(
        current_user.access_token,
        current_user.github_login,
        pdf.filename
    )

    if not annotations_list:
        return Response(content=pdf_bytes, media_type="application/pdf")

    from app.services import pdf_annotator
    try:
        annotated_bytes = pdf_annotator.export_annotated_pdf(pdf_bytes, annotations_list)
        return Response(
            content=annotated_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="annotated_{pdf.filename.split("/")[-1]}"'}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export annotated PDF: {str(e)}")
