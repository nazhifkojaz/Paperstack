import logging
import uuid
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.db.models import Collection, Pdf, PdfCollection, User
from app.schemas.collection import CollectionCreate, CollectionResponse, CollectionUpdate
from app.utils.db_utils import handle_unique_violation

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("", response_model=CollectionResponse)
async def create_collection(
    collection_in: CollectionCreate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Create a new collection."""
    if collection_in.parent_id:
        parent = await db.get(Collection, collection_in.parent_id)
        if not parent or parent.user_id != current_user.id:
            raise HTTPException(status_code=400, detail="Invalid parent collection")

    collection = Collection(
        user_id=current_user.id,
        name=collection_in.name,
        parent_id=collection_in.parent_id,
        position=collection_in.position
    )
    db.add(collection)
    await db.commit()
    await db.refresh(collection)
    return collection

@router.get("", response_model=List[CollectionResponse])
async def list_collections(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """List all collections for the user."""
    query = select(Collection).where(Collection.user_id == current_user.id).order_by(Collection.position)
    result = await db.execute(query)
    return result.scalars().all()

@router.patch("/{collection_id}", response_model=CollectionResponse)
async def update_collection(
    collection_id: uuid.UUID,
    collection_in: CollectionUpdate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Update a collection."""
    collection = await db.get(Collection, collection_id)
    if not collection or collection.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Collection not found")
        
    if collection_in.parent_id and collection_in.parent_id != collection.parent_id:
        parent = await db.get(Collection, collection_in.parent_id)
        if not parent or parent.user_id != current_user.id:
            raise HTTPException(status_code=400, detail="Invalid parent collection")

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
) -> Any:
    """Delete a collection."""
    collection = await db.get(Collection, collection_id)
    if not collection or collection.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Collection not found")
        
    await db.delete(collection)
    await db.commit()
    return {"message": "Collection successfully deleted"}

@router.post("/{collection_id}/pdfs")
async def add_pdf_to_collection(
    collection_id: uuid.UUID,
    pdf_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
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
) -> Any:
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
