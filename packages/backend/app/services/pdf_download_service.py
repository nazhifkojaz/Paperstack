"""PDF download service for fetching PDFs from multiple sources.

Supports:
- GitHub API downloads (via user's access token)
- External URL downloads (direct HTTP(S) links)

Uses streaming for memory efficiency with large files.
"""

import httpx
import logging
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from app.core.security import decrypt_token
from app.services.exceptions import (
    ExternalUrlError,
    GithubApiError,
    InvalidPdfSourceError,
    PdfDownloadError,
)


logger = logging.getLogger(__name__)


GITHUB_API_URL = "https://api.github.com"
REPO_NAME = "paperstack-library"
CHUNK_SIZE = 8192  # 8KB chunks for streaming


class PdfSource(Enum):
    """PDF source types."""
    GITHUB = "github"
    EXTERNAL_URL = "external_url"


@dataclass
class PdfDownloadResult:
    """Result of a PDF download operation.

    Attributes:
        source: Where the PDF was downloaded from
        file_path: Path to the downloaded temp file (caller must clean up)
        file_size: Size of the downloaded file in bytes
    """
    source: PdfSource
    file_path: Path
    file_size: int


class PdfDownloadService:
    """Service for downloading PDFs from various sources."""

    async def download_to_tempfile(
        self,
        source: PdfSource,
        github_access_token: str | None = None,
        github_login: str | None = None,
        github_filename: str | None = None,
        external_url: str | None = None,
    ) -> PdfDownloadResult:
        """Download a PDF to a temporary file.

        Args:
            source: Where to download from (GITHUB or EXTERNAL_URL)
            github_access_token: Encrypted GitHub token (for GITHUB source)
            github_login: User's GitHub username (for GITHUB source)
            github_filename: Path in GitHub repo (for GITHUB source)
            external_url: Direct PDF URL (for EXTERNAL_URL source)

        Returns:
            PdfDownloadResult with temp file path (caller must clean up)

        Raises:
            GithubApiError: If GitHub API returns an error
            ExternalUrlError: If external URL download fails
            InvalidPdfSourceError: If source configuration is invalid
        """
        if source == PdfSource.GITHUB:
            return await self._download_from_github(
                access_token=github_access_token,
                github_login=github_login,
                filepath=github_filename,
            )
        elif source == PdfSource.EXTERNAL_URL:
            return await self._download_from_url(external_url)
        else:
            raise InvalidPdfSourceError(f"Unknown source: {source}")

    async def download_to_bytes(
        self,
        source: PdfSource,
        github_access_token: str | None = None,
        github_login: str | None = None,
        github_filename: str | None = None,
        external_url: str | None = None,
    ) -> bytes:
        """Download a PDF to bytes (for direct serving).

        Args:
            source: Where to download from
            github_access_token: Encrypted GitHub token (for GITHUB source)
            github_login: User's GitHub username (for GITHUB source)
            github_filename: Path in GitHub repo (for GITHUB source)
            external_url: Direct PDF URL (for EXTERNAL_URL source)

        Returns:
            The PDF content as bytes

        Raises:
            GithubApiError: If GitHub API returns an error
            ExternalUrlError: If external URL download fails
            InvalidPdfSourceError: If source configuration is invalid
        """
        if source == PdfSource.GITHUB:
            return await self._download_from_github_bytes(
                access_token=github_access_token,
                github_login=github_login,
                filepath=github_filename,
            )
        elif source == PdfSource.EXTERNAL_URL:
            return await self._download_from_url_bytes(external_url)
        else:
            raise InvalidPdfSourceError(f"Unknown source: {source}")

    async def _download_from_github(
        self,
        access_token: str | None,
        github_login: str | None,
        filepath: str | None,
    ) -> PdfDownloadResult:
        """Download PDF from GitHub to a temp file using streaming.

        Args:
            access_token: Encrypted GitHub access token
            github_login: User's GitHub username
            filepath: Path to the PDF in the repo

        Returns:
            PdfDownloadResult with temp file path

        Raises:
            GithubApiError: If GitHub API returns an error
        """
        if not all([access_token, github_login, filepath]):
            raise InvalidPdfSourceError(
                "GitHub download requires access_token, github_login, and filepath"
            )

        decrypted_token = decrypt_token(access_token)

        async with httpx.AsyncClient() as client:
            client.headers.update({
                "Authorization": f"Bearer {decrypted_token}",
                "Accept": "application/vnd.github.v3.raw",
                "X-GitHub-Api-Version": "2022-11-28",
            })

            url = f"{GITHUB_API_URL}/repos/{github_login}/{REPO_NAME}/contents/{filepath}"
            logger.info("Downloading PDF from GitHub: %s", url)

            async with client.stream("GET", url) as response:
                if response.status_code != 200:
                    raise GithubApiError(
                        status_code=response.status_code,
                        detail=f"Failed to download from GitHub: {response.text}",
                    )

                tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
                file_size = 0
                try:
                    async for chunk in response.aiter_bytes(chunk_size=CHUNK_SIZE):
                        tmp.write(chunk)
                        file_size += len(chunk)
                    tmp.close()
                    logger.info("Downloaded %d bytes from GitHub", file_size)
                    return PdfDownloadResult(
                        source=PdfSource.GITHUB,
                        file_path=Path(tmp.name),
                        file_size=file_size,
                    )
                except Exception as e:
                    tmp.close()
                    Path(tmp.name).unlink(missing_ok=True)
                    raise PdfDownloadError(f"Failed to write temp file: {e}") from e

    async def _download_from_github_bytes(
        self,
        access_token: str | None,
        github_login: str | None,
        filepath: str | None,
    ) -> bytes:
        """Download PDF from GitHub to bytes (non-streaming, for direct serving).

        Args:
            access_token: Encrypted GitHub access token
            github_login: User's GitHub username
            filepath: Path to the PDF in the repo

        Returns:
            The PDF content as bytes

        Raises:
            GithubApiError: If GitHub API returns an error
        """
        if not all([access_token, github_login, filepath]):
            raise InvalidPdfSourceError(
                "GitHub download requires access_token, github_login, and filepath"
            )

        decrypted_token = decrypt_token(access_token)

        async with httpx.AsyncClient() as client:
            client.headers.update({
                "Authorization": f"Bearer {decrypted_token}",
                "Accept": "application/vnd.github.v3.raw",
                "X-GitHub-Api-Version": "2022-11-28",
            })

            url = f"{GITHUB_API_URL}/repos/{github_login}/{REPO_NAME}/contents/{filepath}"
            response = await client.get(url)

            if response.status_code != 200:
                raise GithubApiError(
                    status_code=response.status_code,
                    detail=f"Failed to download from GitHub: {response.text}",
                )

            return response.content

    async def _download_from_url(self, url: str | None) -> PdfDownloadResult:
        """Download PDF from external URL to a temp file using streaming.

        Args:
            url: Direct URL to the PDF

        Returns:
            PdfDownloadResult with temp file path

        Raises:
            ExternalUrlError: If download fails
        """
        if not url:
            raise InvalidPdfSourceError("URL download requires a url parameter")

        logger.info("Downloading PDF from external URL: %s", url)

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=60.0,
        ) as client:
            async with client.stream("GET", url) as response:
                if response.status_code != 200:
                    raise ExternalUrlError(
                        url=url,
                        status_code=response.status_code,
                        detail="Failed to download linked PDF",
                    )

                tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
                file_size = 0
                try:
                    async for chunk in response.aiter_bytes(chunk_size=CHUNK_SIZE):
                        tmp.write(chunk)
                        file_size += len(chunk)
                    tmp.close()
                    logger.info("Downloaded %d bytes from external URL", file_size)
                    return PdfDownloadResult(
                        source=PdfSource.EXTERNAL_URL,
                        file_path=Path(tmp.name),
                        file_size=file_size,
                    )
                except Exception as e:
                    tmp.close()
                    Path(tmp.name).unlink(missing_ok=True)
                    raise ExternalUrlError(
                        url=url,
                        detail=f"Failed to write temp file: {e}",
                    ) from e

    async def _download_from_url_bytes(self, url: str | None) -> bytes:
        """Download PDF from external URL to bytes (non-streaming, for direct serving).

        Args:
            url: Direct URL to the PDF

        Returns:
            The PDF content as bytes

        Raises:
            ExternalUrlError: If download fails
        """
        if not url:
            raise InvalidPdfSourceError("URL download requires a url parameter")

        logger.info("Downloading PDF from external URL: %s", url)

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=60.0,
        ) as client:
            response = await client.get(url)

            if response.status_code != 200:
                raise ExternalUrlError(
                    url=url,
                    status_code=response.status_code,
                    detail="Failed to download linked PDF",
                )

            return response.content


# Singleton instance for use in routes
pdf_download_service = PdfDownloadService()
