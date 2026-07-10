"""Pluggable PDF extraction backends.

A ``DocumentExtractor`` turns raw PDF bytes into a flat, ordered sequence of
typed blocks (``ExtractedDocument``) that the chunker walks. This indirection
is the seam introduced by Phase C so that extraction backends can be swapped
(``pymupdf`` legacy vs ``pymupdf4llm`` Markdown) without touching the chunker
or retrieval layer.

Block model
-----------
The document is modelled as a **flat list of blocks**, not a nested section
tree. Each block carries its own ``page_number`` and ``section_path`` (the
heading stack in effect at that point). The chunker walks blocks in order and
derives section boundaries from ``section_path``. This matches how both
backends produce data (a linear stream per page) and avoids forcing page
boundaries across an artificial section tree.

Note on equations
-----------------
The original plan (``CHUNKING_IMPROVEMENT_PLAN.md`` §6, C.3) assumed pymupdf4llm
emits display math as ``$...$`` / ``$$...$$``. Validation on the golden corpus
showed this is **not** the case: pymupdf4llm renders math as styled text
(italics/superscripts), with zero ``$`` or LaTeX backslashes in the output.
``equation`` is therefore kept in ``BlockType`` for forward-compatibility (a
future nougat/marker backend could emit real LaTeX), but no current backend
populates it. Tables, headings, and captions all classify cleanly.
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, Field

# Ordered loosely by how "structural" a block is. The chunker treats table and
# equation blocks as atomic (never split); paragraph/heading/caption flow.
BlockType = Literal[
    "paragraph",
    "heading",
    "table",
    "caption",
    "code",
    "equation",  # reserved: no current backend emits this (see module docstring)
]


class RawBlock(BaseModel):
    """A single typed content block extracted from one page of a PDF."""

    block_type: BlockType
    content: str
    page_number: int
    # Heading titles from the document root down to the heading in effect at
    # this block, e.g. ["3", "3.2", "Attention"]. Empty before the first
    # heading (title/abstract region). The chunker uses ``section_path[-1]``
    # as ``section_title`` and ``len(section_path)`` as ``section_level``.
    section_path: list[str] = Field(default_factory=list)


class ExtractedDocument(BaseModel):
    """The output of a ``DocumentExtractor``: an ordered, typed block stream."""

    title: str | None = None
    blocks: list[RawBlock] = Field(default_factory=list)
    page_count: int
    extraction_backend: str


class DocumentExtractor(Protocol):
    """Interface every extraction backend implements.

    Implementations must be safe to instantiate cheaply (no I/O at construction
    time); all real work happens in :meth:`extract`.
    """

    def extract(self, pdf_bytes: bytes) -> ExtractedDocument: ...
