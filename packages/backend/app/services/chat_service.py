"""Chat service: builds RAG context and orchestrates streaming LLM calls."""

import logging
from typing import AsyncIterator

import tiktoken

from app.services.llm_service import LLMService, STREAM_PROVIDERS

DEFAULT_CONTEXT_MAX_TOKENS = 4000

logger = logging.getLogger(__name__)

try:
    _ENCODER = tiktoken.get_encoding("cl100k_base")
except Exception:
    _ENCODER = None

SYSTEM_PROMPT = (
    "You are a research assistant helping a user understand academic papers. "
    "Answer questions using ONLY the context excerpts provided below. "
    "If the answer is not in the context, say so clearly. "
    "Format your responses using markdown (bold for key terms, bullet points for lists). "
    "Cite page numbers by writing [p.N] after each claim."
)

COLLECTION_SYSTEM_PROMPT = (
    "You are a research assistant helping a user understand a collection of academic papers. "
    "Answer questions using ONLY the context excerpts provided below. "
    "If the answer is not in the context, say so clearly. "
    "Format your responses using markdown (bold for key terms, bullet points for lists). "
    "Each context excerpt is labelled with its paper title and page number. "
    "Cite sources using the format [Short Title, p.N] where Short Title is a brief but "
    "recognisable abbreviation of the paper title from the context header — "
    "for example 'Attention Is All You Need' becomes [Attention, p.4], "
    "'Intent Mismatch Causes LLMs...' becomes [Intent Mismatch, p.7]."
)

CONTEXT_WINDOW = 10  # maximum number of past messages sent as conversation history


def _count_tokens(text: str) -> int:
    """Count tokens in text using tiktoken, with character fallback."""
    if _ENCODER is not None:
        return len(_ENCODER.encode(text))
    return len(text) // 4


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate text to fit within max_tokens, appending a truncation marker."""
    if _ENCODER is not None:
        tokens = _ENCODER.encode(text)
        if len(tokens) <= max_tokens:
            return text
        truncated_tokens = tokens[:max_tokens]
        truncated_text = _ENCODER.decode(truncated_tokens)
        return truncated_text + "\n[...truncated]"
    remaining_chars = max_tokens * 4
    return text[:remaining_chars] + "\n[...truncated]"


def _deduplicate_chunks(
    chunks: list[dict], similarity_threshold: float = 0.9
) -> list[dict]:
    """Remove chunks with highly overlapping content.

    Uses Jaccard similarity on word sets. Keeps the first occurrence
    when duplicates are found (preserving retrieval ranking order).
    """
    if len(chunks) <= 1:
        return chunks

    unique: list[dict] = []
    unique_word_sets: list[set[str]] = []

    for chunk in chunks:
        words = set(chunk["content"].lower().split())
        if not words:
            continue
        is_dup = False
        for existing_words in unique_word_sets:
            intersection = len(words & existing_words)
            union = len(words | existing_words)
            if union > 0 and intersection / union > similarity_threshold:
                is_dup = True
                break
        if not is_dup:
            unique.append(chunk)
            unique_word_sets.append(words)

    return unique


class ChatService:
    """Chat service for building RAG context and streaming LLM replies.

    Accepts an optional LLMService instance for dependency injection.
    """

    def __init__(self, llm_service: LLMService | None = None):
        """Initialize chat service with optional LLM service.

        Args:
            llm_service: LLMService instance for streaming. If None, uses default.
        """
        self._llm_service = llm_service or LLMService()

    def build_context(
        self, chunks: list[dict], max_tokens: int = DEFAULT_CONTEXT_MAX_TOKENS
    ) -> str:
        """Format retrieved chunks into a context string for the LLM prompt.

        Each chunk dict must have 'page_number' and 'content' keys.
        Optional 'section_title' key adds section context to the header.

        Respects a token budget (max_tokens). Chunks that would exceed the
        budget are truncated with a marker; subsequent chunks are dropped.
        """
        deduped = _deduplicate_chunks(chunks)
        parts = []
        total_tokens = 0

        for c in deduped:
            header = f"[Page {c['page_number']}]"
            if c.get("section_title"):
                header = f"[Page {c['page_number']} · {c['section_title']}]"
            chunk_text = f"{header}\n{c['content']}"
            chunk_tokens = _count_tokens(chunk_text)

            if total_tokens + chunk_tokens > max_tokens:
                remaining = max_tokens - total_tokens
                if remaining > 50:
                    truncated = _truncate_to_tokens(chunk_text, remaining)
                    parts.append(truncated)
                break

            parts.append(chunk_text)
            total_tokens += chunk_tokens

        return "\n\n---\n\n".join(parts)

    def build_messages(
        self,
        context: str,
        history: list[dict],
        user_message: str,
        base_prompt: str | None = None,
    ) -> tuple[str, list[dict]]:
        """Build system prompt and message list for the LLM.

        Returns (system_prompt_with_context, messages).
        The system prompt embeds the retrieved context so every provider
        receives it the same way regardless of their message format.

        Args:
            context: formatted output of build_context()
            history: list of {"role": "user"|"assistant", "content": str} dicts
            user_message: the current user question
            base_prompt: override the default SYSTEM_PROMPT (e.g. COLLECTION_SYSTEM_PROMPT)
        """
        system = (
            (base_prompt or SYSTEM_PROMPT)
            + "\n\n## Context from the papers:\n\n"
            + context
        )
        msgs: list[dict] = []
        # Cap history to last CONTEXT_WINDOW messages
        for h in history[-CONTEXT_WINDOW:]:
            msgs.append({"role": h["role"], "content": h["content"]})
        msgs.append({"role": "user", "content": user_message})
        return system, msgs

    async def stream_reply(
        self,
        system_prompt: str,
        messages: list[dict],
        provider: str,
        api_key: str,
    ) -> AsyncIterator[str]:
        """Stream tokens from the chosen LLM provider.

        Args:
            system_prompt: built by build_messages()
            messages: built by build_messages()
            provider: one of 'openai', 'anthropic', 'gemini', 'glm'
            api_key: the user's (or in-house) API key for the provider

        Yields:
            text tokens as they arrive from the provider
        """
        method_name = STREAM_PROVIDERS.get(provider)
        if not method_name:
            raise ValueError(
                f"Unknown provider '{provider}'. Valid: {list(STREAM_PROVIDERS)}"
            )
        stream_method = getattr(self._llm_service, method_name)
        async for token in stream_method(system_prompt, messages, api_key):
            yield token


# Default singleton for backward compatibility (will be replaced with DI)
chat_service = ChatService()
