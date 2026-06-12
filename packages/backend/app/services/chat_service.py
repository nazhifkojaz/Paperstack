"""Chat service: builds RAG context and orchestrates streaming LLM calls."""

import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator

import tiktoken

from app.schemas.types import ChatMessageDict, ChunkDict, PaperMetadata
from app.services.llm_service import LLMService

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
    "Cite page numbers by writing [p.N] after each claim."
    "\n\nResponse Format Requirements:"
    "\n- Start with a brief 1-2 sentence summary before any headings."
    "\n- Use ### (h3) for section headings only — never # or ##."
    "\n- Use bullet points (-) for lists, never numbered lists."
    "\n- Bold key terms inline only, never use bold for section headings."
    "\n- Keep paragraphs short (2-3 sentences max)."
)

COLLECTION_SYSTEM_PROMPT = (
    "You are a research assistant helping a user understand a collection of academic papers. "
    "Answer questions using ONLY the context excerpts and paper metadata provided below. "
    "If the answer is not in the context, say so clearly. "
    "Each context excerpt is labelled with its paper title and page number. "
    "Cite sources using the format [Short Title, p.N] where Short Title is a brief but "
    "recognisable abbreviation of the paper title from the context header — "
    "for example 'Attention Is All You Need' becomes [Attention, p.4], "
    "'Intent Mismatch Causes LLMs...' becomes [Intent Mismatch, p.7]."
    "\n\nResponse Format Requirements:"
    "\n- Start with a brief 1-2 sentence summary before any headings."
    "\n- Use ### (h3) for section headings only — never # or ##."
    "\n- Use bullet points (-) for lists, never numbered lists."
    "\n- Bold key terms inline only, never use bold for section headings."
    "\n- Keep paragraphs short (2-3 sentences max)."
)

CONTEXT_WINDOW = 10  # maximum number of past messages sent as conversation history


@dataclass(frozen=True)
class BuiltContext:
    context: str
    included_chunk_ids: list[str]


def _format_paper_metadata(metadata: PaperMetadata | list[PaperMetadata] | None) -> str:
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
    chunks: list[ChunkDict], similarity_threshold: float = 0.9
) -> list[ChunkDict]:
    """Remove chunks with highly overlapping content.

    Uses Jaccard similarity on word sets. Keeps the first occurrence
    when duplicates are found (preserving retrieval ranking order).
    """
    if len(chunks) <= 1:
        return chunks

    unique: list[ChunkDict] = []
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
    """Builds RAG context and streams LLM replies."""

    def __init__(self, llm_service: LLMService | None = None):
        self._llm_service = llm_service or LLMService()

    def build_context(
        self, chunks: list[ChunkDict], max_tokens: int = DEFAULT_CONTEXT_MAX_TOKENS
    ) -> str:
        """Format chunks into context string respecting token budget."""
        return self.build_context_with_metadata(chunks, max_tokens=max_tokens).context

    def build_context_with_metadata(
        self, chunks: list[ChunkDict], max_tokens: int = DEFAULT_CONTEXT_MAX_TOKENS
    ) -> BuiltContext:
        """Format chunks and report which chunk IDs were included in the prompt."""
        deduped = _deduplicate_chunks(chunks)
        parts = []
        total_tokens = 0
        included_chunk_ids: list[str] = []

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
                    if c.get("chunk_id"):
                        included_chunk_ids.append(str(c["chunk_id"]))
                break

            parts.append(chunk_text)
            if c.get("chunk_id"):
                included_chunk_ids.append(str(c["chunk_id"]))
            total_tokens += chunk_tokens

        return BuiltContext(
            context="\n\n---\n\n".join(parts),
            included_chunk_ids=included_chunk_ids,
        )

    def build_messages(
        self,
        context: str,
        history: list[ChatMessageDict],
        user_message: str,
        base_prompt: str | None = None,
        paper_metadata: PaperMetadata | list[PaperMetadata] | None = None,
    ) -> tuple[str, list[ChatMessageDict]]:
        """Build system prompt and message list for LLM."""
        metadata_section = _format_paper_metadata(paper_metadata)
        parts = [base_prompt or SYSTEM_PROMPT]
        if metadata_section:
            parts.append(metadata_section)
        parts.append("## Context from the papers:\n\n" + context)
        system = "\n\n".join(parts)
        msgs: list[ChatMessageDict] = []
        for h in history[-CONTEXT_WINDOW:]:
            msgs.append({"role": h["role"], "content": h["content"]})
        msgs.append({"role": "user", "content": user_message})
        return system, msgs

    async def stream_reply(
        self,
        system_prompt: str,
        messages: list[ChatMessageDict],
        provider: str,
        api_key: str,
        model: str | None = None,
    ) -> AsyncIterator[str]:
        if provider != "openrouter":
            raise ValueError(f"Unknown provider: {provider}")
        kwargs: dict[str, Any] = {
            "system_prompt": system_prompt,
            "messages": messages,
            "api_key": api_key,
        }
        if model:
            kwargs["model"] = model
        async for token in self._llm_service.stream_openrouter(**kwargs):
            yield token
