import secrets
from uuid import UUID
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, get_current_user
from app.db.models import User, Share, AnnotationSet, Annotation, Pdf
from app.services import github_repo
from app.services.pdf_download_service import pdf_download_service, PdfSource
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
        annotation_set_id=set_id,
        shared_by=current_user.id,
        shared_with=shared_with_id,
        share_token=token,
        permission=share_in.permission,
    )
    db.add(share)
    await db.commit()
    await db.refresh(share)

    # Construct response with github_login if shared with a user
    response_data = {
        "id": share.id,
        "annotation_set_id": share.annotation_set_id,
        "shared_by": share.shared_by,
        "shared_with": share.shared_with,
        "shared_with_github_login": target_user.github_login if share_in.shared_with_github_login else None,
        "share_token": share.share_token,
        "permission": share.permission,
        "created_at": share.created_at,
    }
    return ShareResponse(**response_data)


@router.get("/annotation-sets/{set_id}/shares", response_model=List[ShareResponse])
async def get_shares_for_set(
    set_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all shares for a given annotation set. Only the owner can view shares."""
    # Verify ownership
    stmt = select(AnnotationSet).where(
        AnnotationSet.id == set_id,
        AnnotationSet.user_id == current_user.id,
    )
    annotation_set = (await db.execute(stmt)).scalar_one_or_none()
    if not annotation_set:
        raise HTTPException(status_code=404, detail="Annotation set not found")

    # Get all shares for this set with shared_with user info
    stmt = (
        select(Share, User)
        .outerjoin(User, User.id == Share.shared_with)
        .where(Share.annotation_set_id == set_id)
        .order_by(Share.created_at.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    # Construct responses with github_login
    shares = []
    for share, shared_with_user in rows:
        shares.append(ShareResponse(
            id=share.id,
            annotation_set_id=share.annotation_set_id,
            shared_by=share.shared_by,
            shared_with=share.shared_with,
            shared_with_github_login=shared_with_user.github_login if shared_with_user else None,
            share_token=share.share_token,
            permission=share.permission,
            created_at=share.created_at,
        ))
    return shares


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
    # Query 1: Fetch share with annotation set in single query
    stmt = (
        select(Share, AnnotationSet)
        .join(AnnotationSet, AnnotationSet.id == Share.annotation_set_id)
        .where(Share.share_token == token)
    )
    result = await db.execute(stmt)
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Share not found or revoked")

    share, ann_set = row

    # Query 2: Fetch annotations, pdf, and sharer with JOINs
    stmt_related = (
        select(Annotation, Pdf, User)
        .select_from(Annotation)
        .join(Pdf, Pdf.id == ann_set.pdf_id)
        .join(User, User.id == share.shared_by)
        .where(Annotation.set_id == ann_set.id)
    )
    result_related = await db.execute(stmt_related)
    related_rows = result_related.all()

    # Extract data from joined results
    if related_rows:
        annotations = [row[0] for row in related_rows]
        pdf = related_rows[0][1]
        sharer = related_rows[0][2]
    else:
        # Edge case: no annotations, still need pdf and sharer
        annotations = []
        stmt_minimal = (
            select(Pdf, User)
            .join(User, User.id == share.shared_by)
            .where(Pdf.id == ann_set.pdf_id)
        )
        result_minimal = await db.execute(stmt_minimal)
        row_minimal = result_minimal.first()
        pdf, sharer = row_minimal if row_minimal else (None, None)

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

    # Both 'view' and 'comment' permissions allow reading the PDF content.
    # 'view' hides note_content (enforced in the annotations endpoint).
    if share.permission not in ("view", "comment"):
        raise HTTPException(status_code=403, detail="Insufficient permission")

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

    # ETag only applies to GitHub-backed PDFs (source_url PDFs have no stable sha)
    if pdf.github_sha:
        etag = f'"{pdf.github_sha}"'
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304)
        etag_header = {"ETag": etag}
    else:
        etag_header = {}

    if pdf.source_url and not pdf.github_sha:
        pdf_bytes = await pdf_download_service.download_to_bytes(
            source=PdfSource.EXTERNAL_URL,
            external_url=pdf.source_url,
        )
    else:
        pdf_bytes = await pdf_download_service.download_to_bytes(
            source=PdfSource.GITHUB,
            github_access_token=owner.access_token,
            github_login=owner.github_login,
            github_filename=pdf.filename,
        )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            **etag_header,
            "Cache-Control": "private, max-age=3600",
        }
    )
