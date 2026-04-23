"""LLM service for auto-highlight paper analysis and chat streaming."""
import json
import logging
import re
from typing import Any, AsyncIterator, Optional

import httpx

from app.services.exceptions import LLMRateLimitError, LLMProviderError

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MAX_CHARS = 20_000

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


def build_prompt(paper_text: str, categories: list[str], max_chars: int = 0) -> tuple[str, str]:
    """Build system and user prompts for paper analysis."""
    if max_chars and len(paper_text) > max_chars:
        paper_text = paper_text[:max_chars] + "\n\n[TRUNCATED: paper text exceeded model context limit]"

    cat_defs = "\n".join(
        f"- {k}: {v}" for k, v in CATEGORY_DEFINITIONS.items() if k in categories
    )

    system_prompt = (
        "You are an academic paper analysis assistant. Your task is to identify "
        "the most important passages in a research paper and copy them CHARACTER "
        "FOR CHARACTER from the source text. You are a copy-paste machine — "
        "never rephrase, summarize, or reconstruct what you read."
    )

    user_prompt = f"""Below is the full text of an academic paper. Page boundaries are marked with "--- PAGE {{n}} ---".

Categories to identify: {", ".join(categories)}

Category definitions:
{cat_defs}

Instructions:
1. Read the entire paper carefully
2. Select 10-20 of the most important passages matching the requested categories
3. For each passage, copy the text EXACTLY as it appears — character for character, including spacing and punctuation
4. Identify which page it appears on (look at the nearest "--- PAGE N ---" marker above the passage)
5. Classify it into one of the requested categories
6. Write a brief reason explaining WHY this passage is important

Return a JSON array (no markdown fencing):
[
  {{
    "text": "exact verbatim quote from the paper",
    "page": 1,
    "category": "findings",
    "reason": "This presents the primary result showing X improves Y by Z%"
  }}
]

CRITICAL RULES:
- The "text" field must be a character-for-character copy from the paper text below
- Find the passage in the text, then copy it by selecting and reproducing it exactly
- Do NOT reconstruct from memory — look at the text and copy it
- Do NOT include passages you cannot find verbatim in the text below
- Do not combine sentences from different paragraphs
- Prefer complete sentences (1-3 sentences max per entry)
- NEVER change even a single word — "agentic" must stay "agentic", not "agent"
- If you cannot find the exact text, skip that passage entirely
- VERIFY: before including any quote, search the paper text above to confirm it appears exactly

--- PAPER TEXT ---
{paper_text}"""

    return system_prompt, user_prompt


