"""Tests for EmbeddingService — OpenRouter /v1/embeddings wrapper."""
import json

import httpx
import pytest
import respx
from httpx import Response

from app.services.embedding_service import EmbeddingService
from app.services.exceptions import EmbeddingError


def _make_embedding_response(n: int, dim: int = 1024) -> dict:
    """Build a fake OpenAI-compatible embedding response."""
    return {
        "data": [
            {"index": i, "embedding": [0.01 * (i + 1)] * dim} for i in range(n)
        ],
        "usage": {"prompt_tokens": n * 10, "total_tokens": n * 10},
    }


@pytest.fixture
def svc():
    return EmbeddingService()


@pytest.fixture(autouse=True)
def set_api_key(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.OPENROUTER_API_KEY", "sk-or-test-key")


@pytest.mark.asyncio
class TestEmbedTexts:
    @respx.mock
    async def test_single_text(self, svc):
        respx.post("https://openrouter.ai/api/v1/embeddings").mock(
            return_value=Response(200, json=_make_embedding_response(1))
        )
        result = await svc.embed_texts(["hello"])
        assert len(result) == 1
        assert len(result[0]) == 1024

    @respx.mock
    async def test_batch_request_structure(self, svc):
        route = respx.post("https://openrouter.ai/api/v1/embeddings").mock(
            return_value=Response(200, json=_make_embedding_response(3))
        )
        await svc.embed_texts(["a", "b", "c"])

        assert route.called
        request = route.calls.last.request
        assert request.headers["authorization"] == "Bearer sk-or-test-key"
        body = json.loads(request.content.decode())
        assert body["model"] == "qwen/qwen3-embedding-8b"
        assert body["input"] == ["a", "b", "c"]
        assert body["dimensions"] == 1024
        assert body["provider"] == {"order": ["nebius", "deepinfra"], "allow_fallbacks": True}

    @respx.mock
    async def test_user_key_is_primary_when_provided(self, svc):
        route = respx.post("https://openrouter.ai/api/v1/embeddings").mock(
            return_value=Response(200, json=_make_embedding_response(1))
        )

        await svc.embed_texts(["hello"], user_api_key="sk-user-key")

        request = route.calls.last.request
        assert request.headers["authorization"] == "Bearer sk-user-key"

    @respx.mock
    async def test_user_key_balance_error_falls_back_to_app_key(self, svc):
        route = respx.post("https://openrouter.ai/api/v1/embeddings").mock(
            side_effect=[
                Response(402, text="insufficient credits"),
                Response(200, json=_make_embedding_response(1)),
            ]
        )

        result = await svc.embed_texts(["hello"], user_api_key="sk-user-key")

        assert len(result) == 1
        assert route.call_count == 2
        assert route.calls[0].request.headers["authorization"] == "Bearer sk-user-key"
        assert route.calls[1].request.headers["authorization"] == "Bearer sk-or-test-key"

    @respx.mock
    async def test_user_key_auth_error_does_not_fallback(self, svc):
        route = respx.post("https://openrouter.ai/api/v1/embeddings").mock(
            return_value=Response(401, text="invalid key")
        )

        with pytest.raises(EmbeddingError, match="401"):
            await svc.embed_texts(["hello"], user_api_key="sk-user-key")

        assert route.call_count == 1

    @respx.mock
    async def test_empty_input(self, svc):
        result = await svc.embed_texts([])
        assert result == []

    async def test_missing_api_key_raises(self, svc, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.OPENROUTER_API_KEY", None)
        with pytest.raises(EmbeddingError, match="OPENROUTER_API_KEY"):
            await svc.embed_texts(["hello"])

    @respx.mock
    async def test_http_error_raises(self, svc):
        respx.post("https://openrouter.ai/api/v1/embeddings").mock(
            return_value=Response(429, text="rate limited")
        )
        with pytest.raises(EmbeddingError, match="429"):
            await svc.embed_texts(["hello"])

    @respx.mock
    async def test_timeout_raises(self, svc):
        respx.post("https://openrouter.ai/api/v1/embeddings").mock(
            side_effect=httpx.TimeoutException("timeout")
        )
        with pytest.raises(EmbeddingError, match="timed out"):
            await svc.embed_texts(["hello"])

    @respx.mock
    async def test_batching_splits_requests(self, svc, monkeypatch):
        monkeypatch.setattr(svc, "BATCH_SIZE", 2)
        route = respx.post("https://openrouter.ai/api/v1/embeddings").mock(
            side_effect=[
                Response(200, json=_make_embedding_response(2)),
                Response(200, json=_make_embedding_response(1)),
            ]
        )
        result = await svc.embed_texts(["a", "b", "c"])
        assert len(result) == 3
        assert route.call_count == 2


@pytest.mark.asyncio
class TestEmbedQuery:
    @respx.mock
    async def test_returns_single_vector(self, svc):
        respx.post("https://openrouter.ai/api/v1/embeddings").mock(
            return_value=Response(200, json=_make_embedding_response(1))
        )
        result = await svc.embed_query("what is attention?")
        assert len(result) == 1024
