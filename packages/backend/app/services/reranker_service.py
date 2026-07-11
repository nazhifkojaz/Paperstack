"""Cross-encoder reranking service (optional second retrieval stage).

When enabled (``settings.RERANKER_MODEL`` set), retrieval returns a wider
candidate pool from hybrid search and re-orders it with a cross-encoder before
truncating to ``top_k``. This recovers ranking quality that bi-encoder retrieval
leaves on the table — gold chunks ranked 11–50 by the first stage get pulled
into the top-k that actually reaches the model.

Validated on PeerQA: ``bge-reranker-v2-m3`` (pool_k=50) lifted Recall@10
0.603 → 0.729 and MRR 0.375 → 0.527, tying PeerQA's best published reranker.

Two interchangeable backends, selected by ``settings.RERANKER_BACKEND``:

* ``"openrouter"`` (default) — ``OpenRouterRerankerService`` calls OpenRouter's
  ``/v1/rerank`` endpoint (e.g. ``cohere/rerank-v3.5``). No heavy deps; reuses
  the same ``OPENROUTER_API_KEY`` as chat/embeddings and the same user-key →
  app-key fallback pattern as ``EmbeddingService``. On a 402 (out of credits)
  from the primary model it retries once with ``RERANKER_FALLBACK_MODEL``
  (typically a ``:free`` slug) before giving up.
* ``"local"`` — ``RerankerService`` loads a HuggingFace cross-encoder via
  torch + sentence-transformers (imported lazily, e.g.
  ``BAAI/bge-reranker-v2-m3``).

Both backends expose the same contract::

    pool_k: int
    async def order(query: str, docs: list[str]) -> list[int]  # indices, best first

so ``retrieve_with_rerank`` and the chat orchestrator are backend-agnostic.

A disabled config (``RERANKER_MODEL=None``) keeps behaviour identical to the
pre-reranker path.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from app.core.config import settings
from app.services.exceptions import RerankError

logger = logging.getLogger(__name__)

_RERANK_URL = "https://openrouter.ai/api/v1/rerank"
# HTTP statuses that indicate the *user's* key is unfunded/forbidden/throttled
# and should be retried with the app key. Mirrors EmbeddingService.
_USER_KEY_FALLBACK_STATUSES = {402, 403, 429}


class RerankServiceProtocol:
    """Informal protocol implemented by both reranker backends."""

    pool_k: int

    async def order(self, query: str, docs: list[str]) -> list[int]:
        """Indices of ``docs`` sorted by descending relevance to ``query``."""
        raise NotImplementedError


class RerankerService(RerankServiceProtocol):
    """Local HuggingFace cross-encoder reranker (sentence-transformers CrossEncoder).

    The model is loaded on first use (``cross_encoder`` property), not at
    construction, so creating a disabled/placeholder instance is free.
    """

    def __init__(
        self,
        model_id: str,
        pool_k: int = 50,
        device: str | None = None,
        max_length: int = 512,
    ) -> None:
        self.model_id = model_id
        self.pool_k = pool_k
        self.max_length = max_length
        self._device = device
        self._ce = None

    @property
    def device(self) -> str:
        if self._device is None:
            import torch

            self._device = "cuda" if torch.cuda.is_available() else "cpu"
        return self._device

    @property
    def cross_encoder(self):  # noqa: ANN201 (lazy; type comes from an optional dep)
        if self._ce is None:
            from sentence_transformers import CrossEncoder

            logger.info("loading reranker %s on %s", self.model_id, self.device)
            self._ce = CrossEncoder(
                self.model_id, device=self.device, max_length=self.max_length
            )
        return self._ce

    async def order(self, query: str, docs: list[str]) -> list[int]:
        """Indices of ``docs`` sorted by descending relevance to ``query``."""
        if not docs:
            return []
        pairs = [(query, d) for d in docs]
        try:
            # ``predict`` is CPU/GPU-bound and can take 100ms–1s+ over a
            # pool_k=50; run it off the event loop and guard any torch/ST
            # failure so the orchestrator's hybrid-retrieval fallback applies.
            scores = await asyncio.to_thread(self.cross_encoder.predict, pairs)
        except Exception as exc:
            raise RerankError(f"Local reranker predict failed: {exc}") from exc
        return sorted(range(len(docs)), key=lambda i: float(scores[i]), reverse=True)


class _CreditsExhausted(RerankError):
    """Every key candidate returned 402 — signals the caller to try the fallback model."""


class OpenRouterRerankerService(RerankServiceProtocol):
    """Calls OpenRouter ``/v1/rerank`` (e.g. ``cohere/rerank-v3.5``).

    Mirrors ``EmbeddingService``: same ``OPENROUTER_API_KEY``, same user-key →
    app-key fallback on ``{402, 403, 429}``. When the primary model 402s (out of
    credits) on every key, it retries once with ``fallback_model_id`` (typically
    a ``:free`` slug) before raising ``RerankError``.
    """

    def __init__(
        self,
        model_id: str,
        pool_k: int = 50,
        fallback_model_id: str | None = None,
        http_client: Optional[httpx.AsyncClient] = None,
        user_api_key: str | None = None,
    ) -> None:
        self.model_id = model_id
        self.pool_k = pool_k
        self.fallback_model_id = fallback_model_id
        self._client = http_client
        self._user_api_key = user_api_key

    async def order(
        self, query: str, docs: list[str], user_api_key: str | None = None
    ) -> list[int]:
        """Indices of ``docs`` sorted by descending relevance to ``query``.

        Tries the primary model, then the fallback model (only on 402). Raises
        ``RerankError`` if every attempt fails.
        """
        if not docs:
            return []

        key_candidates = self._key_candidates(user_api_key)
        if not key_candidates:
            raise RerankError("OPENROUTER_API_KEY is not configured")

        models = [self.model_id]
        if self.fallback_model_id and self.fallback_model_id not in models:
            models.append(self.fallback_model_id)

        last_exc: RerankError | None = None
        for model_id in models:
            payload = {
                "model": model_id,
                "query": query,
                "documents": docs,
                "top_n": len(docs),
            }
            try:
                data = await self._post_rerank(payload, key_candidates)
            except _CreditsExhausted as exc:
                # Out of credits on this model — try the (typically :free) fallback.
                last_exc = exc
                logger.warning(
                    "Rerank model %s returned 402; trying fallback %s",
                    model_id,
                    self.fallback_model_id,
                )
                continue
            return self._rank_indices(data)

        raise last_exc or RerankError("rerank failed: all models exhausted")

    @staticmethod
    def _rank_indices(data: dict) -> list[int]:
        """Map an OpenRouter rerank response to best-first doc indices."""
        results = data.get("results", [])
        ordered = sorted(
            results, key=lambda r: r.get("relevance_score", 0.0), reverse=True
        )
        # Drop malformed entries (missing/non-int ``index``) instead of raising
        # KeyError — ``retrieve_with_rerank`` already tolerates a shorter list
        # and out-of-range indices via its own range guard.
        return [r["index"] for r in ordered if isinstance(r.get("index"), int)]

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

    async def _post_rerank(
        self,
        payload: dict,
        key_candidates: list[tuple[str, str]],
    ) -> dict:
        """Post the rerank request, falling back across key candidates.

        A 402 on the final key raises ``_CreditsExhausted`` so ``order`` can
        retry with the fallback model; any other failure raises ``RerankError``.
        """
        for index, (key_owner, api_key) in enumerate(key_candidates):
            try:
                return await self._post_with_key(payload, api_key)
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                can_fallback_key = (
                    key_owner == "user"
                    and index + 1 < len(key_candidates)
                    and status in _USER_KEY_FALLBACK_STATUSES
                )
                if can_fallback_key:
                    logger.warning(
                        "User rerank key returned %d, falling back to app key",
                        status,
                    )
                    continue
                if status == 402:
                    raise _CreditsExhausted(
                        f"OpenRouter rerank returned 402: {exc.response.text[:200]}"
                    ) from exc
                raise RerankError(
                    f"OpenRouter rerank API returned {status}: "
                    f"{exc.response.text[:300]}"
                ) from exc
            except httpx.TimeoutException as exc:
                raise RerankError("OpenRouter rerank API timed out") from exc
            except httpx.HTTPError as exc:
                # Other transport-level failures (ConnectError, ReadError,
                # RemoteProtocolError, …) are subclasses of HTTPError but not
                # of TimeoutException. These are transient by nature — surface
                # them as RerankError so the chat orchestrator falls back to
                # plain hybrid retrieval instead of crashing the request.
                # Trying the next key candidate would not help (same endpoint),
                # so we do not continue the loop here.
                raise RerankError(f"OpenRouter rerank request failed: {exc}") from exc
        # Defensive terminal raise: the loop above always returns or raises, but
        # an empty key_candidates list (or a future regression) must not silently
        # return None and crash the caller with an AttributeError downstream.
        raise RerankError("rerank failed: no key candidate succeeded")

    async def _post_with_key(
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
                resp = await client.post(_RERANK_URL, headers=headers, json=payload)
                resp.raise_for_status()
        else:
            resp = await client.post(_RERANK_URL, headers=headers, json=payload)
            resp.raise_for_status()
        return resp.json()


# Module-level cache so a long-running process (or benchmark) loads/inits once.
_reranker_cache: dict[tuple, RerankServiceProtocol] = {}


def get_reranker(
    model_id: str | None = None,
    pool_k: int | None = None,
) -> RerankServiceProtocol | None:
    """Return a cached reranker for the configured model, or None if disabled.

    Defaults to ``settings.RERANKER_MODEL`` / ``settings.RERANKER_POOL_K`` so
    call sites can just do ``get_reranker()``. Backend is chosen by
    ``settings.RERANKER_BACKEND``.
    """
    model_id = model_id or settings.RERANKER_MODEL
    if not model_id:
        return None
    pool_k = pool_k if pool_k is not None else settings.RERANKER_POOL_K
    backend = settings.RERANKER_BACKEND
    fallback = settings.RERANKER_FALLBACK_MODEL
    key = (backend, model_id, pool_k, fallback)
    if key not in _reranker_cache:
        if backend == "local":
            _reranker_cache[key] = RerankerService(model_id, pool_k=pool_k)
        else:
            _reranker_cache[key] = OpenRouterRerankerService(
                model_id,
                pool_k=pool_k,
                fallback_model_id=fallback,
            )
    return _reranker_cache[key]


async def retrieve_with_rerank(
    vector_search,
    reranker: RerankServiceProtocol,
    query_text: str,
    query_vector: list[float],
    pdf_id,
    user_id,
    top_k: int,
    db,
):
    """Two-stage retrieval: hybrid pool_k → cross-encoder rerank → top_k results."""
    pool = await vector_search.search_pdf(
        query_vector, pdf_id, user_id, reranker.pool_k, db, query_text=query_text
    )
    if not pool:
        return []
    order = await reranker.order(query_text, [r.content for r in pool])
    n = len(pool)
    # Guard against a malformed index from a provider response: an out-of-range
    # index would raise IndexError (not RerankError) and bypass the orchestrator's
    # graceful fallback. Drop such entries and return the surviving best-first.
    return [pool[i] for i in order[:top_k] if isinstance(i, int) and 0 <= i < n]


async def retrieve_collection_with_rerank(
    vector_search,
    reranker: RerankServiceProtocol,
    query_text: str,
    query_vector: list[float],
    collection_id,
    user_id,
    top_k: int,
    db,
):
    """Two-stage collection retrieval: wide hybrid pool -> per-PDF cap ->
    cross-encoder rerank -> global top_k.

    The per-PDF cap (settings.COLLECTION_RERANK_PER_PDF_CAP) keeps a single
    long paper from filling the candidate pool, so the reranked context can
    draw on every member paper that has relevant chunks.
    """
    pool = await vector_search.search_collection(
        query_vector=query_vector,
        collection_id=collection_id,
        user_id=user_id,
        top_k=reranker.pool_k,
        db=db,
        query_text=query_text,
    )
    if not pool:
        return []

    # Diversity guard: pool is already best-first; keep at most N per PDF.
    cap = settings.COLLECTION_RERANK_PER_PDF_CAP
    per_pdf: dict = {}
    capped = []
    for r in pool:
        count = per_pdf.get(r.pdf_id, 0)
        if count < cap:
            per_pdf[r.pdf_id] = count + 1
            capped.append(r)

    order = await reranker.order(query_text, [r.content for r in capped])
    n = len(capped)
    # Same malformed-index guard as retrieve_with_rerank: an out-of-range
    # index would raise IndexError (not RerankError) and bypass the
    # orchestrator's graceful fallback.
    return [capped[i] for i in order[:top_k] if isinstance(i, int) and 0 <= i < n]
