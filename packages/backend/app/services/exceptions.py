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


class ChatQuotaExhaustedError(Exception):
    """Raised when the user's chat quota is depleted."""
    pass
