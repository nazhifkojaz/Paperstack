"""Contextual retrieval: prepends paper/section context to chunk embedding text.

Implements the technique described in Anthropic's "Contextual Retrieval" post
(https://www.anthropic.com/news/contextual-retrieval). Each chunk's text is
prefixed with the paper title and current section before embedding. The
prefix anchors the chunk in its source context, substantially reducing
retrieval-failure rate on generic queries.

The raw chunk content is preserved in the `content` column (used for display
and as the source of the `search_vector` TSVECTOR). Only the embedding vector
is computed from the contextualized text.
"""

from __future__ import annotations

from typing import Protocol

_UNDEFINED_SECTION = "(untitled)"

_PREFIX_TEMPLATE = "Paper: {title}\nSection: {section}\n\n"


class _ChunkLike(Protocol):
    """Structural type for objects with the fields contextualization needs."""

    content: str
    section_title: str | None


def build_embedding_text(
    content: str,
    pdf_title: str,
    section_title: str | None,
) -> str:
    """Build the text to embed for a chunk.

    Prepends a two-line context header identifying the source paper and the
    section the chunk belongs to, followed by the raw chunk content.

    Args:
        content: Raw chunk content (what users see and what keyword search
            indexes).
        pdf_title: Title of the parent PDF. Used verbatim.
        section_title: Section heading in effect at the chunk's position, or
            None if no section was detected.

    Returns:
        The contextualized string suitable for embedding.
    """
    stripped_section = (section_title or "").strip()
    section = stripped_section or _UNDEFINED_SECTION
    header = _PREFIX_TEMPLATE.format(title=pdf_title, section=section)
    return f"{header}{content}"


def build_embed_inputs(
    chunks: list[_ChunkLike],
    pdf_title: str,
    contextualize: bool,
) -> list[str]:
    """Build the text inputs to embed for a list of chunks.

    When ``contextualize`` is True, each chunk is prefixed with paper/section
    context via :func:`build_embedding_text`. When False, raw chunk content is
    used (matching pre-contextual-retrieval behavior).

    Null bytes are stripped from every input. PyMuPDF occasionally emits them;
    stripping here keeps the embedded text, the persisted ``content`` column,
    and the persisted ``content_for_embedding`` column mutually consistent.

    Args:
        chunks: Chunk-like objects exposing ``content`` and ``section_title``.
        pdf_title: Title of the parent PDF, used in the contextual prefix.
        contextualize: Whether to apply the contextual prefix.

    Returns:
        One embedding input string per chunk, in input order.
    """
    embed_inputs: list[str] = []
    for chunk in chunks:
        # Defensive cleanup: strip null bytes that PyMuPDF occasionally emits.
        # The same stripped text is persisted to the `content` column by the
        # indexing service, so content and content_for_embedding stay
        # consistent with what was actually sent to the embedding API.
        text = chunk.content.replace("\x00", "")
        if contextualize:
            text = build_embedding_text(text, pdf_title, chunk.section_title)
        embed_inputs.append(text)
    return embed_inputs
