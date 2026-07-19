"""Tests for citation routes."""

import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import AsyncClient

from app.core.url_safety import UrlSafetyError
from tests.fixtures import create_test_pdf, create_test_citation


class TestGetCitation:
    """Tests for GET /v1/pdfs/{pdf_id}/citation"""

    async def test_get_citation(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test getting a citation for a PDF."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        await create_test_citation(
            db_session,
            pdf_id=pdf.id,
            user_id=test_user.id,
            bibtex="@article{test2024}",
            doi="10.1234/test",
            title="Test Paper",
            authors="Author One",
            year=2024,
        )
        await db_session.commit()

        response = await client.get(
            f"/v1/pdfs/{pdf.id}/citation",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["doi"] == "10.1234/test"
        assert data["title"] == "Test Paper"

    async def test_get_citation_not_found_returns_404(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test getting citation for PDF without citation returns 404."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        await db_session.commit()

        response = await client.get(
            f"/v1/pdfs/{pdf.id}/citation",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestCreateOrUpdateCitation:
    """Tests for PUT /v1/pdfs/{pdf_id}/citation"""

    async def test_create_citation(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test creating a new citation."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        await db_session.commit()

        response = await client.put(
            f"/v1/pdfs/{pdf.id}/citation",
            json={
                "bibtex": "@article{new2024}",
                "doi": "10.1234/new",
                "title": "New Paper",
                "year": 2024,
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["doi"] == "10.1234/new"

    async def test_update_existing_citation(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test updating an existing citation."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        await create_test_citation(
            db_session,
            pdf_id=pdf.id,
            user_id=test_user.id,
            bibtex="@article{old2024}",
            title="Old Title",
        )
        await db_session.commit()

        response = await client.put(
            f"/v1/pdfs/{pdf.id}/citation",
            json={"title": "Updated Title"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"

    async def test_update_other_users_pdf_returns_404(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """Test updating citation for another user's PDF returns 404."""
        fake_pdf_id = uuid.uuid4()

        response = await client.put(
            f"/v1/pdfs/{fake_pdf_id}/citation",
            json={"bibtex": "@article{test}"},
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_update_title_regenerates_bibtex(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Updating title without explicit bibtex regenerates the skeleton entry."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        await create_test_citation(
            db_session,
            pdf_id=pdf.id,
            user_id=test_user.id,
            bibtex="@article{old2024,\n  title = {Old Title},\n}",
            title="Old Title",
            authors="Doe, John",
        )
        await db_session.commit()

        response = await client.put(
            f"/v1/pdfs/{pdf.id}/citation",
            json={"title": "Brand New Title"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Brand New Title"
        # Bibtex should be regenerated to contain the new title
        assert "Brand New Title" in data["bibtex"]
        assert "Old Title" not in data["bibtex"]
        assert data["source"] == "manual"

    async def test_update_authors_regenerates_bibtex(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Updating authors without explicit bibtex regenerates the skeleton entry."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        await create_test_citation(
            db_session,
            pdf_id=pdf.id,
            user_id=test_user.id,
            bibtex="@article{old,\n  author = {Old Author},\n}",
            title="Some Title",
            authors="Old Author",
        )
        await db_session.commit()

        response = await client.put(
            f"/v1/pdfs/{pdf.id}/citation",
            json={"authors": "New Author, Second Author"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "New Author" in data["bibtex"]
        assert data["source"] == "manual"

    async def test_update_with_explicit_bibtex_untouched(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """When explicit bibtex is provided alongside meta fields, it is used as-is."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        await create_test_citation(
            db_session,
            pdf_id=pdf.id,
            user_id=test_user.id,
            bibtex="@article{old2024}",
            title="Old Title",
        )
        await db_session.commit()

        explicit_bibtex = "@article{custom,\n  title = {Hand Edited},\n}"
        response = await client.put(
            f"/v1/pdfs/{pdf.id}/citation",
            json={"title": "New Title", "bibtex": explicit_bibtex},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        # Explicit bibtex must be stored verbatim
        assert data["bibtex"] == explicit_bibtex
        assert "New Title" not in data["bibtex"]

    async def test_update_non_meta_field_keeps_bibtex(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Updating a non-meta field (e.g. source) should not touch bibtex."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        original_bibtex = "@article{keep2024,\n  title = {Keep Me},\n}"
        await create_test_citation(
            db_session,
            pdf_id=pdf.id,
            user_id=test_user.id,
            bibtex=original_bibtex,
            title="Keep Me",
        )
        await db_session.commit()

        response = await client.put(
            f"/v1/pdfs/{pdf.id}/citation",
            json={"source": "manual"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["bibtex"] == original_bibtex


class TestAutoExtractCitation:
    """Tests for POST /v1/pdfs/{pdf_id}/citation/auto"""

    async def test_auto_extract_with_doi(
        self,
        client: AsyncClient,
        auth_headers,
        mock_github_api,
        mock_crossref_api,
        db_session,
        test_user,
    ) -> None:
        """Test auto-extracting citation with DOI."""
        pdf = await create_test_pdf(
            db_session,
            user_id=test_user.id,
            doi="10.1234/test.doi.12345",
        )
        await db_session.commit()

        response = await client.post(
            f"/v1/pdfs/{pdf.id}/citation/auto",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "bibtex" in data
        assert data["source"] == "crossref"

    async def test_auto_extract_pdf_not_found_returns_404(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """Test auto-extract for non-existent PDF returns 404."""
        fake_pdf_id = uuid.uuid4()

        response = await client.post(
            f"/v1/pdfs/{fake_pdf_id}/citation/auto",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.parametrize(
        "source_url",
        [
            "http://127.0.0.1/private.pdf",
            "http://10.0.0.1/private.pdf",
            "http://169.254.169.254/latest/meta-data",
        ],
    )
    async def test_unsafe_linked_pdf_url_returns_422(
        self, source_url, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        pdf = await create_test_pdf(
            db_session,
            user_id=test_user.id,
            github_sha=None,
        )
        pdf.source_url = source_url
        await db_session.commit()

        response = await client.post(
            f"/v1/pdfs/{pdf.id}/citation/auto",
            headers=auth_headers,
        )

        assert response.status_code == 422

    async def test_unsafe_redirect_returns_422(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        pdf = await create_test_pdf(
            db_session,
            user_id=test_user.id,
            github_sha=None,
        )
        pdf.source_url = "https://example.com/paper.pdf"
        await db_session.commit()

        with (
            patch("app.api.routes.citations.validate_external_url"),
            patch("app.api.routes.citations.httpx.AsyncClient") as mock_client,
        ):
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=UrlSafetyError("redirected to loopback")
            )
            response = await client.post(
                f"/v1/pdfs/{pdf.id}/citation/auto",
                headers=auth_headers,
            )

        assert response.status_code == 422

    async def test_public_upstream_failure_returns_502(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        pdf = await create_test_pdf(
            db_session,
            user_id=test_user.id,
            github_sha=None,
        )
        pdf.source_url = "https://example.com/paper.pdf"
        await db_session.commit()
        request = httpx.Request("GET", pdf.source_url)
        upstream_response = httpx.Response(503, request=request)

        with (
            patch("app.api.routes.citations.validate_external_url"),
            patch("app.api.routes.citations.httpx.AsyncClient") as mock_client,
        ):
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "upstream unavailable",
                    request=request,
                    response=upstream_response,
                )
            )
            response = await client.post(
                f"/v1/pdfs/{pdf.id}/citation/auto",
                headers=auth_headers,
            )

        assert response.status_code == 502


class TestBulkExportCitations:
    """Tests for POST /v1/citations/export"""

    async def test_bulk_export_bibtex(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test bulk exporting citations as BibTeX."""
        pdf1 = await create_test_pdf(
            db_session,
            user_id=test_user.id,
            title="PDF 1",
            filename="pdf1.pdf",
            github_sha="abc1",
        )
        pdf2 = await create_test_pdf(
            db_session,
            user_id=test_user.id,
            title="PDF 2",
            filename="pdf2.pdf",
            github_sha="abc2",
        )

        await create_test_citation(
            db_session,
            pdf_id=pdf1.id,
            user_id=test_user.id,
            bibtex="@article{citation1}",
        )
        await create_test_citation(
            db_session,
            pdf_id=pdf2.id,
            user_id=test_user.id,
            bibtex="@article{citation2}",
        )
        await db_session.commit()

        response = await client.post(
            "/v1/citations/export",
            json={
                "pdf_ids": [str(pdf1.id), str(pdf2.id)],
                "format": "bibtex",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        assert "attachment" in response.headers.get("content-disposition", "")
        content = response.text
        assert "@article{citation1}" in content
        assert "@article{citation2}" in content

    async def test_bulk_export_no_citations_returns_404(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test bulk export with no citations returns 404."""
        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        await db_session.commit()

        response = await client.post(
            "/v1/citations/export",
            json={
                "pdf_ids": [str(pdf.id)],
                "format": "bibtex",
            },
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_bulk_export_unsupported_format_returns_400(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test bulk export with unsupported format returns 400."""
        # Create a PDF with citation so we don't get 404
        pdf = await create_test_pdf(db_session, user_id=test_user.id)
        await create_test_citation(db_session, pdf_id=pdf.id, user_id=test_user.id)
        await db_session.commit()

        response = await client.post(
            "/v1/citations/export",
            json={
                "pdf_ids": [str(pdf.id)],
                "format": "json",
            },
            headers=auth_headers,
        )

        assert response.status_code == 400


class TestValidateCitations:
    """Tests for POST /v1/citations/validate"""

    async def test_validate_all_have_citations(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test validation when all PDFs have citations."""
        pdf1 = await create_test_pdf(
            db_session, user_id=test_user.id, filename="test1.pdf"
        )
        pdf2 = await create_test_pdf(
            db_session, user_id=test_user.id, filename="test2.pdf"
        )
        await create_test_citation(db_session, pdf_id=pdf1.id, user_id=test_user.id)
        await create_test_citation(db_session, pdf_id=pdf2.id, user_id=test_user.id)
        await db_session.commit()

        response = await client.post(
            "/v1/citations/validate",
            json={"pdf_ids": [str(pdf1.id), str(pdf2.id)]},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "has_citation" in data
        assert "missing" in data
        assert len(data["has_citation"]) == 2
        assert len(data["missing"]) == 0

    async def test_validate_some_missing_citations(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ) -> None:
        """Test validation when some PDFs lack citations."""
        pdf1 = await create_test_pdf(
            db_session, user_id=test_user.id, filename="test3.pdf"
        )
        pdf2 = await create_test_pdf(
            db_session, user_id=test_user.id, filename="test4.pdf"
        )
        await create_test_citation(db_session, pdf_id=pdf1.id, user_id=test_user.id)
        await db_session.commit()

        response = await client.post(
            "/v1/citations/validate",
            json={"pdf_ids": [str(pdf1.id), str(pdf2.id)]},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["has_citation"]) == 1
        assert len(data["missing"]) == 1
        assert str(pdf1.id) in data["has_citation"]
        assert str(pdf2.id) in data["missing"]

    async def test_validate_empty_list(self, client: AsyncClient, auth_headers) -> None:
        """Test validation with empty PDF list."""
        response = await client.post(
            "/v1/citations/validate",
            json={"pdf_ids": []},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["has_citation"]) == 0
        assert len(data["missing"]) == 0


class TestLookupCitation:
    """Tests for POST /v1/citations/lookup"""

    async def test_lookup_doi_success(
        self, client: AsyncClient, auth_headers, mock_crossref_api
    ) -> None:
        """Test successful DOI lookup."""
        response = await client.post(
            "/v1/citations/lookup",
            json={"doi": "10.1234/test.doi.12345"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["doi"] == "10.1234/test.doi.12345"
        assert data["isbn"] is None
        assert data["source"] == "crossref"
        assert "bibtex" in data

    async def test_lookup_isbn_success(
        self, client: AsyncClient, auth_headers, mock_openlibrary_api
    ) -> None:
        """Test successful ISBN lookup."""
        response = await client.post(
            "/v1/citations/lookup",
            json={"isbn": "0262033844"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["isbn"] == "0262033844"
        assert data["doi"] is None
        assert data["source"] == "openlibrary"
        assert "@book{" in data["bibtex"]

    async def test_lookup_missing_both_parameters(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """Test lookup with neither DOI nor ISBN returns 400."""
        response = await client.post(
            "/v1/citations/lookup",
            json={},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "Must provide" in response.json()["detail"]

    async def test_lookup_both_parameters(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """Test lookup with both DOI and ISBN returns 400."""
        response = await client.post(
            "/v1/citations/lookup",
            json={"doi": "10.1234/test", "isbn": "0262033844"},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "only one" in response.json()["detail"]

    async def test_lookup_empty_string_parameters(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """Test lookup with empty strings returns 400."""
        response = await client.post(
            "/v1/citations/lookup",
            json={"doi": "", "isbn": ""},
            headers=auth_headers,
        )

        assert response.status_code == 400

    async def test_lookup_doi_not_found(
        self, client: AsyncClient, auth_headers, mock_crossref_api_not_found
    ) -> None:
        """Test DOI not found returns 404."""
        response = await client.post(
            "/v1/citations/lookup",
            json={"doi": "10.9999/nonexistent"},
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    async def test_lookup_isbn_not_found(
        self, client: AsyncClient, auth_headers, mock_openlibrary_api_not_found
    ) -> None:
        """Test ISBN not found returns 404."""
        response = await client.post(
            "/v1/citations/lookup",
            json={"isbn": "9999999999"},
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    async def test_lookup_invalid_doi_format(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """Test invalid DOI format returns 400."""
        response = await client.post(
            "/v1/citations/lookup",
            json={"doi": "not-a-doi"},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "Invalid DOI" in response.json()["detail"]

    async def test_lookup_invalid_isbn_format(
        self, client: AsyncClient, auth_headers
    ) -> None:
        """Test invalid ISBN format returns 400."""
        response = await client.post(
            "/v1/citations/lookup",
            json={"isbn": "not-an-isbn"},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "Invalid ISBN" in response.json()["detail"]

    async def test_lookup_requires_auth(self, client: AsyncClient) -> None:
        """Test lookup endpoint requires authentication."""
        response = await client.post(
            "/v1/citations/lookup",
            json={"doi": "10.1234/test"},
        )

        assert response.status_code == 401
