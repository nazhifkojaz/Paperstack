"""Embedding service: wraps OpenRouter /v1/embeddings for chunk and query embedding.

Model: nvidia/llama-nemotron-embed-vl-1b-v2:free (text-only; image embedding is future work)
"""
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.exceptions import EmbeddingError
from app.services.openrouter_usage_service import openrouter_usage_service

_EMBED_URL = "https://openrouter.ai/api/v1/embeddings"


class EmbeddingService:

    MODEL = "nvidia/llama-nemotron-embed-vl-1b-v2:free"
    DIMENSIONS = 2048
    BATCH_SIZE = 128

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None):
        self._client = http_client

    async def embed_texts(
        self, texts: list[str], db: Optional[AsyncSession] = None
    ) -> list[list[float]]:
        """Embed a list of texts. Returns 2048-dim float vectors in input order.

        Raises EmbeddingError on API failure or missing server key.
        Raises OpenRouterQuotaError when free-tier usage is at/above 90%.
        """
        if not settings.OPENROUTER_API_KEY:
            raise EmbeddingError("OPENROUTER_API_KEY is not configured")

        if not texts:
            return []

        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i : i + self.BATCH_SIZE]

            if db is not None:
                await openrouter_usage_service.record_and_check(db)

            client = self._client or httpx.AsyncClient(timeout=60.0)
            should_close = self._client is None

            payload = {"model": self.MODEL, "input": batch}
            headers = {
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            }

            try:
                if should_close:
                    async with client:
                        resp = await client.post(_EMBED_URL, headers=headers, json=payload)
                        resp.raise_for_status()
                else:
                    resp = await client.post(_EMBED_URL, headers=headers, json=payload)
                    resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise EmbeddingError(
                    f"OpenRouter embedding API returned {exc.response.status_code}: "
                    f"{exc.response.text[:300]}"
                )
            except httpx.TimeoutException:
                raise EmbeddingError("OpenRouter embedding API timed out")

            data = resp.json()
            for item in sorted(data["data"], key=lambda x: x["index"]):
                all_embeddings.append(item["embedding"])

        return all_embeddings

    async def embed_query(
        self, text: str, db: Optional[AsyncSession] = None
    ) -> list[float]:
        """Embed a single query string. Returns a 2048-dim float vector."""
        results = await self.embed_texts([text], db=db)
        return results[0]
