"""LLM service for auto-highlight paper analysis and chat streaming."""
from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable, Optional

import httpx

from app.schemas.types import ChatMessageDict, HighlightDict
from app.services.exceptions import LLMRateLimitError, LLMProviderError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

FREE_MODELS = [
    {
        "id": "nvidia/nemotron-3-super-120b-a12b:free",
        "label": "Nemotron 3 Super 120B",
        "description": "NVIDIA's large model, good general-purpose quality",
    },
    {
        "id": "google/gemma-4-31b-it:free",
        "label": "Gemma 4 31B",
        "description": "Google's instruction-tuned model, strong reasoning",
    },
    {
        "id": "tencent/hy3-preview:free",
        "label": "Hunyuan 3 Preview",
        "description": "Tencent's large preview model",
    },
    {
        "id": "google/gemma-4-26b-a4b-it:free",
        "label": "Gemma 4 26B",
        "description": "Google's compact instruction-tuned Gemma 4 variant",
    },
    {
        "id": "minimax/minimax-m2.5:free",
        "label": "MiniMax M2.5",
        "description": "MiniMax's efficient long-context model",
    },
]

DEFAULT_FREE_MODEL = FREE_MODELS[0]["id"]

CATEGORY_COLORS = {
    "findings": "#22c55e",
    "methods": "#3b82f6",
    "definitions": "#a855f7",
    "limitations": "#f97316",
    "background": "#6b7280",
}

CATEGORY_DEFINITIONS = {
    "findings": "Key results, conclusions, statistical outcomes, novel contributions",
    "methods": "Core experimental design, techniques, key parameters",
    "definitions": "Important terminology, formal definitions, acronyms introduced",
    "limitations": "Stated limitations, caveats, threats to validity, future work",
    "background": "Critical prior work referenced, foundational context",
}


