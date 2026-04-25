import json
import pytest
import httpx
from unittest.mock import AsyncMock, patch
from app.services.llm_service import (
    LLMService, _parse_highlights_json, strip_markdown_fences,
    CATEGORY_COLORS,
)


def test_strip_markdown_fences_json():
    raw = '```json\n[{"text": "hello", "page": 1, "category": "findings", "reason": "test"}]\n```'
    assert strip_markdown_fences(raw) == '[{"text": "hello", "page": 1, "category": "findings", "reason": "test"}]'


def test_strip_markdown_fences_no_fence():
    raw = '[{"text": "hello"}]'
    assert strip_markdown_fences(raw) == '[{"text": "hello"}]'


def test_strip_markdown_fences_plain_backticks():
    raw = '```\n[{"text": "x"}]\n```'
    assert strip_markdown_fences(raw) == '[{"text": "x"}]'


def test_parse_highlights_json_valid():
    raw = json.dumps([
        {"text": "Some finding", "page": 1, "category": "findings", "reason": "Important result"},
        {"text": "A method", "page": 3, "category": "methods", "reason": "Core technique"},
    ])
    highlights = _parse_highlights_json(raw)
    assert len(highlights) == 2
    assert highlights[0]["text"] == "Some finding"
    assert highlights[0]["category"] == "findings"


def test_parse_highlights_json_with_fences():
    raw = '```json\n[{"text": "x", "page": 1, "category": "findings", "reason": "y"}]\n```'
    highlights = _parse_highlights_json(raw)
    assert len(highlights) == 1


def test_parse_highlights_json_invalid_json():
    with pytest.raises(ValueError, match="Failed to parse"):
        _parse_highlights_json("not json at all")


def test_parse_highlights_json_missing_fields():
    raw = json.dumps([{"text": "hello"}])  # missing page, category, reason
    highlights = _parse_highlights_json(raw)
    assert len(highlights) == 1
    assert highlights[0]["page"] == 0
    assert highlights[0]["category"] == "unknown"
    assert highlights[0]["reason"] == ""


def test_parse_highlights_json_not_list():
    raw = json.dumps({"text": "not a list"})
    with pytest.raises(ValueError, match="Expected JSON array"):
        _parse_highlights_json(raw)


def test_category_colors():
    assert "findings" in CATEGORY_COLORS
    assert "methods" in CATEGORY_COLORS
    assert "definitions" in CATEGORY_COLORS
    assert "limitations" in CATEGORY_COLORS
    assert "background" in CATEGORY_COLORS
    for color in CATEGORY_COLORS.values():
        assert color.startswith("#")
        assert len(color) == 7


# --- extract_highlights_from_passages ---


@pytest.mark.asyncio
async def test_extract_highlights_from_passages_glm():
    service = LLMService()
    mock_response = json.dumps([
        {"text": "Key result", "page": 1, "category": "findings", "reason": "Primary finding"},
    ])
    passage = type("P", (), {"content": "some text", "page_number": 1, "categories": ["findings"]})()
    with patch.object(service, "call_glm", new=AsyncMock(return_value=mock_response)):
        highlights = await service.extract_highlights_from_passages(
            [passage], ["findings"], "glm", "fake-key",
        )
    assert len(highlights) == 1
    assert highlights[0]["text"] == "Key result"


@pytest.mark.asyncio
async def test_extract_highlights_from_passages_empty():
    service = LLMService()
    result = await service.extract_highlights_from_passages(
        [], ["findings"], "glm", "fake-key",
    )
    assert result == []


@pytest.mark.asyncio
async def test_extract_highlights_from_passages_unknown_provider():
    service = LLMService()
    passage = type("P", (), {"content": "text", "page_number": 1, "categories": ["findings"]})()
    with pytest.raises(ValueError, match="Unknown provider"):
        await service.extract_highlights_from_passages(
            [passage], ["findings"], "unknown_provider", "key",
        )


# --- Direct OpenRouter method tests (Phase 7.1) ---


