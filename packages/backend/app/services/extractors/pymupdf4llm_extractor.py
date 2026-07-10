"""``pymupdf4llm`` extraction backend (Phase C default-to-be).

Turns a PDF into an :class:`ExtractedDocument` by:

1. Calling ``pymupdf4llm.to_markdown(pdf, page_chunks=True)`` — returns one
   Markdown blob per page (page number = list index + 1; there is no ``page``
   key on the dicts, the ordering *is* the page attribution).
2. Parsing each page's Markdown with ``markdown-it-py`` (tables enabled) into
   a token stream.
3. Walking the tokens and using each block token's ``.map`` (source line
   range) to recover the original Markdown span for that block.
4. Classifying each span: ``heading`` (``#``), ``table`` (pipe-table — kept
   atomic), ``caption`` (``Figure N:`` / ``Table N:``), ``code`` (fence),
   otherwise ``paragraph``.

A section stack is maintained **across pages** so a heading on page 2 still
applies to content on page 3. Bare page-number lines (e.g. a lone ``"9"``)
are dropped as extraction noise.

What this backend does NOT do (validated against the golden corpus):
- It emits **no** ``equation`` blocks. pymupdf4llm renders math as styled text
  (italics/superscripts), not LaTeX. See ``base.py`` module docstring.
"""

from __future__ import annotations

import io
import logging
import re
from collections.abc import Callable

import pymupdf
import pymupdf4llm
from markdown_it import MarkdownIt
from markdown_it.token import Token

from app.services.extractors.base import (
    BlockType,
    ExtractedDocument,
    RawBlock,
)

logger = logging.getLogger(__name__)

# Figure/Table caption detection. Matches "Figure 1:", "Fig. 2)", "Table 3 -".
_CAPTION_RE = re.compile(r"^(Figure|Fig\.?|Table|Tab\.?)\s*\d+[.:)\-\s]", re.IGNORECASE)

# Bare page-number / folio lines dropped as noise.
_PAGE_NOISE_RE = re.compile(r"^\d{1,4}$")


def _clean_inline(text: str) -> str:
    """Strip markdown emphasis and ``<br>`` so headings/captions match cleanly.

    Used only where we need comparable plain text (heading titles, caption
    detection). Paragraph and table content is stored verbatim.
    """
    s = text
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"__([^_]+)__", r"\1", s)
    s = re.sub(r"\*([^*]+)\*", r"\1", s)
    s = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = s.replace("<br>", " ")
    return re.sub(r"\s+", " ", s).strip()


def _span(lines: list[str], token_map: list[int] | None) -> str:
    """Recover the source-Markdown span for a block token from its ``.map``."""
    if not token_map:
        return ""
    start, end = token_map
    return "\n".join(lines[start:end]).strip()


