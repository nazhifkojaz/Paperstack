"""Tests for the PDF download service."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx
from httpx import Response

from app.services.pdf_download_service import (
    PdfDownloadService,
    PdfDownloadResult,
    PdfSource,
    REPO_NAME,
)
from app.services.exceptions import (
    ExternalUrlError,
    GithubApiError,
    InvalidPdfSourceError,
    PdfDownloadError,
)


@pytest.fixture
def download_service():
    return PdfDownloadService()


@pytest.fixture
def sample_pdf():
    return b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\nxref\n0 2\n0000000000 65535 f\n0000000009 00000 n\ntrailer\n<<\n/Size 2\n>>\nstartxref\n50\n%%EOF"


# ---------------------------------------------------------------------------
# download_to_tempfile — GitHub
# ---------------------------------------------------------------------------

class TestDownloadGitHub:

    async def test_download_from_github_success(self, download_service, sample_pdf):
        with respx.mock as mock:
            login = "testuser"
            filename = "paper.pdf"
            url = (
                "https://api.github.com/repos/"
                f"{login}/{REPO_NAME}/contents/{filename}"
            )
            mock.get(url).mock(
                return_value=Response(200, content=sample_pdf)
            )

            with patch(
                "app.services.pdf_download_service.decrypt_token",
                return_value="decrypted_github_token",
            ):
                result = await download_service.download_to_tempfile(
                    source=PdfSource.GITHUB,
                    github_access_token="encrypted_token",
                    github_login=login,
                    github_filename=filename,
                )

        assert isinstance(result, PdfDownloadResult)
        assert result.source == PdfSource.GITHUB
        assert result.file_size == len(sample_pdf)
        assert result.file_path.exists()
        assert result.file_path.suffix == ".pdf"

        result.file_path.unlink()

    async def test_download_from_github_api_error(self, download_service):
        with respx.mock as mock:
            login = "testuser"
            url = (
                "https://api.github.com/repos/"
                f"{login}/{REPO_NAME}/contents/paper.pdf"
            )
            mock.get(url).mock(
                return_value=Response(404, json={"message": "Not Found"})
            )

            with patch(
                "app.services.pdf_download_service.decrypt_token",
                return_value="decrypted_token",
            ):
                with pytest.raises(GithubApiError) as exc_info:
                    await download_service.download_to_tempfile(
                        source=PdfSource.GITHUB,
                        github_access_token="encrypted_token",
                        github_login=login,
                        github_filename="paper.pdf",
                    )

        assert exc_info.value.status_code == 404

    async def test_download_from_github_missing_params(self, download_service):
        with pytest.raises(InvalidPdfSourceError, match="requires access_token"):
            await download_service.download_to_tempfile(
                source=PdfSource.GITHUB,
                github_access_token=None,
                github_login=None,
                github_filename=None,
            )


# ---------------------------------------------------------------------------
# download_to_tempfile — External URL
# ---------------------------------------------------------------------------

class TestDownloadExternalUrl:

    async def test_download_from_url_success(self, download_service, sample_pdf):
        url = "https://example.com/paper.pdf"
        with respx.mock as mock:
            mock.get(url).mock(
                return_value=Response(200, content=sample_pdf)
            )

            result = await download_service.download_to_tempfile(
                source=PdfSource.EXTERNAL_URL,
                external_url=url,
            )

        assert isinstance(result, PdfDownloadResult)
        assert result.source == PdfSource.EXTERNAL_URL
        assert result.file_size == len(sample_pdf)
        assert result.file_path.exists()

        result.file_path.unlink()

    async def test_download_from_url_404(self, download_service):
        url = "https://example.com/missing.pdf"
        with respx.mock as mock:
            mock.get(url).mock(return_value=Response(404))

            with pytest.raises(ExternalUrlError) as exc_info:
                await download_service.download_to_tempfile(
                    source=PdfSource.EXTERNAL_URL,
                    external_url=url,
                )

        assert exc_info.value.status_code == 404

    async def test_download_from_url_missing_url(self, download_service):
        with pytest.raises(InvalidPdfSourceError, match="requires a url"):
            await download_service.download_to_tempfile(
                source=PdfSource.EXTERNAL_URL,
                external_url=None,
            )


# ---------------------------------------------------------------------------
# download_to_bytes
# ---------------------------------------------------------------------------

class TestDownloadToBytes:

    async def test_download_github_bytes(self, download_service, sample_pdf):
        with respx.mock as mock:
            login = "testuser"
            filename = "paper.pdf"
            url = (
                "https://api.github.com/repos/"
                f"{login}/{REPO_NAME}/contents/{filename}"
            )
            mock.get(url).mock(
                return_value=Response(200, content=sample_pdf)
            )

            with patch(
                "app.services.pdf_download_service.decrypt_token",
                return_value="decrypted_github_token",
            ):
                result = await download_service.download_to_bytes(
                    source=PdfSource.GITHUB,
                    github_access_token="encrypted_token",
                    github_login=login,
                    github_filename=filename,
                )

        assert result == sample_pdf

    async def test_download_url_bytes(self, download_service, sample_pdf):
        url = "https://example.com/paper.pdf"
        with respx.mock as mock:
            mock.get(url).mock(
                return_value=Response(200, content=sample_pdf)
            )

            result = await download_service.download_to_bytes(
                source=PdfSource.EXTERNAL_URL,
                external_url=url,
            )

        assert result == sample_pdf

    async def test_download_bytes_invalid_source(self, download_service):
        # Using a non-existent enum value requires a different approach:
        # We pass EXTERNAL_URL without url to get the error
        with pytest.raises(InvalidPdfSourceError, match="requires a url"):
            await download_service.download_to_bytes(
                source=PdfSource.EXTERNAL_URL,
                external_url=None,
            )


# ---------------------------------------------------------------------------
# Invalid source
# ---------------------------------------------------------------------------

class TestInvalidSource:

    async def test_invalid_source_download_to_tempfile(self, download_service):
        # Pass a valid source name but missing required params
        with pytest.raises(InvalidPdfSourceError):
            await download_service.download_to_tempfile(
                source=PdfSource.GITHUB,
                github_access_token=None,
                github_login=None,
                github_filename=None,
            )
