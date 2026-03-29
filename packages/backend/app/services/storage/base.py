"""Abstract base class for PDF storage backends."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class UploadResult:
    """Result of a storage upload operation.

    Attributes:
        file_id: Opaque identifier stored in Pdf.github_sha (GitHub) or Pdf.drive_file_id (Google).
        provider: Storage provider name ('github' | 'google').
    """
    file_id: str
    provider: str


class StorageBackend(ABC):
    """Protocol for PDF storage backends.

    Each backend handles upload, download, and deletion for one provider.
    Credentials are injected at construction time.
    """

    @abstractmethod
    async def ensure_container(self) -> None:
        """Create the storage container (repo / Drive folder) if it doesn't exist."""
        ...

    @abstractmethod
    async def upload(self, filename: str, file_bytes: bytes, title: str) -> UploadResult:
        """Upload a PDF and return its opaque file identifier."""
        ...

    @abstractmethod
    async def download_bytes(self, file_id: str, filename: str) -> bytes:
        """Download a PDF as bytes.

        Args:
            file_id: The opaque identifier returned by upload() (sha for GitHub, Drive file ID for Google).
            filename: The path/name stored in Pdf.filename (used by GitHub; ignored by Google).
        """
        ...

    @abstractmethod
    async def download_to_tempfile(self, file_id: str, filename: str) -> Path:
        """Download a PDF to a temporary file and return its path.

        Caller is responsible for deleting the temp file after use.
        """
        ...

    @abstractmethod
    async def delete(self, file_id: str, filename: str) -> None:
        """Delete a PDF from storage.

        Args:
            file_id: SHA for GitHub (required for the DELETE API), Drive file ID for Google.
            filename: Repo path for GitHub; ignored for Google.
        """
        ...
