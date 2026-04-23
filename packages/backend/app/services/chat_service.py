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
    "Answer questions using ONLY the context excerpts and paper metadata provided below. "
    "If the answer is not in the context, say so clearly. "
    "Format your responses using markdown (bold for key terms, bullet points for lists). "
    "Cite page numbers by writing [p.N] after each claim."
)

COLLECTION_SYSTEM_PROMPT = (
    "You are a research assistant helping a user understand a collection of academic papers. "
    "Answer questions using ONLY the context excerpts and paper metadata provided below. "
    "If the answer is not in the context, say so clearly. "
    "Format your responses using markdown (bold for key terms, bullet points for lists). "
    "Each context excerpt is labelled with its paper title and page number. "
    "Cite sources using the format [Short Title, p.N] where Short Title is a brief but "
    "recognisable abbreviation of the paper title from the context header — "
    "for example 'Attention Is All You Need' becomes [Attention, p.4], "
    "'Intent Mismatch Causes LLMs...' becomes [Intent Mismatch, p.7]."
)

CONTEXT_WINDOW = 10  # maximum number of past messages sent as conversation history


def _format_paper_metadata(metadata: dict | list[dict] | None) -> str:
    """Format paper metadata into a compact section for the system prompt.

    Single-PDF: {"title": "...", "authors": "...", "year": 2024}
    Collection: [{"title": "...", "authors": "...", "year": 2024}, ...]
    """
    if metadata is None:
        return ""

    if isinstance(metadata, dict):
        parts = ["## Paper Metadata:"]
        if metadata.get("title"):
            parts.append(f"Title: {metadata['title']}")
        if metadata.get("authors"):
            parts.append(f"Authors: {metadata['authors']}")
        if metadata.get("year"):
            parts.append(f"Year: {metadata['year']}")
        return "\n".join(parts) if len(parts) > 1 else ""

    # Collection: list of dicts
    lines = ["## Paper Metadata:"]
    for i, m in enumerate(metadata, 1):
        title = m.get("title", "Untitled")
        authors = m.get("authors")
        year = m.get("year")
        entry = f"{i}. {title}"
        if authors:
            entry += f" — {authors}"
        if year:
            entry += f" ({year})"
        lines.append(entry)
    return "\n".join(lines) if len(lines) > 1 else ""


def _count_tokens(text: str) -> int:
    if _ENCODER is not None:
        return len(_ENCODER.encode(text))
    return len(text) // 4


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
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
        self._llm_service = llm_service or LLMService()

    def build_context(
        self, chunks: list[dict], max_tokens: int = DEFAULT_CONTEXT_MAX_TOKENS
    ) -> str:
        """Format retrieved chunks into a context string for the LLM prompt.

        Respects a token budget (max_tokens). Chunks that would exceed the
        budget are truncated with a marker; subsequent chunks are dropped.
        """
        deduped = _deduplicate_chunks(chunks)
        parts = []
        total_tokens = 0

        for c in deduped:
            end_page = c.get("end_page_number")
            if end_page and end_page > c["page_number"]:
                page_label = f"Pages {c['page_number']}-{end_page}"
            else:
                page_label = f"Page {c['page_number']}"
            header = f"[{page_label}]"
            if c.get("section_title"):
                header = f"[{page_label} · {c['section_title']}]"
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
        paper_metadata: dict | list[dict] | None = None,
    ) -> tuple[str, list[dict]]:
        """Build system prompt and message list for the LLM.

        The system prompt embeds the retrieved context so every provider
        receives it the same way regardless of their message format.
        """
        metadata_section = _format_paper_metadata(paper_metadata)
        parts = [base_prompt or SYSTEM_PROMPT]
        if metadata_section:
            parts.append(metadata_section)
        parts.append("## Context from the papers:\n\n" + context)
        system = "\n\n".join(parts)
        msgs: list[dict] = []
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
        model: str | None = None,
    ) -> AsyncIterator[str]:
        method_name = STREAM_PROVIDERS.get(provider)
        if not method_name:
            raise ValueError(
                f"Unknown provider '{provider}'. Valid: {list(STREAM_PROVIDERS)}"
            )
        stream_method = getattr(self._llm_service, method_name)
        kwargs: dict = {"system_prompt": system_prompt, "messages": messages, "api_key": api_key}
        if model and provider == "openrouter":
            kwargs["model"] = model
        async for token in stream_method(**kwargs):
            yield token
