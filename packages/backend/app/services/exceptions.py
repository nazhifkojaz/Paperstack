"""Custom exceptions for service layer."""


class LLMRateLimitError(Exception):
    """Raised when an LLM provider returns 429 Too Many Requests."""

    def __init__(self, provider: str):
        self.provider = provider
        super().__init__(
            f"{provider.upper()} API rate limit exceeded. Please wait a moment and try again."
        )


class LLMProviderError(Exception):
    """Raised when an LLM provider returns an unexpected HTTP error."""

    def __init__(self, provider: str, status_code: int, detail: str = ""):
        self.provider = provider
        self.status_code = status_code
        super().__init__(
            f"{provider.upper()} API error ({status_code}): {detail}"
            if detail
            else f"{provider.upper()} API error ({status_code})"
        )


class EmbeddingError(Exception):
    """Raised when the embedding service fails."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class IndexingError(Exception):
    """Raised when PDF indexing fails."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


# ============================================================================
# API Key Service Exceptions
# ============================================================================

class ApiKeyNotFoundError(Exception):
    """Raised when no API key is available and quota is exhausted."""

    def __init__(self, quota_type: str = "general"):
        self.quota_type = quota_type
        super().__init__(
            f"No API key configured and {quota_type} quota exhausted. "
            "Please add an API key in Settings."
        )


class QuotaExhaustedError(Exception):
    """Raised when specific quota type is depleted."""

    def __init__(self, quota_type: str, remaining: int = 0):
        self.quota_type = quota_type
        self.remaining = remaining
        super().__init__(
            f"{quota_type.replace('_', ' ').title()} quota exhausted ({remaining} remaining). "
            "Please add an API key."
        )


# ============================================================================
# PDF Download Service Exceptions
# ============================================================================

class PdfDownloadError(Exception):
    """Base exception for PDF download failures."""
    pass


class GithubApiError(PdfDownloadError):
    """Raised when GitHub API returns an error."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"GitHub API error ({status_code}): {detail}")


class ExternalUrlError(PdfDownloadError):
    """Raised when external URL download fails."""

    def __init__(self, url: str, status_code: int | None = None, detail: str = ""):
        self.url = url
        self.status_code = status_code
        detail_msg = f": {detail}" if detail else ""
        status_msg = f" (HTTP {status_code})" if status_code else ""
        super().__init__(f"Failed to download from {url}{status_msg}{detail_msg}")


class InvalidPdfSourceError(PdfDownloadError):
    """Raised when source configuration is invalid."""
    pass


class GoogleDriveError(PdfDownloadError):
    """Raised when the Google Drive API returns an error."""

    def __init__(self, status_code: int | None = None, detail: str = ""):
        self.status_code = status_code
        detail_msg = f": {detail}" if detail else ""
        status_msg = f" (HTTP {status_code})" if status_code else ""
        super().__init__(f"Google Drive API error{status_msg}{detail_msg}")


# ============================================================================
# Indexing Service Exceptions
# ============================================================================

class TextExtractionError(IndexingError):
    """Raised when PDF text extraction fails."""
    pass


class ChunkingError(IndexingError):
    """Raised when PDF chunking fails."""
    pass


class IndexInProgressError(IndexingError):
    """Raised when indexing is actively in progress (not stale)."""

    def __init__(self, pdf_id: str, updated_at):
        self.pdf_id = pdf_id
        self.updated_at = updated_at
        super().__init__(
            f"PDF {pdf_id} indexing is in progress (started {updated_at}). "
            "Please try again shortly."
        )