class TestCallOpenRouter:
    """Direct unit tests for LLMService.call_openrouter."""

    @pytest.mark.asyncio
    async def test_success_returns_text(self):
        """Successful call returns the content from the response."""
        import respx
        from app.services.llm_service import OPENROUTER_BASE_URL

        async with httpx.AsyncClient() as client:
            service = LLMService(http_client=client)
            with respx.mock:
                respx.post(f"{OPENROUTER_BASE_URL}/chat/completions").mock(
                    return_value=httpx.Response(
                        200,
                        json={
                            "choices": [
                                {"message": {"content": "Hello from OpenRouter"}}
                            ]
                        },
                    )
                )
                result = await service.call_openrouter("sys", "user", "test-key")
        assert result == "Hello from OpenRouter"

    @pytest.mark.asyncio
    async def test_429_raises_rate_limit_error(self):
        """429 response should raise LLMRateLimitError."""
        import respx
        from app.services.llm_service import OPENROUTER_BASE_URL
        from app.services.exceptions import LLMRateLimitError

        async with httpx.AsyncClient() as client:
            service = LLMService(http_client=client)
            with respx.mock:
                respx.post(f"{OPENROUTER_BASE_URL}/chat/completions").mock(
                    return_value=httpx.Response(429, text="Rate limited")
                )
                with pytest.raises(LLMRateLimitError):
                    await service.call_openrouter("sys", "user", "test-key")

    @pytest.mark.asyncio
    async def test_timeout_raises_provider_error(self):
        """Timeout should raise LLMProviderError."""
        import respx
        from app.services.llm_service import OPENROUTER_BASE_URL
        from app.services.exceptions import LLMProviderError

        async with httpx.AsyncClient() as client:
            service = LLMService(http_client=client)
            with respx.mock:
                respx.post(f"{OPENROUTER_BASE_URL}/chat/completions").mock(
                    side_effect=httpx.TimeoutException("timed out")
                )
                with pytest.raises(LLMProviderError, match="timed out"):
                    await service.call_openrouter("sys", "user", "test-key")

    @pytest.mark.asyncio
    async def test_500_raises_provider_error(self):
        """500 response should raise LLMProviderError."""
        import respx
        from app.services.llm_service import OPENROUTER_BASE_URL
        from app.services.exceptions import LLMProviderError

        async with httpx.AsyncClient() as client:
            service = LLMService(http_client=client)
            with respx.mock:
                respx.post(f"{OPENROUTER_BASE_URL}/chat/completions").mock(
                    return_value=httpx.Response(500, text="Internal Server Error")
                )
                with pytest.raises(LLMProviderError) as exc_info:
                    await service.call_openrouter("sys", "user", "test-key")
                assert exc_info.value.status_code == 500


class TestStreamOpenRouter:
    """Direct unit tests for LLMService.stream_openrouter."""

    @pytest.mark.asyncio
    async def test_yields_tokens(self):
        """Should yield content tokens from SSE stream."""
        import respx
        from app.services.llm_service import OPENROUTER_BASE_URL

        sse_body = (
            "data: {\"choices\":[{\"delta\":{\"content\":\"Hello \"}}]}\n\n"
            "data: {\"choices\":[{\"delta\":{\"content\":\"world\"}}]}\n\n"
            "data: [DONE]\n\n"
        )

        async with httpx.AsyncClient() as client:
            service = LLMService(http_client=client)
            with respx.mock:
                respx.post(f"{OPENROUTER_BASE_URL}/chat/completions").mock(
                    return_value=httpx.Response(
                        200,
                        text=sse_body,
                        headers={"content-type": "text/event-stream"},
                    )
                )
                tokens = []
                async for token in service.stream_openrouter(
                    "sys", [{"role": "user", "content": "hi"}], "test-key"
                ):
                    tokens.append(token)
        assert tokens == ["Hello ", "world"]

    @pytest.mark.asyncio
    async def test_skips_empty_delta(self):
        """Should skip SSE chunks with empty content."""
        import respx
        from app.services.llm_service import OPENROUTER_BASE_URL

        sse_body = (
            "data: {\"choices\":[{\"delta\":{\"role\":\"assistant\"}}]}\n\n"
            "data: {\"choices\":[{\"delta\":{\"content\":\"token\"}}]}\n\n"
            "data: [DONE]\n\n"
        )

        async with httpx.AsyncClient() as client:
            service = LLMService(http_client=client)
            with respx.mock:
                respx.post(f"{OPENROUTER_BASE_URL}/chat/completions").mock(
                    return_value=httpx.Response(
                        200,
                        text=sse_body,
                        headers={"content-type": "text/event-stream"},
                    )
                )
                tokens = []
                async for token in service.stream_openrouter(
                    "sys", [{"role": "user", "content": "hi"}], "test-key"
                ):
                    tokens.append(token)
        assert tokens == ["token"]

    @pytest.mark.asyncio
    async def test_429_before_stream_raises_http_error(self):
        """429 on streaming endpoint should raise httpx.HTTPStatusError."""
        import respx
        from app.services.llm_service import OPENROUTER_BASE_URL

        async with httpx.AsyncClient() as client:
            service = LLMService(http_client=client)
            with respx.mock:
                respx.post(f"{OPENROUTER_BASE_URL}/chat/completions").mock(
                    return_value=httpx.Response(429, text="Rate limited")
                )
                with pytest.raises(httpx.HTTPStatusError) as exc_info:
                    async for _ in service.stream_openrouter(
                        "sys", [{"role": "user", "content": "hi"}], "test-key"
                    ):
                        pass
                assert exc_info.value.response.status_code == 429
