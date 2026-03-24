"""Tests for GitHub repo service."""
import pytest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException


class TestEnsureUserRepo:
    """Tests for ensure_user_repo function."""

    async def test_repo_exists_returns_true(self) -> None:
        """Test that existing repo returns True."""
        from app.services.github_repo import ensure_user_repo

        async def mock_get(url, **kwargs):
            class MockResponse:
                status_code = 200
            return MockResponse()

        with patch("app.services.github_repo.get_github_client") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = mock_get

            result = await ensure_user_repo("encrypted_token", "testuser")
            assert result is True

    async def test_repo_not_found_creates_new(self) -> None:
        """Test that non-existent repo is created."""
        from app.services.github_repo import ensure_user_repo

        async def mock_get(url, **kwargs):
            class MockResponse:
                status_code = 404
            return MockResponse()

        async def mock_post(url, **kwargs):
            class MockResponse:
                status_code = 201
            return MockResponse()

        with patch("app.services.github_repo.get_github_client") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = mock_get
            mock_client.return_value.__aenter__.return_value.post = mock_post

            result = await ensure_user_repo("encrypted_token", "testuser")
            assert result is True

    async def test_repo_check_fails_raises_500(self) -> None:
        """Test that repo check failure raises HTTPException."""
        from app.services.github_repo import ensure_user_repo

        async def mock_get(url, **kwargs):
            class MockResponse:
                status_code = 500
                text = "Server error"
            return MockResponse()

        with patch("app.services.github_repo.get_github_client") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = mock_get

            with pytest.raises(HTTPException) as exc:
                await ensure_user_repo("encrypted_token", "testuser")

            assert exc.value.status_code == 500


class TestUploadPdfToGitHub:
    """Tests for upload_pdf_to_github function."""

    async def test_upload_success(self) -> None:
        """Test successful PDF upload."""
        from app.services.github_repo import upload_pdf_to_github

        async def mock_put(url, **kwargs):
            class MockResponse:
                status_code = 201
                def json(self):
                    return {"content": {"sha": "abc123"}}
            return MockResponse()

        with patch("app.services.github_repo.get_github_client") as mock_client:
            mock_client.return_value.__aenter__.return_value.put = mock_put

            result = await upload_pdf_to_github(
                "encrypted_token",
                "testuser",
                "pdfs/test.pdf",
                b"%PDF-1.4 test content",
                "Add PDF"
            )

            assert result["content"]["sha"] == "abc123"

    async def test_upload_failure_raises_500(self) -> None:
        """Test upload failure raises HTTPException."""
        from app.services.github_repo import upload_pdf_to_github

        async def mock_put(url, **kwargs):
            class MockResponse:
                status_code = 500
                text = "Upload failed"
            return MockResponse()

        with patch("app.services.github_repo.get_github_client") as mock_client:
            mock_client.return_value.__aenter__.return_value.put = mock_put

            with pytest.raises(HTTPException) as exc:
                await upload_pdf_to_github(
                    "encrypted_token",
                    "testuser",
                    "pdfs/test.pdf",
                    b"%PDF-1.4 test content"
                )

            assert exc.value.status_code == 500


class TestDownloadPdfFromGitHub:
    """Tests for download_pdf_from_github function."""

    async def test_download_success(self) -> None:
        """Test successful PDF download."""
        from app.services.github_repo import download_pdf_from_github

        async def mock_get(url, **kwargs):
            class MockResponse:
                status_code = 200
                content = b"%PDF-1.4 test content"
            return MockResponse()

        with patch("app.services.github_repo.get_github_client") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = mock_get

            result = await download_pdf_from_github(
                "encrypted_token",
                "testuser",
                "pdfs/test.pdf"
            )

            assert result == b"%PDF-1.4 test content"

    async def test_download_failure_raises_exception(self) -> None:
        """Test download failure raises HTTPException."""
        from app.services.github_repo import download_pdf_from_github

        async def mock_get(url, **kwargs):
            class MockResponse:
                status_code = 404
                text = "Not found"
            return MockResponse()

        with patch("app.services.github_repo.get_github_client") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = mock_get

            with pytest.raises(HTTPException) as exc:
                await download_pdf_from_github(
                    "encrypted_token",
                    "testuser",
                    "pdfs/nonexistent.pdf"
                )

            assert exc.value.status_code == 404


class TestDeletePdfFromGitHub:
    """Tests for delete_pdf_from_github function."""

    async def test_delete_success(self) -> None:
        """Test successful PDF deletion."""
        from app.services.github_repo import delete_pdf_from_github

        async def mock_request(method, url, **kwargs):
            class MockResponse:
                status_code = 200
            return MockResponse()

        with patch("app.services.github_repo.get_github_client") as mock_client:
            mock_client.return_value.__aenter__.return_value.request = mock_request

            result = await delete_pdf_from_github(
                "encrypted_token",
                "testuser",
                "pdfs/test.pdf",
                "abc123",
                "Delete PDF"
            )

            assert result is True

    async def test_delete_failure_raises_500(self) -> None:
        """Test delete failure raises HTTPException."""
        from app.services.github_repo import delete_pdf_from_github

        async def mock_request(method, url, **kwargs):
            class MockResponse:
                status_code = 500
                text = "Delete failed"
            return MockResponse()

        with patch("app.services.github_repo.get_github_client") as mock_client:
            mock_client.return_value.__aenter__.return_value.request = mock_request

            with pytest.raises(HTTPException) as exc:
                await delete_pdf_from_github(
                    "encrypted_token",
                    "testuser",
                    "pdfs/test.pdf",
                    "abc123"
                )

            assert exc.value.status_code == 500