class PyMuPdf4LlmExtractor:
    """Extraction backend backed by ``pymupdf4llm.to_markdown``.

    The parser is constructed once per instance (the table rule is enabled).
    The instance holds no per-document state, so it is safe to reuse.
    """

    def __init__(self) -> None:
        self._parser: MarkdownIt = MarkdownIt().enable("table")

    def extract(self, pdf_bytes: bytes) -> ExtractedDocument:
        doc = pymupdf.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
        try:
            pages = pymupdf4llm.to_markdown(doc, page_chunks=True, show_progress=False)
        finally:
            doc.close()

        title = _extract_title(pages)
        page_count = len(pages)

        blocks: list[RawBlock] = []
        # Section stack persists across pages: [(level, title), ...].
        section_stack: list[tuple[int, str]] = []

        for page_index, page in enumerate(pages):
            page_number = page_index + 1
            markdown_text = (page.get("text") if isinstance(page, dict) else "") or ""
            if not markdown_text.strip():
                continue
            self._parse_page(
                markdown_text,
                page_number=page_number,
                section_stack=section_stack,
                out=blocks,
            )

        return ExtractedDocument(
            title=title,
            blocks=blocks,
            page_count=page_count,
            extraction_backend="pymupdf4llm",
        )

    def _parse_page(
        self,
        markdown_text: str,
        *,
        page_number: int,
        section_stack: list[tuple[int, str]],
        out: list[RawBlock],
    ) -> None:
        lines = markdown_text.splitlines()
        tokens = self._parser.parse(markdown_text)

        i = 0
        while i < len(tokens):
            token = tokens[i]

            if token.type == "heading_open":
                i = self._handle_heading(
                    tokens,
                    i,
                    lines=lines,
                    page_number=page_number,
                    section_stack=section_stack,
                    out=out,
                )
                continue

            if token.type == "table_open":
                content = _span(lines, token.map)
                if content:
                    out.append(
                        RawBlock(
                            block_type="table",
                            content=content,
                            page_number=page_number,
                            section_path=_current_path(section_stack),
                        )
                    )
                i = self._index_after_close(tokens, i, "table_close")
                continue

            if token.type == "paragraph_open":
                i = self._handle_paragraph(
                    tokens,
                    i,
                    lines=lines,
                    page_number=page_number,
                    section_stack=section_stack,
                    out=out,
                )
                continue

            if token.type == "fence":
                if token.content.strip():
                    out.append(
                        RawBlock(
                            block_type="code",
                            content=token.content,
                            page_number=page_number,
                            section_path=_current_path(section_stack),
                        )
                    )
                i += 1
                continue

            i += 1

    def _handle_heading(
        self,
        tokens: list[Token],
        i: int,
        *,
        lines: list[str],
        page_number: int,
        section_stack: list[tuple[int, str]],
        out: list[RawBlock],
    ) -> int:
        open_tok = tokens[i]
        level = int(open_tok.tag[1:]) if open_tok.tag.startswith("h") else 1

        # The inline token between heading_open and heading_close carries the
        # raw (markup-laden) heading text.
        title = ""
        if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
            title = _clean_inline(tokens[i + 1].content)

        # Maintain the section stack: pop any headings at this level or deeper,
        # then push this one.
        while section_stack and section_stack[-1][0] >= level:
            section_stack.pop()
        section_stack.append((level, title or "(untitled)"))

        content = _span(lines, open_tok.map)
        if content:
            out.append(
                RawBlock(
                    block_type="heading",
                    content=content,
                    page_number=page_number,
                    section_path=_current_path(section_stack),
                )
            )
        # Skip heading_open + inline + heading_close.
        return i + 3

    def _handle_paragraph(
        self,
        tokens: list[Token],
        i: int,
        *,
        lines: list[str],
        page_number: int,
        section_stack: list[tuple[int, str]],
        out: list[RawBlock],
    ) -> int:
        open_tok = tokens[i]
        raw_span = _span(lines, open_tok.map)
        plain = _clean_inline(raw_span)

        # Drop bare page-number folios.
        if _PAGE_NOISE_RE.match(plain):
            return i + 3

        block_type: BlockType = "paragraph"
        content = raw_span
        if _CAPTION_RE.match(plain):
            block_type = "caption"
            content = plain

        if content:
            out.append(
                RawBlock(
                    block_type=block_type,
                    content=content,
                    page_number=page_number,
                    section_path=_current_path(section_stack),
                )
            )
        return i + 3

    @staticmethod
    def _index_after_close(tokens: list[Token], start: int, close_type: str) -> int:
        """Return the index just past the next ``close_type`` token."""
        j = start + 1
        while j < len(tokens):
            if tokens[j].type == close_type:
                return j + 1
            j += 1
        return j


def _current_path(section_stack: list[tuple[int, str]]) -> list[str]:
    return [title for _, title in section_stack]


def _extract_title(pages: list) -> str | None:
    """Pull the document title from the first page's ``metadata.title``."""
    if not pages:
        return None
    first = pages[0]
    if isinstance(first, dict):
        meta = first.get("metadata") or {}
        title = (meta.get("title") or "").strip()
        return title or None
    return None


# Sentinel kept for symmetry with a potential future extractor registry; the
# factory in __init__ selects backends by name.
_EXTRACTOR_FACTORY: dict[str, Callable[[], "PyMuPdf4LlmExtractor"]] = {
    "pymupdf4llm": PyMuPdf4LlmExtractor,
}
