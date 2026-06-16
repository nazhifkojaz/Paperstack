"""Embedding service: wraps OpenRouter /v1/embeddings for chunk and query embedding.

Model: qwen/qwen3-embedding-8b (1024-dim via Matryoshka, providers: nebius + deepinfra)
"""

from typing import Optional

import httpx

from app.core.config import settings
from app.services.exceptions import EmbeddingError

import logging

logger = logging.getLogger(__name__)

_EMBED_URL = "https://openrouter.ai/api/v1/embeddings"
_USER_KEY_FALLBACK_STATUSES = {402, 403, 429}

_PROVIDER_BLOCK = {
    "order": ["nebius", "deepinfra"],
    "allow_fallbacks": True,
}


class EmbeddingService:
    MODEL = "qwen/qwen3-embedding-8b"
    DIMENSIONS = 1024
    BATCH_SIZE = 128

    def __init__(
        self,
        http_client: Optional[httpx.AsyncClient] = None,
        user_api_key: str | None = None,
    ):
        self._client = http_client
        self._user_api_key = user_api_key

    async def embed_texts(
        self, texts: list[str], user_api_key: str | None = None
    ) -> list[list[float]]:
        """Embed a list of texts. Returns 1024-dim float vectors in input order.

        Raises EmbeddingError on API failure or missing server key.
        """
        key_candidates = self._key_candidates(user_api_key)
        if not key_candidates:
            raise EmbeddingError("OPENROUTER_API_KEY is not configured")

        if not texts:
            return []

        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i : i + self.BATCH_SIZE]

            payload = {
                "model": self.MODEL,
                "input": batch,
                "dimensions": self.DIMENSIONS,
                "provider": _PROVIDER_BLOCK,
            }
            data = await self._post_embedding_batch(payload, key_candidates)

            for item in sorted(data["data"], key=lambda x: x["index"]):
                embedding = item["embedding"]
                if len(embedding) != self.DIMENSIONS:
                    raise EmbeddingError(
                        f"Expected {self.DIMENSIONS}-dim embedding, got {len(embedding)}"
                    )
                all_embeddings.append(embedding)

        return all_embeddings

    async def embed_query(
        self, text: str, user_api_key: str | None = None
    ) -> list[float]:
        """Embed a single query string. Returns a 1024-dim float vector."""
        results = await self.embed_texts([text], user_api_key=user_api_key)
        return results[0]

    def _key_candidates(
        self,
        user_api_key: str | None,
    ) -> list[tuple[str, str]]:
        user_key = user_api_key or self._user_api_key
        candidates: list[tuple[str, str]] = []
        if user_key:
            candidates.append(("user", user_key))
        app_key = settings.OPENROUTER_API_KEY
        if app_key and app_key != user_key:
            candidates.append(("app", app_key))
        return candidates

    async def _post_embedding_batch(
        self,
        payload: dict,
        key_candidates: list[tuple[str, str]],
    ) -> dict:
        for index, (key_owner, api_key) in enumerate(key_candidates):
            try:
                return await self._post_embedding_with_key(payload, api_key)
            except httpx.HTTPStatusError as exc:
                last_error = EmbeddingError(
                    f"OpenRouter embedding API returned {exc.response.status_code}: "
                    f"{exc.response.text[:300]}"
                )
                can_fallback = (
                    key_owner == "user"
                    and index + 1 < len(key_candidates)
                    and exc.response.status_code in _USER_KEY_FALLBACK_STATUSES
                )
                if can_fallback:
                    logger.warning(
                        "User embedding key returned %d, falling back to app key",
                        exc.response.status_code,
                    )
                    continue
                raise last_error from exc
            except httpx.TimeoutException as exc:
                raise EmbeddingError("OpenRouter embedding API timed out") from exc

    async def _post_embedding_with_key(
        self,
        payload: dict,
        api_key: str,
    ) -> dict:
        client = self._client or httpx.AsyncClient(timeout=60.0)
        should_close = self._client is None
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if should_close:
            async with client:
                resp = await client.post(_EMBED_URL, headers=headers, json=payload)
                resp.raise_for_status()
        else:
            resp = await client.post(_EMBED_URL, headers=headers, json=payload)
            resp.raise_for_status()
        return resp.json()
