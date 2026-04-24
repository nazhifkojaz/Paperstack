"""Tests for LLM service: call_openrouter, build_prompt, analyze_paper."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from app.services.llm_service import (
    LLMService,
    build_prompt,
    parse_llm_response,
    DEFAULT_FREE_MODEL,
)
from app.services.exceptions import LLMProviderError, LLMRateLimitError


# --- build_prompt ---


class TestBuildPrompt:
    def test_no_truncation_when_within_limit(self):
        text = "A" * 500
        system, user = build_prompt(text, ["findings"], max_chars=1000)
        assert text in user
        assert "[TRUNCATED" not in user

    def test_truncation_applied_when_exceeds_limit(self):
        text = "A" * 2000
        system, user = build_prompt(text, ["findings"], max_chars=1000)
        assert "A" * 1000 in user
        assert "[TRUNCATED" in user
        assert "A" * 2000 not in user

    def test_no_truncation_when_max_chars_zero(self):
        text = "A" * 100_000
        system, user = build_prompt(text, ["findings"], max_chars=0)
        assert text in user

    def test_prompt_contains_categories(self):
        system, user = build_prompt("some text", ["findings", "methods"])
        assert "findings" in user
        assert "methods" in user


# --- parse_llm_response ---


class TestParseLlmResponse:
    def test_valid_json_array(self):
        raw = '[{"text": "finding", "page": 1, "category": "findings", "reason": "test"}]'
        result = parse_llm_response(raw)
        assert len(result) == 1
        assert result[0]["text"] == "finding"

    def test_strips_markdown_fences(self):
        raw = '```json\n[{"text": "t", "page": 1, "category": "findings", "reason": "r"}]\n```'
        result = parse_llm_response(raw)
        assert len(result) == 1

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match="Failed to parse"):
            parse_llm_response("not json at all")

    def test_non_array_raises(self):
        with pytest.raises(ValueError, match="Expected JSON array"):
            parse_llm_response('{"text": "oops"}')

    def test_missing_fields_get_defaults(self):
        raw = '[{"text": "partial"}]'
        result = parse_llm_response(raw)
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


# --- analyze_paper ---


class TestAnalyzePaper:
    async def test_openrouter_truncates_paper(self):
        long_text = "A" * 200_001  # Exceed OPENROUTER_MAX_CHARS (200_000)
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '[{"text":"t","page":1,"category":"findings","reason":"r"}]'
                    }
                }
            ]
        }
        mock_client.post = AsyncMock(return_value=mock_response)

        svc = LLMService(http_client=mock_client)
        result = await svc.analyze_paper(long_text, ["findings"], "openrouter", "key")
        assert len(result) == 1

        # Verify the paper text was truncated in the request
        call_args = mock_client.post.call_args
        sent_text = call_args[1]["json"]["messages"][1]["content"]
        # The prompt includes instructions + paper text, so check that truncation marker exists
        # and that the paper text portion doesn't exceed max_chars
        assert "[TRUNCATED" in sent_text
        # Extract just the paper text (it's after "--- PAPER TEXT ---")
        paper_start = sent_text.find("--- PAPER TEXT ---")
        assert paper_start > 0
        paper_text = sent_text[paper_start:]
        # The paper text should be ~200_000 chars + truncation message
        assert len(paper_text) < 200_100  # 200_000 + some buffer for truncation message

    async def test_non_openrouter_no_truncation(self):
        long_text = "A" * 50_000
        svc = LLMService(http_client=AsyncMock())

        with patch.object(svc, "call_openai", new_callable=AsyncMock, return_value='[{"text":"t","page":1,"category":"findings","reason":"r"}]'):
            result = await svc.analyze_paper(long_text, ["findings"], "openai", "key")
            assert len(result) == 1
            # call_openai gets the full text
            svc.call_openai.assert_called_once()
            args = svc.call_openai.call_args[0]
            assert len(args[1]) > 50_000  # user_prompt still contains full text

    async def test_unknown_provider_raises(self):
        svc = LLMService(http_client=AsyncMock())
        with pytest.raises(ValueError, match="Unknown provider"):
            await svc.analyze_paper("text", ["findings"], "unknown_provider", "key")
