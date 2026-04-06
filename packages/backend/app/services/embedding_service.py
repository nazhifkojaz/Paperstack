"""Embedding service: wraps Gemini gemini-embedding-001 for chunk and query embedding."""
from typing import Optional

import httpx

from app.core.config import settings
from app.services.exceptions import EmbeddingError

_EMBED_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:batchEmbedContents"


class EmbeddingService:
    """Service for text embedding using Gemini API.

    Accepts an optional http_client parameter for dependency injection.
    If not provided, creates a new client per request (legacy behavior).
    """

    MODEL = "gemini-embedding-001"
    DIMENSIONS = 768
    BATCH_SIZE = 100  # Gemini batchEmbedContents limit

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None):
        """Initialize embedding service with optional shared HTTP client.

        Args:
            http_client: Shared httpx.AsyncClient for connection pooling.
                        If None, creates new client per request (not recommended).
        """
        self._client = http_client

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Batch embed a list of texts using Gemini gemini-embedding-001.

        Returns a list of 768-dim float vectors in the same order as the input.
        Raises EmbeddingError on API failure or missing key.
        """
        if not settings.GEMINI_EMBEDDING_KEY:
            raise EmbeddingError("GEMINI_EMBEDDING_KEY is not configured")

        if not texts:
            return []

        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i : i + self.BATCH_SIZE]
            requests_payload = [
                {
                    "model": f"models/{self.MODEL}",
                    "content": {"parts": [{"text": t}]},
                    "outputDimensionality": self.DIMENSIONS,
                }
                for t in batch
            ]

            client = self._client or httpx.AsyncClient(timeout=60.0)
            should_close = self._client is None

            try:
                if should_close:
                    async with client:
                        resp = await client.post(
                            _EMBED_URL,
                            headers={"x-goog-api-key": settings.GEMINI_EMBEDDING_KEY},
                            json={"requests": requests_payload},
                        )
                        resp.raise_for_status()
                else:
                    resp = await client.post(
                        _EMBED_URL,
                        headers={"x-goog-api-key": settings.GEMINI_EMBEDDING_KEY},
                        json={"requests": requests_payload},
                    )
                    resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise EmbeddingError(
                    f"Gemini embedding API returned {exc.response.status_code}: "
                    f"{exc.response.text[:200]}"
                )
            except httpx.TimeoutException:
                raise EmbeddingError("Gemini embedding API timed out")

            data = resp.json()
            for emb in data["embeddings"]:
                all_embeddings.append(emb["values"])

        return all_embeddings

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string. Returns a 768-dim float vector."""
        results = await self.embed_texts([text])
        return results[0]
