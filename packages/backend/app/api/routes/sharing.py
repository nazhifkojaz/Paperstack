import secrets
from uuid import UUID
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, get_current_user
from app.db.models import User, Share, AnnotationSet, Annotation, Pdf
from app.services.pdf_download_service import pdf_download_service, PdfSource
from app.services.storage.factory import get_storage_backend
from app.schemas.sharing import (
    ShareCreate, ShareResponse, SharedAnnotationsResponse,
    AnnotationSetData, AnnotationData,
)

# Two routers: authenticated actions + public access
router = APIRouter(tags=["sharing"])
public_router = APIRouter(tags=["sharing"])


# Authenticated routes

@router.post("/annotation-sets/{set_id}/share", response_model=ShareResponse)
async def create_share(
    set_id: UUID,
    share_in: ShareCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Share an annotation set — optionally with a specific GitHub user, or as a public link."""
    stmt = select(AnnotationSet).where(
        AnnotationSet.id == set_id,
        AnnotationSet.user_id == current_user.id,
    )
    annotation_set = (await db.execute(stmt)).scalar_one_or_none()
    if not annotation_set:
        raise HTTPException(status_code=404, detail="Annotation set not found")

    # Resolve shared_with user if a GitHub login was provided
    shared_with_id: Optional[UUID] = None
    target_user: Optional[User] = None
    if share_in.shared_with_github_login:
        stmt_user = select(User).where(User.github_login == share_in.shared_with_github_login)
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

    return ShareResponse(
        id=share.id,
        annotation_set_id=share.annotation_set_id,
        shared_by=share.shared_by,
        shared_with=share.shared_with,
        shared_with_github_login=target_user.github_login if target_user else None,
        share_token=share.share_token,
        permission=share.permission,
        created_at=share.created_at,
    )


@router.get("/annotation-sets/{set_id}/shares", response_model=List[ShareResponse])
async def get_shares_for_set(
    set_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all shares for a given annotation set. Only the owner can view shares."""
    stmt = select(AnnotationSet).where(
        AnnotationSet.id == set_id,
        AnnotationSet.user_id == current_user.id,
    )
    if not (await db.execute(stmt)).scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Annotation set not found")

    stmt = (
        select(Share, User)
        .outerjoin(User, User.id == Share.shared_with)
        .where(Share.annotation_set_id == set_id)
        .order_by(Share.created_at.desc())
    )
    rows = (await db.execute(stmt)).all()

    return [
        ShareResponse(
            id=share.id,
            annotation_set_id=share.annotation_set_id,
            shared_by=share.shared_by,
            shared_with=share.shared_with,
            shared_with_github_login=shared_with_user.github_login if shared_with_user else None,
            share_token=share.share_token,
            permission=share.permission,
            created_at=share.created_at,
        )
        for share, shared_with_user in rows
    ]


@router.get("/shared/with-me", response_model=List[ShareResponse])
async def shared_with_me(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all annotation sets that have been shared with the current user."""
    stmt = select(Share).where(Share.shared_with == current_user.id)
    return (await db.execute(stmt)).scalars().all()


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


# Permission helpers

def _filter_annotations_by_permission(annotations: List[Annotation], permission: str) -> List[AnnotationData]:
    return [
        AnnotationData(
            id=str(a.id),
            set_id=str(a.set_id),
            page_number=a.page_number,
            type=a.type,
            rects=a.rects,
            selected_text=a.selected_text,
            note_content=a.note_content if permission == "comment" else None,
            color=a.color,
        )
        for a in annotations
    ]


# Public routes — no auth required

@public_router.get("/shared/annotations/{token}", response_model=SharedAnnotationsResponse)
async def get_shared_annotations(token: str, db: AsyncSession = Depends(get_db)):
    """Public endpoint: returns the annotation set and PDF data for a share token."""
    stmt = (
        select(Share, AnnotationSet)
        .join(AnnotationSet, AnnotationSet.id == Share.annotation_set_id)
        .where(Share.share_token == token)
    )
    row = (await db.execute(stmt)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Share not found or revoked")

    share, ann_set = row

    stmt_related = (
        select(Annotation, Pdf, User)
        .select_from(Annotation)
        .join(Pdf, Pdf.id == ann_set.pdf_id)
        .join(User, User.id == share.shared_by)
        .where(Annotation.set_id == ann_set.id)
    )
    related_rows = (await db.execute(stmt_related)).all()

    if related_rows:
        annotations = [r[0] for r in related_rows]
        pdf = related_rows[0][1]
        sharer = related_rows[0][2]
    else:
        annotations = []
        stmt_minimal = (
            select(Pdf, User)
            .join(User, User.id == share.shared_by)
            .where(Pdf.id == ann_set.pdf_id)
        )
        row_minimal = (await db.execute(stmt_minimal)).first()
        pdf, sharer = row_minimal if row_minimal else (None, None)

    filtered_annotations = _filter_annotations_by_permission(annotations, share.permission)

    # Use display_name preferentially; fall back to github_login for GitHub users
    shared_by_login = (sharer.display_name or sharer.github_login or "Unknown") if sharer else "Unknown"

    return SharedAnnotationsResponse(
        shared_by_login=shared_by_login,
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
    db: AsyncSession = Depends(get_db),
):
    """Publicly serve PDF content for a valid share token.

    For stored PDFs, proxies through the owner's storage backend (GitHub or Drive).
    For URL-linked PDFs, fetches directly from the source URL.
    """
    stmt = select(Share).where(Share.share_token == token)
    share = (await db.execute(stmt)).scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="Share link invalid or revoked")

    if share.permission not in ("view", "comment"):
        raise HTTPException(status_code=403, detail="Insufficient permission")

    stmt_pdf = (
        select(Pdf, User)
        .join(AnnotationSet, AnnotationSet.pdf_id == Pdf.id)
        .join(User, User.id == Pdf.user_id)
        .where(AnnotationSet.id == share.annotation_set_id)
    )
    row = (await db.execute(stmt_pdf)).first()
    if not row:
        raise HTTPException(status_code=404, detail="PDF content not found")

    pdf, owner = row

    # URL-linked PDF — fetch directly, no storage backend needed
    if pdf.source_url and not pdf.github_sha and not pdf.drive_file_id:
        pdf_bytes = await pdf_download_service.download_to_bytes(
            source=PdfSource.EXTERNAL_URL,
            external_url=pdf.source_url,
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Cache-Control": "private, max-age=3600"},
        )

    # Stored PDF — ETag caching using the storage file identifier
    file_id = pdf.drive_file_id or pdf.github_sha
    etag = f'"{file_id}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)

    # Use the owner's storage backend to proxy the file
    backend = await get_storage_backend(owner, db)
    pdf_bytes = await backend.download_bytes(file_id, pdf.filename)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"ETag": etag, "Cache-Control": "private, max-age=3600"},
    )
