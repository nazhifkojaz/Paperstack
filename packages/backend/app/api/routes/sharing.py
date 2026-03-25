import secrets
from uuid import UUID, uuid4
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, get_current_user
from app.db.models import User, Share, AnnotationSet, Annotation, Pdf
from app.services import github_repo
from app.schemas.sharing import (
    ShareCreate, ShareResponse, SharedAnnotationsResponse,
    AnnotationSetData, AnnotationData,
)

# Two routers: authenticated actions + public access
router = APIRouter(tags=["sharing"])
public_router = APIRouter(tags=["sharing"])


# ────────────────────────────────────────────────────────────
# Authenticated routes
# ────────────────────────────────────────────────────────────

@router.post("/annotation-sets/{set_id}/share", response_model=ShareResponse)
async def create_share(
    set_id: UUID,
    share_in: ShareCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Share an annotation set — optionally with a specific GitHub user, or as a public link."""
    # Verify the set belongs to the current user
    stmt = select(AnnotationSet).where(
        AnnotationSet.id == set_id,
        AnnotationSet.user_id == current_user.id,
    )
    annotation_set = (await db.execute(stmt)).scalar_one_or_none()
    if not annotation_set:
        raise HTTPException(status_code=404, detail="Annotation set not found")

    # Resolve shared_with user if a GitHub login was provided
    shared_with_id: Optional[UUID] = None
    if share_in.shared_with_github_login:
        stmt_user = select(User).where(
            User.github_login == share_in.shared_with_github_login
        )
        target_user = (await db.execute(stmt_user)).scalar_one_or_none()
        if not target_user:
            raise HTTPException(
                status_code=404,
                detail=f"User '{share_in.shared_with_github_login}' not found in Paperstack",
            )
        shared_with_id = target_user.id

    token = secrets.token_urlsafe(32)
    share = Share(
        id=uuid4(),  # Generate ID in Python for SQLite compatibility
        annotation_set_id=set_id,
        shared_by=current_user.id,
        shared_with=shared_with_id,
        share_token=token,
        permission=share_in.permission,
    )
    db.add(share)
    await db.commit()
    await db.refresh(share)
    return share


@router.get("/shared/with-me", response_model=List[ShareResponse])
async def shared_with_me(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all annotation sets that have been shared with the current user."""
    stmt = select(Share).where(Share.shared_with == current_user.id)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.delete("/shares/{share_id}", status_code=204)
async def revoke_share(
    share_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revoke a share. Only the original sharer can revoke."""
    stmt = select(Share).where(Share.id == share_id, Share.shared_by == current_user.id)
    share = (await db.execute(stmt)).scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")
    await db.delete(share)
    await db.commit()


# ────────────────────────────────────────────────────────────
# ────────────────────────────────────────────────────────────
# Permission helpers
# ────────────────────────────────────────────────────────────

def _filter_annotations_by_permission(annotations: List[Annotation], permission: str) -> List[AnnotationData]:
    """Filter annotations based on share permission level.

    Args:
        annotations: List of Annotation models from the database
        permission: Either 'view' or 'comment'

    Returns:
        Filtered list of AnnotationData. For 'view' permission, note_content is excluded.
    """
    filtered = []
    for a in annotations:
        annotation_data = AnnotationData(
            id=str(a.id),
            set_id=str(a.set_id),
            page_number=a.page_number,
            type=a.type,
            rects=a.rects,
            selected_text=a.selected_text,
            # note_content is only included for 'comment' permission
            note_content=a.note_content if permission == "comment" else None,
            color=a.color,
        )
        filtered.append(annotation_data)
    return filtered


# ────────────────────────────────────────────────────────────
# Public route — no auth required
# ────────────────────────────────────────────────────────────

@public_router.get("/shared/annotations/{token}", response_model=SharedAnnotationsResponse)
async def get_shared_annotations(token: str, db: AsyncSession = Depends(get_db)):
    """Public endpoint: returns the annotation set and PDF data for a given share token.

    Permission enforcement:
    - 'view': Annotations are returned without note_content
    - 'comment': Full annotations including note_content are returned
    """
    stmt = select(Share).where(Share.share_token == token)
    share = (await db.execute(stmt)).scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="Share not found or revoked")

    # Load the annotation set
    stmt_set = select(AnnotationSet).where(AnnotationSet.id == share.annotation_set_id)
    ann_set = (await db.execute(stmt_set)).scalar_one_or_none()
    if not ann_set:
        raise HTTPException(status_code=404, detail="Annotation set no longer exists")

    # Load all annotations for this set
    stmt_ann = select(Annotation).where(Annotation.set_id == ann_set.id)
    annotations = (await db.execute(stmt_ann)).scalars().all()

    # Load related PDF
    stmt_pdf = select(Pdf).where(Pdf.id == ann_set.pdf_id)
    pdf = (await db.execute(stmt_pdf)).scalar_one_or_none()

    # Load the sharer's profile
    stmt_user = select(User).where(User.id == share.shared_by)
    sharer = (await db.execute(stmt_user)).scalar_one_or_none()

    # Filter annotations based on share permission
    filtered_annotations = _filter_annotations_by_permission(annotations, share.permission)

    return SharedAnnotationsResponse(
        shared_by_login=sharer.github_login if sharer else "unknown",
        shared_by_avatar=sharer.avatar_url if sharer else None,
        permission=share.permission,
        annotation_set=AnnotationSetData(
            id=str(ann_set.id),
            pdf_id=str(ann_set.pdf_id),
            name=ann_set.name,
            color=ann_set.color or "#FFFF00",
            annotations=filtered_annotations,
        ),
        pdf_id=str(ann_set.pdf_id),
        pdf_title=pdf.title if pdf else "Unknown PDF",
    )


@public_router.get("/shared/pdf/{token}")
async def get_shared_pdf_content(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Publicly serve PDF content for a valid share token.
    Uses ETag for caching based on the PDF's GitHub SHA.
    """
    stmt = select(Share).where(Share.share_token == token)
    share = (await db.execute(stmt)).scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="Share link invalid or revoked")

    # Get the PDF info via the annotation set
    stmt_pdf = (
        select(Pdf, User)
        .join(AnnotationSet, AnnotationSet.pdf_id == Pdf.id)
        .join(User, User.id == Pdf.user_id)
        .where(AnnotationSet.id == share.annotation_set_id)
    )
    result = await db.execute(stmt_pdf)
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="PDF content not found")
    
    pdf, owner = row

    # ETag Implementation
    etag = f'"{pdf.github_sha}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)

    pdf_bytes = await github_repo.download_pdf_from_github(
        owner.access_token,
        owner.github_login,
        pdf.filename
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "ETag": etag,
            "Cache-Control": "private, max-age=3600" # Cache for 1 hour
        }
    )
