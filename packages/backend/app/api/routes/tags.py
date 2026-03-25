import logging
import uuid
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.db.models import Pdf, PdfTag, Tag, User
from app.schemas.tag import TagCreate, TagResponse, TagUpdate
from app.utils.db_utils import handle_unique_violation

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("", response_model=TagResponse)
async def create_tag(
    tag_in: TagCreate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Create a new tag."""
    tag = Tag(
        user_id=current_user.id,
        name=tag_in.name,
        color=tag_in.color
    )
    db.add(tag)
    async with handle_unique_violation(
        db,
        "Tag with this name already exists",
        logger,
        {"user_id": str(current_user.id), "tag_name": tag_in.name},
    ):
        await db.flush()
        await db.refresh(tag)
        await db.commit()
    return tag

@router.get("", response_model=List[TagResponse])
async def list_tags(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """List all tags for the user."""
    query = select(Tag).where(Tag.user_id == current_user.id).order_by(Tag.name)
    result = await db.execute(query)
    return result.scalars().all()

@router.patch("/{tag_id}", response_model=TagResponse)
async def update_tag(
    tag_id: uuid.UUID,
    tag_in: TagUpdate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Update a tag."""
    tag = await db.get(Tag, tag_id)
    if not tag or tag.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Tag not found")
        
    update_data = tag_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tag, field, value)

    db.add(tag)
    async with handle_unique_violation(
        db,
        "Tag with this name already exists",
        logger,
        {"user_id": str(current_user.id), "tag_id": str(tag_id), "new_name": tag_in.name},
    ):
        await db.flush()
        await db.refresh(tag)
        await db.commit()
    return tag

@router.delete("/{tag_id}")
async def delete_tag(
    tag_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Delete a tag."""
    tag = await db.get(Tag, tag_id)
    if not tag or tag.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Tag not found")
        
    await db.delete(tag)
    await db.commit()
    return {"message": "Tag successfully deleted"}

@router.post("/pdfs/{pdf_id}/tags/{tag_id}")
async def add_tag_to_pdf(
    pdf_id: uuid.UUID,
    tag_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Add a tag to a PDF."""
    tag = await db.get(Tag, tag_id)
    if not tag or tag.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Tag not found")
        
    pdf = await db.get(Pdf, pdf_id)
    if not pdf or pdf.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="PDF not found")
        
    pdf_tag = PdfTag(pdf_id=pdf_id, tag_id=tag_id)
    db.add(pdf_tag)

    async with handle_unique_violation(
        db,
        "Tag is already assigned to this PDF",
        logger,
        {"user_id": str(current_user.id), "pdf_id": str(pdf_id), "tag_id": str(tag_id)},
    ):
        await db.commit()

    return {"message": "Tag added to PDF"}

@router.delete("/pdfs/{pdf_id}/tags/{tag_id}")
async def remove_tag_from_pdf(
    pdf_id: uuid.UUID,
    tag_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Remove a tag from a PDF."""
    # Verify ownership of both the PDF and the tag
    tag = await db.get(Tag, tag_id)
    if not tag or tag.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Tag not found")

    pdf = await db.get(Pdf, pdf_id)
    if not pdf or pdf.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="PDF not found")

    pdf_tag = await db.get(PdfTag, (pdf_id, tag_id))
    if not pdf_tag:
        raise HTTPException(status_code=404, detail="Tag is not assigned to this PDF")

    await db.delete(pdf_tag)
    await db.commit()
    return {"message": "Tag removed from PDF"}
