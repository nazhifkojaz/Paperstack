"""GitHub repository storage backend."""

from pathlib import Path

from app.services import github_repo
from app.services.storage.base import StorageBackend, UploadResult


class GitHubStorageBackend(StorageBackend):
    """Stores PDFs in the user's private 'paperstack-library' GitHub repo."""

    def __init__(self, encrypted_access_token: str, github_login: str) -> None:
        self._token = encrypted_access_token
        self._login = github_login

    async def ensure_container(self) -> None:
        await github_repo.ensure_user_repo(self._token, self._login)

    async def upload(self, filename: str, file_bytes: bytes, title: str) -> UploadResult:
        resp = await github_repo.upload_pdf_to_github(
            self._token,
            self._login,
            filename,
            file_bytes,
            f"Add {title}",
        )
        github_sha = resp.get("content", {}).get("sha", "")
        return UploadResult(file_id=github_sha, provider="github")

    async def download_bytes(self, file_id: str, filename: str) -> bytes:
        return await github_repo.download_pdf_from_github(self._token, self._login, filename)

    async def download_to_tempfile(self, file_id: str, filename: str) -> Path:
        return await github_repo.download_pdf_to_tempfile(self._token, self._login, filename)

    async def delete(self, file_id: str, filename: str) -> None:
        await github_repo.delete_pdf_from_github(
            self._token, self._login, filename, file_id
        )