def strip_markdown_fences(text: str) -> str:
    """Strip markdown code fences from LLM response."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _parse_highlights_json(raw_response: str) -> list[HighlightDict]:
    """Parse and validate LLM response into highlight list."""
    cleaned = strip_markdown_fences(raw_response)

    # Sanitize literal newlines inside JSON string values (some LLMs emit these)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        sanitized = re.sub(r'(?<=[^\\])\n(?=[^"]*")', ' ', cleaned)
        try:
            data = json.loads(sanitized)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse LLM response as JSON: {e}")

    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array, got {type(data).__name__}")

    highlights = []
    for item in data:
        highlights.append({
            "text": item.get("text", ""),
            "page": item.get("page", 0),
            "category": item.get("category", "unknown"),
            "reason": item.get("reason", ""),
        })

    return highlights


def _check_openrouter_error(data: dict) -> None:
    """Check OpenRouter response for error objects and raise if found."""
    if "error" in data:
        err = data["error"]
        logger.error("OpenRouter error response: %s", err)
        error_msg = err.get("message", str(err))
        metadata = err.get("metadata", {})
        if metadata:
            error_msg = f"{error_msg} | {metadata}"
        raise LLMProviderError("openrouter", 0, error_msg)


class LLMService:
    """Service for calling LLM providers.

    Requires a shared httpx.AsyncClient for connection pooling.
    """

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None):
        self._client = http_client

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("LLMService requires a shared HTTP client")
        return self._client

    def _handle_http_error(self, exc: httpx.HTTPStatusError, provider: str) -> None:
        """Translate httpx HTTP errors into domain exceptions."""
        if exc.response.status_code == 429:
            raise LLMRateLimitError(provider) from exc
        raise LLMProviderError(
            provider, exc.response.status_code, exc.response.text[:200]
        ) from exc

    async def _call_provider(
        self,
        url: str,
        headers: dict[str, str],
        json_body: dict[str, Any],
        extract_fn: Callable[[dict], str],
        provider_name: str,
        timeout_msg: str = "Request timed out.",
        pre_check_fn: Callable[[dict], None] | None = None,
    ) -> str:
        client = self._require_client()
        try:
            resp = await client.post(url, headers=headers, json=json_body)
        except httpx.TimeoutException:
            raise LLMProviderError(provider_name, 0, timeout_msg)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self._handle_http_error(exc, provider_name)
        data = resp.json()
        if pre_check_fn:
            pre_check_fn(data)
        return extract_fn(data)

    async def call_glm(self, system_prompt: str, user_prompt: str, api_key: str) -> str:
        """Call Zhipu AI GLM API and return extracted text content."""
        return await self._call_provider(
            url="https://api.z.ai/api/paas/v4/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json_body={
                "model": "glm-4.7-flash",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.1,
            },
            extract_fn=lambda d: d["choices"][0]["message"]["content"],
            provider_name="glm",
            timeout_msg="Request timed out. The paper may be too large for this model.",
        )

    async def call_gemini(self, system_prompt: str, user_prompt: str, api_key: str) -> str:
        """Call Google Gemini API and return extracted text content."""
        return await self._call_provider(
            url="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
            headers={"x-goog-api-key": api_key},
            json_body={
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"parts": [{"text": user_prompt}]}],
                "generationConfig": {"temperature": 0.1},
            },
            extract_fn=lambda d: d["candidates"][0]["content"]["parts"][0]["text"],
            provider_name="gemini",
            timeout_msg="Request timed out. The paper may be too large for this model.",
        )

    async def call_openai(self, system_prompt: str, user_prompt: str, api_key: str) -> str:
        """Call OpenAI Chat Completions API and return text content."""
        return await self._call_provider(
            url="https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json_body={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
            },
            extract_fn=lambda d: d["choices"][0]["message"]["content"],
            provider_name="openai",
        )

    async def call_anthropic(self, system_prompt: str, user_prompt: str, api_key: str) -> str:
        """Call Anthropic Messages API and return text content."""
        return await self._call_provider(
            url="https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            json_body={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 4096,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            },
            extract_fn=lambda d: d["content"][0]["text"],
            provider_name="anthropic",
        )

    async def call_openrouter(self, system_prompt: str, user_prompt: str, api_key: str, model: str = DEFAULT_FREE_MODEL) -> str:
        """Call OpenRouter API (OpenAI-compatible) and return text content."""
        logger.info(
            "Calling OpenRouter %s (prompt: %d chars, key: ...%s)",
            model, len(user_prompt), api_key[-4:],
        )
        result = await self._call_provider(
            url=f"{OPENROUTER_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json_body={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
            },
            extract_fn=lambda d: d["choices"][0]["message"]["content"],
            provider_name="openrouter",
            pre_check_fn=_check_openrouter_error,
        )
        logger.info("OpenRouter responded successfully")
        return result

    # --- Streaming methods for chat ---

    async def _stream_openai_compatible(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> AsyncIterator[str]:
        """Stream tokens from an OpenAI-compatible SSE endpoint."""
        client = self._require_client()
        async with client.stream("POST", url, headers=headers, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    try:
                        chunk = json.loads(line[6:])
                        delta = chunk["choices"][0].get("delta", {})
                        if "content" in delta and delta["content"]:
                            yield delta["content"]
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

    async def stream_openai(
        self, system_prompt: str, messages: list[ChatMessageDict], api_key: str
    ) -> AsyncIterator[str]:
        """Stream tokens from OpenAI Chat Completions (SSE)."""
        async for token in self._stream_openai_compatible(
            url="https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            payload={
                "model": "gpt-4o-mini",
                "messages": [{"role": "system", "content": system_prompt}] + messages,
                "temperature": 0.3,
                "stream": True,
            },
        ):
            yield token

    async def stream_anthropic(
        self, system_prompt: str, messages: list[ChatMessageDict], api_key: str
    ) -> AsyncIterator[str]:
        """Stream tokens from Anthropic Messages API (SSE)."""
        client = self._require_client()
        async with client.stream(
            "POST",
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 4096,
                "system": system_prompt,
                "messages": messages,
                "stream": True,
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    try:
                        event = json.loads(line[6:])
                        if event.get("type") == "content_block_delta":
                            text = event.get("delta", {}).get("text", "")
                            if text:
                                yield text
                    except (json.JSONDecodeError, KeyError):
                        continue

    async def stream_gemini(
        self, system_prompt: str, messages: list[ChatMessageDict], api_key: str
    ) -> AsyncIterator[str]:
        """Stream tokens from Gemini (SSE)."""
        contents = [
            {
                "role": m["role"] if m["role"] != "assistant" else "model",
                "parts": [{"text": m["content"]}],
            }
            for m in messages
        ]
        client = self._require_client()
        async with client.stream(
            "POST",
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:streamGenerateContent?alt=sse",
            headers={"x-goog-api-key": api_key},
            json={
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": contents,
                "generationConfig": {"temperature": 0.3},
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    try:
                        chunk = json.loads(line[6:])
                        parts = (
                            chunk.get("candidates", [{}])[0]
                            .get("content", {})
                            .get("parts", [])
                        )
                        for part in parts:
                            if "text" in part and part["text"]:
                                yield part["text"]
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

    async def stream_glm(
        self, system_prompt: str, messages: list[ChatMessageDict], api_key: str
    ) -> AsyncIterator[str]:
        """Stream tokens from GLM (OpenAI-compatible SSE)."""
        async for token in self._stream_openai_compatible(
            url="https://api.z.ai/api/paas/v4/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            payload={
                "model": "glm-4.7-flash",
                "messages": [{"role": "system", "content": system_prompt}] + messages,
                "temperature": 0.3,
                "stream": True,
            },
        ):
            yield token

    async def stream_openrouter(
        self, system_prompt: str, messages: list[ChatMessageDict], api_key: str, model: str = DEFAULT_FREE_MODEL
    ) -> AsyncIterator[str]:
        """Stream tokens from OpenRouter (OpenAI-compatible SSE)."""
        async for token in self._stream_openai_compatible(
            url=f"{OPENROUTER_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            payload={
                "model": model,
                "messages": [{"role": "system", "content": system_prompt}] + messages,
                "temperature": 0.3,
                "stream": True,
            },
        ):
            yield token

    async def extract_highlights_from_passages(
        self,
        passages: list,
        categories: list[str],
        provider: str,
        api_key: str,
        model: Optional[str] = None,
        db: AsyncSession | None = None,
    ) -> list[HighlightDict]:
        """Given pre-filtered passages, pick verbatim highlight-worthy quotes.

        Each passage must have: content, page_number, categories (list[str]).
        Always a single non-streaming call. For OpenRouter, records usage.
        """
        from app.services.openrouter_usage_service import openrouter_usage_service

        if not passages:
            return []

        cat_defs = "\n".join(
            f"- {k}: {CATEGORY_DEFINITIONS[k]}" for k in categories if k in CATEGORY_DEFINITIONS
        )

        numbered = []
        for i, p in enumerate(passages, 1):
            cats = ",".join(p.categories)
            numbered.append(
                f"[Passage {i}] (page {p.page_number}; candidate categories: {cats})\n"
                f"{p.content}"
            )
        passages_block = "\n\n".join(numbered)

        system_prompt = (
            "You are an academic paper analysis assistant. You will be given a set of "
            "pre-filtered passages from a research paper. Your job is to select the most "
            "highlight-worthy VERBATIM sentences and classify them. You must copy text "
            "character-for-character from the provided passages — never paraphrase."
        )

        user_prompt = f"""Below are passages from an academic paper, each pre-tagged with candidate categories.

