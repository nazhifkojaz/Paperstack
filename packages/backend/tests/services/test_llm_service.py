"""Tests for LLM service: call_openrouter, _parse_highlights_json."""
import pytest
from unittest.mock import AsyncMock, MagicMock
import httpx

from app.services.llm_service import (
    LLMService,
    _parse_highlights_json,
    DEFAULT_FREE_MODEL,
)
from app.services.exceptions import LLMProviderError, LLMRateLimitError


# --- _parse_highlights_json ---


class TestParseHighlightsJson:
    def test_valid_json_array(self):
        raw = '[{"text": "finding", "page": 1, "category": "findings", "reason": "test"}]'
        result = _parse_highlights_json(raw)
        assert len(result) == 1
        assert result[0]["text"] == "finding"

    def test_strips_markdown_fences(self):
        raw = '```json\n[{"text": "t", "page": 1, "category": "findings", "reason": "r"}]\n```'
        result = _parse_highlights_json(raw)
        assert len(result) == 1

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match="Failed to parse"):
            _parse_highlights_json("not json at all")

    def test_non_array_raises(self):
        with pytest.raises(ValueError, match="Expected JSON array"):
            _parse_highlights_json('{"text": "oops"}')

    def test_missing_fields_get_defaults(self):
        raw = '[{"text": "partial"}]'
        result = _parse_highlights_json(raw)
        assert result[0]["page"] == 0
        assert result[0]["category"] == "unknown"
        assert result[0]["reason"] == ""


# --- call_openrouter ---


class TestCallOpenRouter:
    async def test_success_returns_content(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "LLM response text"}}]
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        svc = LLMService(http_client=mock_client)
        result = await svc.call_openrouter("sys", "user", "test-key")
        assert result == "LLM response text"

        call_args = mock_client.post.call_args
        assert call_args[1]["json"]["model"] == DEFAULT_FREE_MODEL

    async def test_error_response_raises_provider_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "error": {
                "message": "Provider returned error",
                "metadata": {"raw": '{"error":"context too long"}'},
            }
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        svc = LLMService(http_client=mock_client)
        with pytest.raises(LLMProviderError, match="Provider returned error"):
            await svc.call_openrouter("sys", "user", "test-key")

    async def test_http_429_raises_rate_limit(self):
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "429", request=MagicMock(), response=mock_response
            )
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        svc = LLMService(http_client=mock_client)
        with pytest.raises(LLMRateLimitError):
            await svc.call_openrouter("sys", "user", "test-key")

    async def test_http_500_raises_provider_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "500", request=MagicMock(), response=mock_response
            )
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        svc = LLMService(http_client=mock_client)
        with pytest.raises(LLMProviderError, match="500"):
            await svc.call_openrouter("sys", "user", "test-key")

    async def test_no_client_raises_runtime_error(self):
        svc = LLMService(http_client=None)
        with pytest.raises(RuntimeError, match="shared HTTP client"):
            await svc.call_openrouter("sys", "user", "test-key")

    async def test_timeout_raises_provider_error(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        svc = LLMService(http_client=mock_client)
        with pytest.raises(LLMProviderError, match="timed out"):
            await svc.call_openrouter("sys", "user", "test-key")
