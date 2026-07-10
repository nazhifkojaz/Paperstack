"""LLM service for auto-highlight paper analysis and chat streaming."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, AsyncIterator, Callable, Optional

import httpx

from app.schemas.types import ChatMessageDict, HighlightDict
from app.services.exceptions import LLMRateLimitError, LLMProviderError
from app.core.config import settings

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _openrouter_model(
    model_id: str,
    label: str,
    description: str,
    requires_byok: bool | None = None,
) -> dict[str, str | bool]:
    if requires_byok is None:
        requires_byok = not model_id.endswith(":free")
    return {
        "id": model_id,
        "label": label,
        "description": description,
        "requires_byok": requires_byok,
    }


OPENROUTER_MODELS = [
    _openrouter_model(
        "nvidia/nemotron-3-super-120b-a12b:free",
        "Nemotron 3 Super 120B",
        "NVIDIA's Nemotron 3 Super model (default)",
    ),
    _openrouter_model(
        "openai/gpt-oss-120b:free",
        "GPT-OSS 120B",
        "OpenAI's open-source 120B model",
    ),
    _openrouter_model(
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "Nemotron 3 Ultra 550B",
        "NVIDIA's ultra-scale Nemotron 3 model",
    ),
    _openrouter_model(
        "anthropic/claude-fable-5",
        "Claude Fable 5",
        "Anthropic's Claude Fable model through OpenRouter",
    ),
    _openrouter_model(
        "qwen/qwen3.7-plus",
        "Qwen3.7 Plus",
        "Qwen's plus model through OpenRouter",
    ),
    _openrouter_model(
        "minimax/minimax-m3",
        "MiniMax M3",
        "MiniMax's M3 model through OpenRouter",
    ),
    _openrouter_model(
        "anthropic/claude-opus-4.8",
        "Claude Opus 4.8",
        "Anthropic's Claude Opus model through OpenRouter",
    ),
    _openrouter_model(
        "x-ai/grok-4.3",
        "Grok 4.3",
        "xAI's Grok model through OpenRouter",
    ),
    _openrouter_model(
        "openai/gpt-5.5",
        "GPT-5.5",
        "OpenAI's GPT model through OpenRouter",
    ),
    _openrouter_model(
        "deepseek/deepseek-v4-pro",
        "DeepSeek V4 Pro",
        "DeepSeek's V4 Pro model through OpenRouter",
    ),
    _openrouter_model(
        "deepseek/deepseek-v4-flash",
        "DeepSeek V4 Flash",
        "DeepSeek's V4 Flash model through OpenRouter",
    ),
    _openrouter_model(
        "qwen/qwen3.6-plus",
        "Qwen3.6 Plus",
        "Qwen's plus model through OpenRouter",
    ),
]

FREE_MODELS = [m for m in OPENROUTER_MODELS if not m["requires_byok"]]
OPENROUTER_MODEL_IDS = {str(m["id"]) for m in OPENROUTER_MODELS}
OPENROUTER_BYOK_MODEL_IDS = {
    str(m["id"]) for m in OPENROUTER_MODELS if m["requires_byok"]
}

DEFAULT_FREE_MODEL = str(FREE_MODELS[0]["id"])

CATEGORY_DEFINITIONS = {
    "findings": "Key results, conclusions, statistical outcomes, novel contributions",
    "methods": "Core experimental design, techniques, key parameters",
    "definitions": "Important terminology, formal definitions, acronyms introduced",
    "limitations": "Stated limitations, caveats, threats to validity, future work",
    "background": "Critical prior work referenced, foundational context",
}


def strip_markdown_fences(text: str | None) -> str:
    """Strip markdown code fences from LLM response."""
    if not text:
        return ""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _parse_highlights_json(raw_response: str | None) -> list[HighlightDict]:
    """Parse and validate LLM response into highlight list."""
    if not raw_response:
        logger.warning("Empty LLM response in highlight extraction")
        return []
    cleaned = strip_markdown_fences(raw_response)

    # Sanitize literal newlines inside JSON string values (some LLMs emit these)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        sanitized = re.sub(r'(?<=[^\\])\n(?=[^"]*")', " ", cleaned)
        try:
            data = json.loads(sanitized)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse LLM response as JSON: {e}")

    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array, got {type(data).__name__}")

    highlights = []
    for item in data:
        highlights.append(
            {
                "text": item.get("text", ""),
                "page": item.get("page", 0),
                "category": item.get("category", "unknown"),
                "reason": item.get("reason", ""),
            }
        )

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


def _parse_queries_json(
    raw_response: str | None, categories: list[str]
) -> dict[str, str]:
    """Parse LLM response into a {category: query} dict."""
    if not raw_response:
        logger.warning("Empty LLM response in query generation")
        return {}
    cleaned = strip_markdown_fences(raw_response)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        sanitized = re.sub(r'(?<=[^\\])\n(?=[^"]*")', " ", cleaned)
        try:
            data = json.loads(sanitized)
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse query-generation JSON: %s", e)
            return {}

    if not isinstance(data, dict):
        logger.warning("Expected dict from query generation, got %s", type(data))
        return {}

    result: dict[str, str] = {}
    for cat in categories:
        if cat in data and isinstance(data[cat], str) and data[cat].strip():
            result[cat] = data[cat].strip()
    return result


SUMMARY_FIELDS = (
    "tldr",
    "problem",
    "method",
    "dataset",
    "result",
    "contribution",
)


def _parse_summary_json(raw_response: str | None) -> dict[str, Any]:
    """Parse the paper-summary LLM response into a validated dict."""
    if not raw_response:
        raise ValueError("Empty LLM response in summary generation")
    cleaned = strip_markdown_fences(raw_response)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        sanitized = re.sub(r'(?<=[^\\])\n(?=[^"]*")', " ", cleaned)
        try:
            data = json.loads(sanitized)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse summary JSON: {e}: {cleaned[:200]}")
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object, got {type(data).__name__}")

    parsed: dict[str, Any] = {}
    for field in SUMMARY_FIELDS:
        value = data.get(field)
        parsed[field] = (
            value.strip() if isinstance(value, str) and value.strip() else None
        )
    claims = data.get("key_claims")
    if isinstance(claims, list):
        parsed["key_claims"] = [
            c.strip() for c in claims if isinstance(c, str) and c.strip()
        ][:5]
    else:
        parsed["key_claims"] = []
    if not parsed["tldr"]:
        raise ValueError("Summary response missing required 'tldr' field")
    return parsed


class LLMService:
    """Service for calling LLM providers.

    Requires a shared httpx.AsyncClient for connection pooling.
    """

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None):
        self._client = http_client
        self.last_reasoning_trace: str | None = None

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
        on_response: Callable[[dict], None] | None = None,
        timeout: httpx.Timeout | None = None,
    ) -> str:
        client = self._require_client()
        try:
            resp = await client.post(
                url, headers=headers, json=json_body, timeout=timeout
            )
        except httpx.TimeoutException:
            raise LLMProviderError(provider_name, 0, timeout_msg)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self._handle_http_error(exc, provider_name)
        data = resp.json()
        if pre_check_fn:
            pre_check_fn(data)
        if on_response:
            on_response(data)
        return extract_fn(data)

    async def call_openrouter(
        self,
        system_prompt: str,
        user_prompt: str,
        api_key: str,
        model: str = DEFAULT_FREE_MODEL,
        reasoning_effort: str | None = None,
    ) -> str:
        """Call OpenRouter API (OpenAI-compatible) and return text content.

        When reasoning_effort is set (e.g. "medium"), OpenRouter will enable
        extended reasoning/thinking on the model and include a reasoning trace
        in the response. The trace is stored on self.last_reasoning_trace.

        If a reasoning call times out (httpx timeout or Cloudflare 524),
        the call is automatically retried without reasoning to avoid
        blocking the pipeline on slow model responses.
        """
        logger.info(
            "Calling OpenRouter %s (prompt: %d chars, reasoning: %s)",
            model,
            len(user_prompt),
            reasoning_effort or "off",
        )

        json_body: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        if reasoning_effort:
            json_body["reasoning"] = {"effort": reasoning_effort}

        def _on_response(data: dict) -> None:
            reasoning = data["choices"][0]["message"].get("reasoning")
            if reasoning:
                self.last_reasoning_trace = reasoning
                logger.debug("OpenRouter reasoning trace (%d chars)", len(reasoning))
            else:
                self.last_reasoning_trace = None

        # Use a longer read timeout for reasoning calls to avoid
        # httpx-side timeouts while the model is thinking
        call_timeout = (
            httpx.Timeout(
                connect=10.0,
                read=settings.OPENROUTER_REASONING_TIMEOUT_READ,
                write=10.0,
                pool=10.0,
            )
            if reasoning_effort
            else None
        )

        try:
            result = await self._call_provider(
                url=f"{OPENROUTER_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json_body=json_body,
                extract_fn=lambda d: d["choices"][0]["message"]["content"],
                provider_name="openrouter",
                pre_check_fn=_check_openrouter_error,
                on_response=_on_response,
                timeout=call_timeout,
            )
            logger.info("OpenRouter responded successfully")
            return result
        except LLMProviderError as e:
            if not reasoning_effort:
                raise
            if e.status_code not in (0, 400, 422, 524):
                raise
            logger.warning(
                "OpenRouter reasoning call failed (status=%d), retrying without reasoning: %s",
                e.status_code,
                e,
            )
            self.last_reasoning_trace = None
            del json_body["reasoning"]
            result = await self._call_provider(
                url=f"{OPENROUTER_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json_body=json_body,
                extract_fn=lambda d: d["choices"][0]["message"]["content"],
                provider_name="openrouter",
                pre_check_fn=_check_openrouter_error,
            )
            logger.info(
                "OpenRouter responded successfully (fallback without reasoning)"
            )
            return result

    # --- Streaming methods for chat ---

    async def _stream_openai_compatible(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        provider_name: str = "openai",
    ) -> AsyncIterator[str]:
        """Stream tokens from an OpenAI-compatible SSE endpoint."""
        client = self._require_client()
        async with client.stream("POST", url, headers=headers, json=payload) as resp:
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                self._handle_http_error(exc, provider_name)
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
        self,
        system_prompt: str,
        messages: list[ChatMessageDict],
        api_key: str,
        model: str = DEFAULT_FREE_MODEL,
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
            provider_name="openrouter",
        ):
            yield token

    async def extract_highlights_from_passages(
        self,
        passages: list,
        categories: list[str],
        provider: str,
        api_key: str,
        model: Optional[str] = None,
    ) -> list[HighlightDict]:
        """Given pre-filtered passages, pick verbatim highlight-worthy quotes.

        Each passage must have: content, page_number, categories (list[str]).
        Always a single non-streaming call.
        """
        if not passages:
            return []

        cat_defs = "\n".join(
            f"- {k}: {CATEGORY_DEFINITIONS[k]}"
            for k in categories
            if k in CATEGORY_DEFINITIONS
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

        if provider == "openrouter":
            reasoning_effort = (
                settings.OPENROUTER_REASONING_EFFORT
                if settings.OPENROUTER_REASONING_ENABLED
                else None
            )
            raw = await self.call_openrouter(
                system_prompt,
                user_prompt,
                api_key,
                model=model or DEFAULT_FREE_MODEL,
                reasoning_effort=reasoning_effort,
            )
        else:
            raise ValueError(f"Unknown provider: {provider}")

        return _parse_highlights_json(raw)

    async def generate_paper_queries(
        self,
        title: str,
        abstract: str,
        categories: list[str],
        provider: str,
        api_key: str,
        model: str | None = None,
    ) -> dict[str, str]:
        """Generate paper-specific search queries for highlight category retrieval.

        Uses the paper's title and abstract to produce category-specific search
        queries that match the paper's actual vocabulary, named entities, and
        key phrases. Falls back to empty dict on any error.
        """
        cat_defs = "\n".join(
            f"- {k}: {CATEGORY_DEFINITIONS[k]}"
            for k in categories
            if k in CATEGORY_DEFINITIONS
        )

        system_prompt = (
            "You are an academic research assistant. Generate expanded search queries "
            "for vector similarity search to find relevant passages within a specific paper. "
            "Incorporate the paper's own terminology, named entities, and key phrases."
        )

        user_prompt = (
            f"Paper Title: {title}\n\n"
            f"Abstract:\n{abstract[:3000]}\n\n"
            f"For each category below, generate a search query (10-30 words) that "
            f"includes key terms, proper nouns, and technical vocabulary from THIS paper:\n\n"
            f"{cat_defs}\n\n"
            f"Return JSON (no markdown fences):\n"
            f'{{"findings": "query...", "methods": "query...", ...}}\n\n'
            f"CRITICAL: Use the paper's actual model names, datasets, metrics, "
            f"and domain terms. Do not use generic placeholder terms."
        )

        try:
            if provider == "openrouter":
                reasoning_effort = (
                    settings.OPENROUTER_REASONING_EFFORT
                    if settings.OPENROUTER_REASONING_ENABLED
                    else None
                )
                raw = await self.call_openrouter(
                    system_prompt,
                    user_prompt,
                    api_key,
                    model=model or DEFAULT_FREE_MODEL,
                    reasoning_effort=reasoning_effort,
                )
            else:
                logger.warning("Unknown provider for query generation: %s", provider)
                return {}
        except Exception:
            logger.exception("Failed to generate paper-specific queries")
            return {}

        return _parse_queries_json(raw, categories)

    async def generate_paper_summary(
        self,
        title: str,
        source_text: str,
        provider: str,
        api_key: str,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Generate a structured summary of a paper from its abstract/conclusion.

        Returns {tldr, problem, method, dataset, result, contribution,
        key_claims}. Raises ValueError on unparseable responses and
        LLMProviderError/LLMRateLimitError on provider failures.
        """
        system_prompt = (
            "You are an academic paper analysis assistant. You produce faithful, "
            "compact structured summaries of research papers. Only state facts "
            "supported by the provided text; use null when a field cannot be "
            "determined."
        )
        user_prompt = (
            f"Paper Title: {title}\n\n"
            f"Text (abstract, and conclusion when available):\n{source_text[:6000]}\n\n"
            "Summarize into JSON (no markdown fences) with EXACTLY these keys:\n"
            "{\n"
            '  "tldr": "2-3 sentence plain-language summary",\n'
            '  "problem": "the problem addressed, 1-2 sentences or null",\n'
            '  "method": "the approach/technique, 1-2 sentences or null",\n'
            '  "dataset": "datasets/corpora/benchmarks used, or null",\n'
            '  "result": "headline quantitative/qualitative results, or null",\n'
            '  "contribution": "the main novel contribution, or null",\n'
            '  "key_claims": ["3-5 short verbatim-or-near-verbatim claims"]\n'
            "}\n\n"
            "CRITICAL: use the paper's actual terminology; do not invent "
            "numbers or datasets not present in the text."
        )
        if provider != "openrouter":
            raise ValueError(f"Unknown provider: {provider}")
        reasoning_effort = (
            settings.OPENROUTER_REASONING_EFFORT
            if settings.OPENROUTER_REASONING_ENABLED
            else None
        )
        raw = await self.call_openrouter(
            system_prompt,
            user_prompt,
            api_key,
            model=model or DEFAULT_FREE_MODEL,
            reasoning_effort=reasoning_effort,
        )
        return _parse_summary_json(raw)
