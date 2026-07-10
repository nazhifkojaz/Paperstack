"""Tests for the reranker service — OpenRouter /v1/rerank wrapper + backend dispatch."""

import httpx
import pytest
import respx
from httpx import Response

from app.services.exceptions import RerankError
from app.services.reranker_service import (
    OpenRouterRerankerService,
    RerankerService,
    _reranker_cache,
    get_reranker,
    retrieve_with_rerank,
)

_RERANK_URL = "https://openrouter.ai/api/v1/rerank"


def _make_rerank_response(index_scores: list[tuple[int, float]]) -> dict:
    """Build a fake OpenRouter rerank response.

    ``index_scores`` is given in the (arbitrary) order the API would return
    results; relevance_score drives the best-first mapping, not list order.
    """
    return {
        "results": [
            {
                "index": idx,
                "relevance_score": score,
                "document": {"text": f"doc{idx}"},
            }
            for idx, score in index_scores
        ]
    }


@pytest.fixture(autouse=True)
def _set_api_key(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.OPENROUTER_API_KEY", "sk-or-test-key")


@pytest.fixture(autouse=True)
def _clear_cache():
    _reranker_cache.clear()
    yield
    _reranker_cache.clear()


@pytest.fixture
def svc():
    return OpenRouterRerankerService("cohere/rerank-v3.5", pool_k=50)


@pytest.mark.asyncio
class TestOrder:
    @respx.mock
    async def test_orders_indices_by_relevance_descending(self, svc):
        respx.post(_RERANK_URL).mock(
            return_value=Response(
                200, json=_make_rerank_response([(1, 0.9), (0, 0.3), (2, 0.7)])
            )
        )
        order = await svc.order("query", ["a", "b", "c"])
        assert order == [1, 2, 0]  # 0.9, 0.7, 0.3

    @respx.mock
    async def test_request_structure(self, svc):
        route = respx.post(_RERANK_URL).mock(
            return_value=Response(200, json=_make_rerank_response([(0, 0.5)]))
        )
        await svc.order("what is attention?", ["chunk a", "chunk b"])

        assert route.called
        request = route.calls.last.request
        assert request.headers["authorization"] == "Bearer sk-or-test-key"
        body = request.read()
        import json

        payload = json.loads(body)
        assert payload["model"] == "cohere/rerank-v3.5"
        assert payload["query"] == "what is attention?"
        assert payload["documents"] == ["chunk a", "chunk b"]
        assert payload["top_n"] == 2

    async def test_empty_docs_short_circuits_no_api_call(self, svc):
        # No respx route registered → would raise if a call were made.
        assert await svc.order("query", []) == []

    @respx.mock
    async def test_402_falls_back_to_fallback_model(self, monkeypatch):
        svc = OpenRouterRerankerService(
            "cohere/rerank-v3.5",
            fallback_model_id="nvidia/llama-nemotron-rerank-vl-1b-v2:free",
        )
        route = respx.post(_RERANK_URL).mock(
            side_effect=[
                Response(402, text="insufficient credits"),
                Response(200, json=_make_rerank_response([(2, 0.8), (0, 0.1)])),
            ]
        )

        order = await svc.order("query", ["a", "b", "c"])

        assert route.call_count == 2
        assert order == [2, 0]  # from the fallback response
        import json

        primary_body = json.loads(route.calls[0].request.read())
        fallback_body = json.loads(route.calls[1].request.read())
        assert primary_body["model"] == "cohere/rerank-v3.5"
        assert fallback_body["model"] == "nvidia/llama-nemotron-rerank-vl-1b-v2:free"

    @respx.mock
    async def test_402_without_fallback_raises(self, svc):
        route = respx.post(_RERANK_URL).mock(
            return_value=Response(402, text="insufficient credits")
        )
        with pytest.raises(RerankError, match="402"):
            await svc.order("query", ["a", "b"])
        assert route.call_count == 1

    @respx.mock
    async def test_both_models_402_raises(self):
        svc = OpenRouterRerankerService(
            "cohere/rerank-v3.5", fallback_model_id="nvidia/some:free"
        )
        route = respx.post(_RERANK_URL).mock(
            side_effect=[
                Response(402, text="insufficient credits"),
                Response(402, text="still no credits"),
            ]
        )
        with pytest.raises(RerankError, match="402"):
            await svc.order("query", ["a", "b"])
        assert route.call_count == 2

    @respx.mock
    async def test_non_402_error_does_not_try_fallback(self):
        svc = OpenRouterRerankerService(
            "cohere/rerank-v3.5", fallback_model_id="nvidia/some:free"
        )
        route = respx.post(_RERANK_URL).mock(
            return_value=Response(500, text="internal error")
        )
        with pytest.raises(RerankError, match="500"):
            await svc.order("query", ["a", "b"])
        assert route.call_count == 1  # fallback not attempted

    @respx.mock
    async def test_timeout_raises(self, svc):
        respx.post(_RERANK_URL).mock(side_effect=httpx.TimeoutException("timeout"))
        with pytest.raises(RerankError, match="timed out"):
            await svc.order("query", ["a", "b"])

    @respx.mock
    async def test_transport_error_raises_rerank_error(self, svc):
        # A non-timeout transport failure (ConnectError/ReadError) is a subclass
        # of httpx.HTTPError but NOT httpx.TimeoutException. Before the fix these
        # escaped uncaught and crashed chat instead of triggering the fallback.
        respx.post(_RERANK_URL).mock(side_effect=httpx.ConnectError("refused"))
        with pytest.raises(RerankError, match="request failed"):
            await svc.order("query", ["a", "b"])

    async def test_rank_indices_drops_malformed_entries(self):
        # A missing or non-int ``index`` must be dropped, not raise KeyError —
        # otherwise a malformed provider response bypasses the orchestrator's
        # hybrid-retrieval fallback.
        data = {
            "results": [
                {"index": 1, "relevance_score": 0.9},
                {"relevance_score": 0.8},  # missing index
                {"index": "x", "relevance_score": 0.7},  # non-int index
                {"index": 0, "relevance_score": 0.5},
            ]
        }
        assert OpenRouterRerankerService._rank_indices(data) == [1, 0]

    async def test_missing_api_key_raises(self, svc, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.OPENROUTER_API_KEY", None)
        with pytest.raises(RerankError, match="OPENROUTER_API_KEY"):
            await svc.order("query", ["a", "b"])


class TestGetRerankerDispatch:
    def test_disabled_when_model_none(self, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.RERANKER_MODEL", None)
        assert get_reranker() is None

    def test_openrouter_backend_default(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.config.settings.RERANKER_MODEL", "cohere/rerank-v3.5"
        )
        monkeypatch.setattr("app.core.config.settings.RERANKER_BACKEND", "openrouter")
        monkeypatch.setattr(
            "app.core.config.settings.RERANKER_FALLBACK_MODEL", "nvidia/x:free"
        )
        rr = get_reranker()
        assert isinstance(rr, OpenRouterRerankerService)
        assert rr.model_id == "cohere/rerank-v3.5"
        assert rr.fallback_model_id == "nvidia/x:free"
        assert rr.pool_k == 50

    def test_openrouter_instance_cached(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.config.settings.RERANKER_MODEL", "cohere/rerank-v3.5"
        )
        monkeypatch.setattr("app.core.config.settings.RERANKER_BACKEND", "openrouter")
        assert get_reranker() is get_reranker()

    def test_local_backend_returns_local_reranker(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.config.settings.RERANKER_MODEL", "BAAI/bge-reranker-v2-m3"
        )
        monkeypatch.setattr("app.core.config.settings.RERANKER_BACKEND", "local")
        rr = get_reranker()
        assert isinstance(rr, RerankerService)
        assert rr.model_id == "BAAI/bge-reranker-v2-m3"
        assert rr.pool_k == 50


@pytest.mark.asyncio
class TestRetrieveWithRerank:
    async def test_drops_out_of_range_indices(self):
        """A malformed provider index must not raise (would bypass the fallback)."""
        from unittest.mock import AsyncMock, MagicMock

        pool = [MagicMock(content=f"doc{i}") for i in range(3)]
        vector_search = MagicMock()
        vector_search.search_pdf = AsyncMock(return_value=pool)
        reranker = MagicMock(pool_k=50)
        # 9 is out of range; 1 and 0 are valid — best-first after dropping 9.
        reranker.order = AsyncMock(return_value=[9, 1, 0])

        result = await retrieve_with_rerank(
            vector_search, reranker, "q", [0.1], "pdf", "u", 10, MagicMock()
        )

        assert result == [pool[1], pool[0]]

    async def test_empty_pool_returns_empty(self):
        from unittest.mock import AsyncMock, MagicMock

        vector_search = MagicMock()
        vector_search.search_pdf = AsyncMock(return_value=[])
        reranker = MagicMock(pool_k=50)
        reranker.order = AsyncMock(return_value=[])

        result = await retrieve_with_rerank(
            vector_search, reranker, "q", [0.1], "pdf", "u", 10, MagicMock()
        )

        assert result == []
        reranker.order.assert_not_called()