def parse_llm_response(raw_response: str) -> list[dict[str, Any]]:
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

    async def call_glm(self, system_prompt: str, user_prompt: str, api_key: str) -> str:
        """Call Zhipu AI GLM API and return extracted text content."""
        client = self._require_client()
        try:
            resp = await client.post(
                "https://api.z.ai/api/paas/v4/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "glm-4.7-flash",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.1,
                },
            )
        except httpx.TimeoutException:
            raise LLMProviderError("glm", 0, "Request timed out. The paper may be too large for this model.")
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self._handle_http_error(exc, "glm")
        return resp.json()["choices"][0]["message"]["content"]

    async def call_gemini(self, system_prompt: str, user_prompt: str, api_key: str) -> str:
        """Call Google Gemini API and return extracted text content."""
        client = self._require_client()
        try:
            resp = await client.post(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
                headers={"x-goog-api-key": api_key},
                json={
                    "system_instruction": {"parts": [{"text": system_prompt}]},
                    "contents": [{"parts": [{"text": user_prompt}]}],
                    "generationConfig": {"temperature": 0.1},
                },
            )
        except httpx.TimeoutException:
            raise LLMProviderError("gemini", 0, "Request timed out. The paper may be too large for this model.")
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self._handle_http_error(exc, "gemini")
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]

    async def call_openai(self, system_prompt: str, user_prompt: str, api_key: str) -> str:
        """Call OpenAI Chat Completions API and return text content."""
        client = self._require_client()
        try:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.2,
                },
            )
        except httpx.TimeoutException:
            raise LLMProviderError("openai", 0, "Request timed out.")
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self._handle_http_error(exc, "openai")
        return resp.json()["choices"][0]["message"]["content"]

    async def call_anthropic(self, system_prompt: str, user_prompt: str, api_key: str) -> str:
        """Call Anthropic Messages API and return text content."""
        client = self._require_client()
        try:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 4096,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
            )
        except httpx.TimeoutException:
            raise LLMProviderError("anthropic", 0, "Request timed out.")
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self._handle_http_error(exc, "anthropic")
        return resp.json()["content"][0]["text"]

    async def call_openrouter(self, system_prompt: str, user_prompt: str, api_key: str, model: str = DEFAULT_FREE_MODEL) -> str:
        """Call OpenRouter API (OpenAI-compatible) and return text content."""
        client = self._require_client()
        logger.info(
            "Calling OpenRouter %s (prompt: %d chars, key: ...%s)",
            model, len(user_prompt), api_key[-4:],
        )
        try:
            resp = await client.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.2,
                },
            )
        except httpx.TimeoutException:
            raise LLMProviderError("openrouter", 0, "Request timed out.")
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self._handle_http_error(exc, "openrouter")
        logger.info("OpenRouter responded: status=%d, body=%s", resp.status_code, resp.text[:500])
        data = resp.json()
        if "error" in data:
            err = data["error"]
            logger.error("OpenRouter error response: %s", err)
            error_msg = err.get("message", str(err))
            metadata = err.get("metadata", {})
            if metadata:
                error_msg = f"{error_msg} | {metadata}"
            raise LLMProviderError("openrouter", resp.status_code, error_msg)
        return data["choices"][0]["message"]["content"]

    # --- Streaming methods for chat ---

    async def stream_openai(
        self, system_prompt: str, messages: list[dict], api_key: str
    ) -> AsyncIterator[str]:
        """Stream tokens from OpenAI Chat Completions (SSE)."""
        client = self._require_client()
        async with client.stream(
            "POST",
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "system", "content": system_prompt}] + messages,
                "temperature": 0.3,
                "stream": True,
            },
        ) as resp:
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

    async def stream_anthropic(
        self, system_prompt: str, messages: list[dict], api_key: str
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
        self, system_prompt: str, messages: list[dict], api_key: str
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
        self, system_prompt: str, messages: list[dict], api_key: str
    ) -> AsyncIterator[str]:
        """Stream tokens from GLM (OpenAI-compatible SSE)."""
        client = self._require_client()
        async with client.stream(
            "POST",
            "https://api.z.ai/api/paas/v4/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "glm-4.7-flash",
                "messages": [{"role": "system", "content": system_prompt}] + messages,
                "temperature": 0.3,
                "stream": True,
            },
        ) as resp:
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

    async def stream_openrouter(
        self, system_prompt: str, messages: list[dict], api_key: str, model: str = DEFAULT_FREE_MODEL
    ) -> AsyncIterator[str]:
        """Stream tokens from OpenRouter (OpenAI-compatible SSE)."""
        client = self._require_client()
        async with client.stream(
            "POST",
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{"role": "system", "content": system_prompt}] + messages,
                "temperature": 0.3,
                "stream": True,
            },
        ) as resp:
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

    async def analyze_paper(
        self,
        paper_text: str,
        categories: list[str],
        provider: str,
        api_key: str,
        model: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Analyze a paper and return structured highlights."""
        max_chars = OPENROUTER_MAX_CHARS if provider == "openrouter" else 0
        system_prompt, user_prompt = build_prompt(paper_text, categories, max_chars)

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

        return parse_llm_response(raw)


# Registry mapping provider name → streaming method name on LLMService
STREAM_PROVIDERS: dict[str, str] = {
    "openai": "stream_openai",
    "anthropic": "stream_anthropic",
    "gemini": "stream_gemini",
    "glm": "stream_glm",
    "openrouter": "stream_openrouter",
}
