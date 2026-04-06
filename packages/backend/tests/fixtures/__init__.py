"""Test data fixtures for Paperstack backend tests."""
import uuid

from app.db.models import Pdf, Tag, AnnotationSet, Annotation, Collection, Citation, Share, PdfCollection


async def create_test_pdf(
    db_session,
    id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    title: str = "Test PDF",
    filename: str = "test.pdf",
    github_sha: str | None = "abc123",
    file_size: int | None = None,
    page_count: int | None = 1,
    doi: str | None = None,
) -> Pdf:
    """Create a test Pdf. PostgreSQL will auto-generate id and timestamps."""
    pdf = Pdf(
        id=id,
        user_id=user_id,
        title=title,
        filename=filename,
        github_sha=github_sha,
        file_size=file_size,
        page_count=page_count,
        doi=doi,
        isbn=None,
    )
    db_session.add(pdf)
    await db_session.flush()
    return pdf


async def create_test_tag(
    db_session,
    id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    name: str = "Test Tag",
    color: str | None = "#FF0000",
) -> Tag:
    """Create a test Tag. PostgreSQL will auto-generate id."""
    tag = Tag(
        id=id,
        user_id=user_id,
        name=name,
        color=color,
    )
    db_session.add(tag)
    await db_session.flush()
    return tag


async def create_test_annotation_set(
    db_session,
    id: uuid.UUID | None = None,
    pdf_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    name: str = "Default",
    color: str | None = "#FFFF00",
) -> AnnotationSet:
    """Create a test AnnotationSet. PostgreSQL will auto-generate id and timestamps."""
    ann_set = AnnotationSet(
        id=id,
        pdf_id=pdf_id,
        user_id=user_id,
        name=name,
        color=color,
    )
    db_session.add(ann_set)
    await db_session.flush()
    return ann_set


async def create_test_annotation(
    db_session,
    id: uuid.UUID | None = None,
    set_id: uuid.UUID | None = None,
    page_number: int = 1,
    type: str = "highlight",
    rects: list | None = None,
    selected_text: str | None = None,
    note_content: str | None = None,
    color: str | None = "#FFFF00",
) -> Annotation:
    """Create a test Annotation. PostgreSQL will auto-generate id and timestamps."""
    annotation = Annotation(
        id=id,
        set_id=set_id,
        page_number=page_number,
        type=type,
        rects=rects or [],
        selected_text=selected_text,
        note_content=note_content,
        color=color,
    )
    db_session.add(annotation)
    await db_session.flush()
    return annotation


async def create_test_collection(
    db_session,
    id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    name: str = "Test Collection",
    parent_id: uuid.UUID | None = None,
    position: int | None = 0,
) -> Collection:
    """Create a test Collection. PostgreSQL will auto-generate id and created_at."""
    collection = Collection(
        id=id,
        user_id=user_id,
        name=name,
        parent_id=parent_id,
        position=position,
    )
    db_session.add(collection)
    await db_session.flush()
    return collection


async def create_test_citation(
    db_session,
    id: uuid.UUID | None = None,
    pdf_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    bibtex: str = "@article{test2024}",
    csl_json: dict | None = None,
    doi: str | None = None,
    title: str | None = None,
    authors: str | None = None,
    year: int | None = None,
    source: str = "manual",
) -> Citation:
    """Create a test Citation. PostgreSQL will auto-generate id and timestamps."""
    citation = Citation(
        id=id,
        pdf_id=pdf_id,
        user_id=user_id,
        bibtex=bibtex,
        csl_json=csl_json,
        doi=doi,
        title=title,
        authors=authors,
        year=year,
        source=source,
    )
    db_session.add(citation)
    await db_session.flush()
    return citation


async def create_test_share(
    db_session,
    id: uuid.UUID | None = None,
    annotation_set_id: uuid.UUID | None = None,
    shared_by: uuid.UUID | None = None,
    shared_with: uuid.UUID | None = None,
    share_token: str | None = None,
    permission: str = "view",
) -> Share:
    """Create a test Share. PostgreSQL will auto-generate id and created_at."""
    import secrets

    share = Share(
        id=id,
        annotation_set_id=annotation_set_id,
        shared_by=shared_by,
        shared_with=shared_with,
        share_token=share_token or secrets.token_urlsafe(48),
        permission=permission,
    )
    db_session.add(share)
    await db_session.flush()
    return share


async def create_test_pdf_collection(
    db_session,
    pdf_id: uuid.UUID,
    collection_id: uuid.UUID,
) -> PdfCollection:
    """Create a test PdfCollection association. PostgreSQL will auto-generate added_at."""
    pc = PdfCollection(
        pdf_id=pdf_id,
        collection_id=collection_id,
    )
    db_session.add(pc)
    await db_session.flush()
    return pc


__all__ = [
    "create_test_pdf",
    "create_test_tag",
    "create_test_annotation_set",
    "create_test_annotation",
    "create_test_collection",
    "create_test_citation",
    "create_test_share",
    "create_test_pdf_collection",
]
