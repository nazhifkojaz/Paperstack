"""Legacy ``pymupdf`` extraction backend.

Wraps the existing :func:`app.services.text_extractor.extract_text_with_pages`
pipeline so it speaks the same :class:`ExtractedDocument` contract as the new
``pymupdf4llm`` backend. Extraction itself is **unchanged** — this module only
re-parses the legacy ``--- PAGE N ---`` / ``[HEADING L{n}]`` / ``[TABLE]`` text
format into typed blocks.

Purpose:
- Give the chunker (Phase 3) a single interface regardless of backend.
- Keep the ``pymupdf`` backend as a working fallback after the default flips
  to ``pymupdf4llm``.
- Let the golden-corpus harness exercise the legacy path through the same
  ``ExtractedDocument`` shape.

This extractor emits the same heading/table/caption signals the current
chunker already recognises (``[HEADING L{n}]``, ``[TABLE]...[/TABLE]``,
``[FIGURE CAPTION]``, ``[TABLE CAPTION]``). Reference-section exclusion stays
a *chunker* concern (Phase 3 reproduces it), so this extractor emits every
block faithfully.
"""

from __future__ import annotations

import io
import re

from app.services.extractors.base import ExtractedDocument, RawBlock
from app.services.text_extractor import extract_text_with_pages

# ``[HEADING L{n}] title`` — same shape text_extractor emits.
_HEADING_RE = re.compile(r"^\[HEADING L(\d+)\]\s+(.+)$", re.MULTILINE)

# ``[TABLE]\n<markdown>\n[/TABLE]`` — captures the inner table markdown.
_TABLE_RE = re.compile(r"\[TABLE\]\n?(.*?)\n?\[/TABLE\]", re.DOTALL)

# Page marker split: yields (page_number, page_text) preserving order.
_PAGE_RE = re.compile(r"--- PAGE (\d+) ---\n(.*?)(?=--- PAGE \d+ ---|\Z)", re.DOTALL)

_CAPTION_PREFIXES = ("[FIGURE CAPTION]", "[TABLE CAPTION]")


class PyMuPdfExtractor:
    """Legacy backend: reuse current extraction, repackage as blocks."""

    def extract(self, pdf_bytes: bytes) -> ExtractedDocument:
        file_obj = io.BytesIO(pdf_bytes)
        text_with_pages, total_pages, _note = extract_text_with_pages(file_obj)

        blocks: list[RawBlock] = []
        # Section stack persists across pages: [(level, title), ...].
        section_stack: list[tuple[int, str]] = []

        for page_num, page_text in _iter_pages(text_with_pages):
            for segment in page_text.split("\n\n"):
                seg = segment.strip()
                if not seg:
                    continue
                self._classify(
                    seg, page_num=page_num, section_stack=section_stack, out=blocks
                )

        return ExtractedDocument(
            title=None,  # legacy extractor has no reliable title source
            blocks=blocks,
            page_count=total_pages,
            extraction_backend="pymupdf",
        )

    @staticmethod
    def _classify(
        segment: str,
        *,
        page_num: int,
        section_stack: list[tuple[int, str]],
        out: list[RawBlock],
    ) -> None:
        heading_match = _HEADING_RE.match(segment)
        if heading_match:
            level = int(heading_match.group(1))
            title = heading_match.group(2).strip() or "(untitled)"
            _push_section(section_stack, level, title)
            out.append(
                RawBlock(
                    block_type="heading",
                    content=segment,
                    page_number=page_num,
                    section_path=_current_path(section_stack),
                )
            )
            return

        if segment.startswith("[TABLE]"):
            inner = _TABLE_RE.search(segment)
            content = inner.group(1).strip() if inner else segment
            out.append(
                RawBlock(
                    block_type="table",
                    content=content,
                    page_number=page_num,
                    section_path=_current_path(section_stack),
                )
            )
            return

        if segment.startswith(_CAPTION_PREFIXES):
            out.append(
                RawBlock(
                    block_type="caption",
                    content=segment,
                    page_number=page_num,
                    section_path=_current_path(section_stack),
                )
            )
            return

        out.append(
            RawBlock(
                block_type="paragraph",
                content=segment,
                page_number=page_num,
                section_path=_current_path(section_stack),
            )
        )


def _iter_pages(text: str):
    for match in _PAGE_RE.finditer(text):
        yield int(match.group(1)), match.group(2)


def _push_section(stack: list[tuple[int, str]], level: int, title: str) -> None:
    """Maintain the heading stack: pop deeper-or-equal levels, then push."""
    while stack and stack[-1][0] >= level:
        stack.pop()
    stack.append((level, title))


def _current_path(stack: list[tuple[int, str]]) -> list[str]:
    return [title for _, title in stack]