Categories to surface: {", ".join(categories)}

Category definitions:
{cat_defs}

Instructions:
1. From each passage, select 0-3 verbatim sentences that are highlight-worthy.
2. Aim for 2-4 quotes per requested category across the whole set.
3. Copy each quote EXACTLY as written. Preserve punctuation, spacing, casing.
4. Use the page number from the passage header.
5. Classify each quote into exactly one of the requested categories.
6. Write a short reason (under 20 words).

Return JSON (no markdown fencing):
[
  {{"text": "exact verbatim quote", "page": 3, "category": "findings", "reason": "..."}}
]

CRITICAL:
- text must be a substring of a passage above. Do NOT invent or rephrase.
- Skip any quote you cannot copy exactly.
- Prefer complete single sentences (1-3 sentences max).

--- PASSAGES ---
{passages_block}"""

        if provider == "openrouter" and db is not None:
            await openrouter_usage_service.record_and_check(db)

        if provider == "glm":
            raw = await self.call_glm(system_prompt, user_prompt, api_key)
        elif provider == "gemini":
            raw = await self.call_gemini(system_prompt, user_prompt, api_key)
        elif provider == "openai":
            raw = await self.call_openai(system_prompt, user_prompt, api_key)
        elif provider == "anthropic":
            raw = await self.call_anthropic(system_prompt, user_prompt, api_key)
        elif provider == "openrouter":
            raw = await self.call_openrouter(system_prompt, user_prompt, api_key, model=model or DEFAULT_FREE_MODEL)
        else:
            raise ValueError(f"Unknown provider: {provider}")

        return _parse_highlights_json(raw)


# Registry mapping provider name → streaming method name on LLMService
STREAM_PROVIDERS: dict[str, str] = {
    "openai": "stream_openai",
    "anthropic": "stream_anthropic",
    "gemini": "stream_gemini",
    "glm": "stream_glm",
    "openrouter": "stream_openrouter",
}
