from typing import Any, List
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_user
from app.db.models import User, AnnotationSet, Annotation, Pdf
from app.schemas.annotation import (
    AnnotationSetCreate, AnnotationSetUpdate, AnnotationSetResponse,
    AnnotationCreate, AnnotationUpdate, AnnotationResponse
)

router = APIRouter()

# --- Annotation Sets ---

@router.get("/sets", response_model=List[AnnotationSetResponse])
async def list_annotation_sets(
    pdf_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    # First verify user has access to this PDF
    pdf = await db.scalar(select(Pdf).where(Pdf.id == pdf_id, Pdf.user_id == current_user.id))
    if not pdf:
        raise HTTPException(status_code=404, detail="PDF not found")
        
    result = await db.scalars(
        select(AnnotationSet)
        .where(AnnotationSet.pdf_id == pdf_id, AnnotationSet.user_id == current_user.id)
        .order_by(AnnotationSet.created_at.desc())
    )
    return result.all()

@router.post("/sets", response_model=AnnotationSetResponse, status_code=status.HTTP_201_CREATED)
async def create_annotation_set(
    set_in: AnnotationSetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    pdf = await db.scalar(select(Pdf).where(Pdf.id == set_in.pdf_id, Pdf.user_id == current_user.id))
    if not pdf:
        raise HTTPException(status_code=404, detail="PDF not found")
        
    db_set = AnnotationSet(
        id=uuid4(),  # Generate ID in Python for SQLite compatibility
        pdf_id=set_in.pdf_id,
        user_id=current_user.id,
        name=set_in.name,
        color=set_in.color
    )
    db.add(db_set)
    await db.commit()
    await db.refresh(db_set)
    return db_set

@router.patch("/sets/{set_id}", response_model=AnnotationSetResponse)
async def update_annotation_set(
    set_id: UUID,
    set_in: AnnotationSetUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    db_set = await db.scalar(
        select(AnnotationSet).where(AnnotationSet.id == set_id, AnnotationSet.user_id == current_user.id)
    )
    if not db_set:
        raise HTTPException(status_code=404, detail="Annotation set not found")
        
    update_data = set_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_set, field, value)
        
    await db.commit()
    await db.refresh(db_set)
    return db_set

@router.delete("/sets/{set_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_annotation_set(
    set_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    db_set = await db.scalar(
        select(AnnotationSet).where(AnnotationSet.id == set_id, AnnotationSet.user_id == current_user.id)
    )
    if not db_set:
        raise HTTPException(status_code=404, detail="Annotation set not found")
        
    await db.delete(db_set)
    await db.commit()

# --- Annotations ---

@router.get("/sets/{set_id}/items", response_model=List[AnnotationResponse])
async def list_annotations(
    set_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    # Verify set ownership
    db_set = await db.scalar(
        select(AnnotationSet).where(AnnotationSet.id == set_id, AnnotationSet.user_id == current_user.id)
    )
    if not db_set:
        raise HTTPException(status_code=404, detail="Annotation set not found")
        
    result = await db.scalars(
        select(Annotation).where(Annotation.set_id == set_id)
    )
    return result.all()

@router.post("/items", response_model=AnnotationResponse, status_code=status.HTTP_201_CREATED)
async def create_annotation(
    ann_in: AnnotationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    # Verify set ownership
    db_set = await db.scalar(
        select(AnnotationSet).where(AnnotationSet.id == ann_in.set_id, AnnotationSet.user_id == current_user.id)
    )
    if not db_set:
        raise HTTPException(status_code=404, detail="Annotation set not found")
        
    db_ann = Annotation(
        id=uuid4(),  # Generate ID in Python for SQLite compatibility
        set_id=ann_in.set_id,
        page_number=ann_in.page_number,
        type=ann_in.type,
        rects=ann_in.rects,
        selected_text=ann_in.selected_text,
        note_content=ann_in.note_content,
        color=ann_in.color
    )
    db.add(db_ann)
    await db.commit()
    await db.refresh(db_ann)
    return db_ann

@router.patch("/items/{ann_id}", response_model=AnnotationResponse)
async def update_annotation(
    ann_id: UUID,
    ann_in: AnnotationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    # Need to join with set to verify user ownership
    db_ann = await db.scalar(
        select(Annotation)
        .join(AnnotationSet)
        .where(Annotation.id == ann_id, AnnotationSet.user_id == current_user.id)
    )
    if not db_ann:
        raise HTTPException(status_code=404, detail="Annotation not found")
        
    update_data = ann_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_ann, field, value)
        
    await db.commit()
    await db.refresh(db_ann)
    return db_ann

@router.delete("/items/{ann_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_annotation(
    ann_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    db_ann = await db.scalar(
        select(Annotation)
        .join(AnnotationSet)
        .where(Annotation.id == ann_id, AnnotationSet.user_id == current_user.id)
    )
    if not db_ann:
        raise HTTPException(status_code=404, detail="Annotation not found")
        
    await db.delete(db_ann)
    await db.commit()
