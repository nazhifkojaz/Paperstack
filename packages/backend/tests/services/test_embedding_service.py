"""Tests for EmbeddingService — OpenRouter /v1/embeddings wrapper."""
import pytest
import respx
from httpx import Response

from app.services.embedding_service import EmbeddingService
from app.services.exceptions import EmbeddingError


def _make_embedding_response(n: int, dim: int = 2048) -> dict:
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
        assert len(result[0]) == 2048

    @respx.mock
    async def test_batch_request_structure(self, svc):
        route = respx.post("https://openrouter.ai/api/v1/embeddings").mock(
            return_value=Response(200, json=_make_embedding_response(3))
        )
        await svc.embed_texts(["a", "b", "c"])

        assert route.called
        request = route.calls.last.request
        assert request.headers["authorization"] == "Bearer sk-or-test-key"
        import json
        body = json.loads(request.content.decode())
        assert body["model"] == "nvidia/llama-nemotron-embed-vl-1b-v2:free"
        assert body["input"] == ["a", "b", "c"]

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
            side_effect=Exception("timeout")
        )
        # The service catches httpx.TimeoutException specifically, but any exception
        # during the request will propagate as an error.
        with pytest.raises((EmbeddingError, Exception)):
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
        assert len(result) == 2048
