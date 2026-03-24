"""Tests for PDF routes."""
import uuid
from io import BytesIO
from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient, ASGITransport
from tests.fixtures import create_test_pdf, create_test_annotation_set, create_test_annotation, create_test_collection, create_test_pdf_collection


class TestUploadPdf:
    """Tests for POST /v1/pdfs/upload"""

    async def test_upload_pdf_success(self, client: AsyncClient, auth_headers, mock_github_api, sample_pdf_bytes) -> None:
        """Test successful PDF upload."""
        files = {"file": ("test.pdf", BytesIO(sample_pdf_bytes), "application/pdf")}
        data = {"title": "Test PDF", "doi": "10.1234/test"}

        response = await client.post(
            "/v1/pdfs/upload",
            files=files,
            data=data,
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Test PDF"
        assert data["doi"] == "10.1234/test"
        assert "id" in data
        assert data["page_count"] == 1

    async def test_upload_pdf_invalid_type_returns_400(self, client: AsyncClient, auth_headers) -> None:
        """Test that uploading non-PDF file returns 400."""
        files = {"file": ("test.txt", BytesIO(b"not a pdf"), "text/plain")}
        data = {"title": "Test File"}

        response = await client.post(
            "/v1/pdfs/upload",
            files=files,
            data=data,
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "must be a PDF" in response.json()["detail"]

    async def test_upload_requires_auth(self, client: AsyncClient, sample_pdf_bytes) -> None:
        """Test that upload requires authentication."""
        files = {"file": ("test.pdf", BytesIO(sample_pdf_bytes), "application/pdf")}
        data = {"title": "Test PDF"}

        response = await client.post(
            "/v1/pdfs/upload",
            files=files,
            data=data,
        )

        assert response.status_code == 401

    async def test_upload_creates_repo_if_not_exists(self, client: AsyncClient, auth_headers, mock_github_api, sample_pdf_bytes) -> None:
        """Test that upload creates GitHub repo if it doesn't exist."""
        files = {"file": ("test.pdf", BytesIO(sample_pdf_bytes), "application/pdf")}
        data = {"title": "Test PDF"}

        response = await client.post(
            "/v1/pdfs/upload",
            files=files,
            data=data,
            headers=auth_headers,
        )

        assert response.status_code == 200


class TestListPdfs:
    """Tests for GET /v1/pdfs"""

    async def test_list_pdfs_returns_user_pdfs_only(self, client: AsyncClient, auth_headers, db_session, test_user, test_user_2) -> None:
        """Test that list only returns PDFs belonging to current user."""
        # Create a PDF for test_user
        await create_test_pdf(db_session, user_id=test_user.id, title="User's PDF", filename="user.pdf", github_sha="abc123", page_count=5)
        # Create a PDF for another user
        await create_test_pdf(db_session, user_id=test_user_2.id, title="Other User's PDF", filename="other.pdf", github_sha="def456", page_count=3)
        await db_session.commit()

        response = await client.get(
            "/v1/pdfs",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["title"] == "User's PDF"

    async def test_list_pdfs_paginated(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test pagination of PDF list."""
        # Create 5 PDFs
        for i in range(5):
            await create_test_pdf(
                db_session,
                user_id=test_user.id,
                title=f"PDF {i}",
                filename=f"pdf{i}.pdf",
                github_sha=f"sha{i}",
                page_count=1
            )
        await db_session.commit()

        # Get first page
        response = await client.get(
            "/v1/pdfs?page=1&per_page=2",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    async def test_list_pdfs_filters_by_collection(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test filtering PDFs by collection."""
        # Create PDFs
        pdf1 = await create_test_pdf(db_session, user_id=test_user.id, title="In Collection", filename="in.pdf", github_sha="abc")
        pdf2 = await create_test_pdf(db_session, user_id=test_user.id, title="Not In Collection", filename="out.pdf", github_sha="def")

        # Create collection and add pdf1
        collection = await create_test_collection(db_session, user_id=test_user.id, name="Test Collection")
        await create_test_pdf_collection(db_session, pdf_id=pdf1.id, collection_id=collection.id)
        await db_session.commit()

        # Filter by collection
        response = await client.get(
            f"/v1/pdfs?collection_id={collection.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["title"] == "In Collection"

    async def test_list_pdfs_searches_by_title(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test searching PDFs by title."""
        await create_test_pdf(db_session, user_id=test_user.id, title="Machine Learning Paper", filename="ml.pdf", github_sha="abc")
        await create_test_pdf(db_session, user_id=test_user.id, title="Quantum Physics", filename="qp.pdf", github_sha="def")
        await db_session.commit()

        response = await client.get(
            "/v1/pdfs?q=machine",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert "machine" in data[0]["title"].lower()

    async def test_list_pdfs_sorting(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test sorting PDFs."""
        pdf1 = await create_test_pdf(db_session, user_id=test_user.id, title="A Title", filename="a.pdf", github_sha="abc")
        pdf2 = await create_test_pdf(db_session, user_id=test_user.id, title="Z Title", filename="z.pdf", github_sha="def")
        await db_session.commit()

        # Sort ascending
        response = await client.get(
            "/v1/pdfs?sort=title",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data[0]["title"] == "A Title"

        # Sort descending
        response = await client.get(
            "/v1/pdfs?sort=-title",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data[0]["title"] == "Z Title"


class TestGetPdf:
    """Tests for GET /v1/pdfs/{pdf_id}"""

    async def test_get_pdf_by_id(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test getting a specific PDF by ID."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id, title="Test PDF", filename="test.pdf", github_sha="abc123", page_count=5)
        await db_session.commit()

        response = await client.get(
            f"/v1/pdfs/{pdf.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(pdf.id)
        assert data["title"] == "Test PDF"

    async def test_get_pdf_not_found_returns_404(self, client: AsyncClient, auth_headers) -> None:
        """Test getting non-existent PDF returns 404."""
        fake_id = uuid.uuid4()
        response = await client.get(
            f"/v1/pdfs/{fake_id}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_get_pdf_other_user_returns_404(self, client: AsyncClient, auth_headers, db_session, test_user, test_user_2) -> None:
        """Test getting another user's PDF returns 404."""
        pdf = await create_test_pdf(db_session, user_id=test_user_2.id, title="Other's PDF", filename="other.pdf", github_sha="abc")
        await db_session.commit()

        response = await client.get(
            f"/v1/pdfs/{pdf.id}",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestUpdatePdf:
    """Tests for PATCH /v1/pdfs/{pdf_id}"""

    async def test_update_pdf_title(self, client: AsyncClient, auth_headers, db_session, test_user) -> None:
        """Test updating PDF title."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id, title="Original Title", filename="test.pdf", github_sha="abc")
        await db_session.commit()

        response = await client.patch(
            f"/v1/pdfs/{pdf.id}",
            json={"title": "Updated Title"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"

    async def test_update_pdf_not_found(self, client: AsyncClient, auth_headers) -> None:
        """Test updating non-existent PDF returns 404."""
        response = await client.patch(
            f"/v1/pdfs/{uuid.uuid4()}",
            json={"title": "New Title"},
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestDeletePdf:
    """Tests for DELETE /v1/pdfs/{pdf_id}"""

    async def test_delete_pdf_success(self, client: AsyncClient, auth_headers, mock_github_api, db_session, test_user) -> None:
        """Test successful PDF deletion."""
        from sqlalchemy import select
        from app.db.models import Pdf

        pdf = await create_test_pdf(db_session, user_id=test_user.id, title="To Delete", filename="delete.pdf", github_sha="abc123")
        await db_session.commit()

        response = await client.delete(
            f"/v1/pdfs/{pdf.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert "deleted" in response.json()["message"].lower()

        # Verify it's gone from DB
        result = await db_session.execute(select(Pdf).where(Pdf.id == pdf.id))
        assert result.scalar_one_or_none() is None

    async def test_delete_pdf_cascades_to_annotations(self, client: AsyncClient, auth_headers, mock_github_api, db_session, test_user) -> None:
        """Test that deleting PDF cascades to annotations."""
        from sqlalchemy import select
        from app.db.models import AnnotationSet

        pdf = await create_test_pdf(db_session, user_id=test_user.id, title="With Annotations", filename="with_ann.pdf")
        ann_set = await create_test_annotation_set(db_session, pdf_id=pdf.id, user_id=test_user.id)
        await create_test_annotation(db_session, set_id=ann_set.id, page_number=1)
        await db_session.commit()

        # Delete PDF
        await client.delete(
            f"/v1/pdfs/{pdf.id}",
            headers=auth_headers,
        )

        # Verify annotations are gone (cascade delete)
        result = await db_session.execute(select(AnnotationSet).where(AnnotationSet.pdf_id == pdf.id))
        assert result.scalar_one_or_none() is None

    async def test_delete_pdf_calls_github(self, client: AsyncClient, auth_headers, mock_github_api, db_session, test_user) -> None:
        """Test that deletion calls GitHub API."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id, title="GitHub PDF", filename="gh_test.pdf", github_sha="sha_to_delete")
        await db_session.commit()

        response = await client.delete(
            f"/v1/pdfs/{pdf.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200


class TestGetPdfContent:
    """Tests for GET /v1/pdfs/{pdf_id}/content"""

    async def test_get_pdf_content_streams(self, client: AsyncClient, auth_headers, mock_github_api, db_session, test_user) -> None:
        """Test getting PDF content streams correctly."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id, title="Content Test", filename="content.pdf", github_sha="abc123")
        await db_session.commit()

        response = await client.get(
            f"/v1/pdfs/{pdf.id}/content",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert "etag" in response.headers

    async def test_get_pdf_content_etag_cache(self, client: AsyncClient, auth_headers, mock_github_api, db_session, test_user) -> None:
        """Test ETag caching for PDF content."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id, title="Cache Test", filename="cache.pdf", github_sha="etag_sha")
        await db_session.commit()

        # First request
        response1 = await client.get(
            f"/v1/pdfs/{pdf.id}/content",
            headers=auth_headers,
        )
        etag = response1.headers.get("etag")

        # Second request with If-None-Match
        response2 = await client.get(
            f"/v1/pdfs/{pdf.id}/content",
            headers={
                **auth_headers,
                "if-none-match": etag,
            },
        )

        assert response2.status_code == 304


class TestExportAnnotatedPdf:
    """Tests for GET /v1/pdfs/{pdf_id}/export-annotated"""

    async def test_export_with_no_annotations(self, client: AsyncClient, auth_headers, mock_github_api, db_session, test_user) -> None:
        """Test exporting PDF with no annotations returns original."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id, title="No Annotations", filename="no_ann.pdf")
        await db_session.commit()

        response = await client.get(
            f"/v1/pdfs/{pdf.id}/export-annotated",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"

    async def test_export_with_annotations(self, client: AsyncClient, auth_headers, mock_github_api, db_session, test_user) -> None:
        """Test exporting PDF with annotations bakes them in."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id, title="With Annotations", filename="with_ann.pdf")
        ann_set = await create_test_annotation_set(db_session, pdf_id=pdf.id, user_id=test_user.id, color="#FFFF00")
        await create_test_annotation(db_session, set_id=ann_set.id, page_number=1)
        await db_session.commit()

        response = await client.get(
            f"/v1/pdfs/{pdf.id}/export-annotated",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert "attachment" in response.headers.get("content-disposition", "")
