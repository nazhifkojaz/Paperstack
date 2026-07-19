"""Chunking service: splits a PDF (as an ``ExtractedDocument``) into chunks.

Phase C, Phase 3 — markdown-aware chunker. The entry point is
:func:`chunk_document`, which walks the flat block stream produced by a
``DocumentExtractor`` (see :mod:`app.services.extractors`) and emits typed,
token-size-bounded chunks.

Atomicity over size
-------------------
Table and equation blocks are **never split**, even when they exceed the size
budget — splitting a markdown pipe-table mid-row produces garbage, and orphaning
a display equation loses context. An oversized atomic chunk is correct; the
retrieval layer (``vector_search_service`` proximity boost, ``search_all``
truncation) already tolerates variable chunk sizes.

Section boundaries
------------------
Heading blocks flush the running paragraph buffer and update the section
context (derived from each block's ``section_path``). Overlap therefore never
crosses a heading boundary — it is drawn from the just-flushed buffer, which by
construction lives within a single section.

Sizing
------
Size and overlap are measured in tokens (``tiktoken`` cl100k_base) via
``CHUNK_SIZE_TOKENS`` / ``CHUNK_OVERLAP_TOKENS``. The legacy char-based
``CHUNK_SIZE`` / ``CHUNK_OVERLAP`` settings are retained but no longer drive
sizing.

Backwards compatibility
-----------------------
:func:`chunk_text_with_pages` — the legacy ``--- PAGE N ---`` entry point used
by the ``pymupdf`` backend and the golden-corpus harness — is retained as a
thin adapter that builds an :class:`ExtractedDocument` from the marked-up text
(via :func:`_legacy_text_to_document`) and delegates to :func:`chunk_document`.
The regex heading fallback that used to live in this function is applied while
building the legacy document so headings the font heuristics missed are still
recovered (Phase C locked decision #7).

Earlier-phase behaviours preserved by the new chunker:
- Paragraph-aware, sentence-respecting overlap (now paragraph-aware in tokens).
- Reference/bibliography section skipping.
- List preservation: a run of list items may extend a chunk past the size
  budget, up to 2×, to avoid splitting a list mid-run.
- Quality filtering (:func:`_is_quality_chunk`) on paragraph chunks.
"""

import re
from dataclasses import dataclass

import tiktoken
from app.core.config import settings
from app.services.extractors.base import ExtractedDocument, RawBlock

_REFERENCE_HEADINGS = {
    "references",
    "bibliography",
    "works cited",
    "literature cited",
}

_ABBREVIATIONS = {
    "e.g",
    "i.e",
    "et al",
    "vs",
    "Fig",
    "Eq",
    "Tab",
    "Dr",
    "Prof",
    "Mr",
    "Mrs",
    "Ms",
    "Sr",
    "Jr",
    "vol",
    "no",
    "pp",
    "ch",
    "sec",
    "cf",
    "al",
    "approx",
    "est",
    "ref",
    "dept",
    "univ",
}

_HEADING_RE = re.compile(r"^\[HEADING L(\d+)\]\s+(.+)$")

_LIST_ITEM_RE = re.compile(r"^[\s]*[-•*]\s|^\d+[.)]\s")


def _is_list_item(text: str) -> bool:
    """Check if a paragraph is a list item (bulleted or numbered)."""
    return bool(_LIST_ITEM_RE.match(text.strip()))


# tiktoken encoder for token-based chunk sizing (cl100k_base matches the
# embedding model family). Encoding is ~free; the instance is module-global.
_ENCODER = tiktoken.get_encoding("cl100k_base")


def _ntokens(text: str) -> int:
    """Token count of ``text`` under the cl100k_base encoding."""
    if not text:
        return 0
    return len(_ENCODER.encode(text))


# ``[TABLE]\n<markdown>\n[/TABLE]`` — captures the inner table markdown. Used by
# the legacy text adapter to recover table content from marker-wrapped text.
_TABLE_RE = re.compile(r"\[TABLE\]\n?(.*?)\n?\[/TABLE\]", re.DOTALL)

_CAPTION_PREFIXES = ("[FIGURE CAPTION]", "[TABLE CAPTION]")


@dataclass
class _BufferPara:
    """A paragraph accumulated into the running chunk buffer."""

    text: str
    page: int
    section_title: str | None
    section_level: int | None


def _has_list_content(paragraphs: list[tuple[int, int, str]]) -> bool:
    """Check if any of the paragraphs are list items."""
    return any(_is_list_item(p[2]) for p in paragraphs)


def _is_reference_heading(text: str) -> bool:
    """Detect reference section heading."""
    lower = text.strip().lower()
    if lower in _REFERENCE_HEADINGS:
        return True
    return (
        re.match(
            r"^\d*\.?\s*(references|bibliography|works cited|literature cited)",
            text.strip(),
            re.IGNORECASE,
        )
        is not None
    )


def _is_appendix_heading(text: str) -> bool:
    """Detect an appendix / supplementary heading.

    Used to *resume* indexing after the reference list. NeurIPS/ICLR/ACL papers
    conventionally place a substantial appendix (data cards, checklists, extra
    experiments) *after* References; the chunker's ``in_references`` latch must
    not discard it, since gold evidence frequently lives there.
    """
    stripped = text.strip()
    lower = stripped.lower()
    if lower.startswith("appendix") or lower.startswith("supplementary"):
        return True
    # Lettered appendix sections: "A Appendix", "A. Details", "(B) ...", "C More..."
    return re.match(r"^\(?[A-Z]\)?\.?\s+\S", stripped) is not None


@dataclass
class Chunk:
    chunk_index: int
    page_number: int
    end_page_number: int
    content: str
    section_title: str | None = None
    section_level: int | None = None
    # 'paragraph' | 'table' | 'equation' | 'caption' | 'heading' | 'code'.
    # Atomic blocks (table/equation/code) get their own chunk; paragraphs flow.
    chunk_type: str = "paragraph"


_SECTION_KEYWORDS = {
    "abstract",
    "introduction",
    "methods",
    "methodology",
    "results",
    "discussion",
    "conclusion",
    "references",
    "bibliography",
    "acknowledgments",
    "acknowledgements",
    "appendix",
    "supplementary",
    "background",
    "related work",
    "literature review",
    "future work",
    "limitations",
    "experimental setup",
    "experiments",
    "evaluation",
    "implementation",
    "data",
    "dataset",
    "model",
    "approach",
    "framework",
    "system design",
    "architecture",
    "threat model",
    "attack taxonomy",
    "defences",
    "defenses",
    "ethical considerations",
    "broader impact",
}


def _parse_headings(full_text: str) -> list[tuple[int, str, int]]:
    """Parse headings from extracted text.

    Two-pass approach:
    1. Consume [HEADING L{level}] markers from Phase 0.3 font analysis
    2. Fall back to regex-based detection for sections missed by font analysis

    Returns list of (char_offset, heading_text, level).
    """
    headings: list[tuple[int, str, int]] = []
    seen_offsets: set[int] = set()
    seen_titles: dict[str, int] = {}  # title -> count (for dedup)

    # Pass 1: font-analysis markers (highest confidence)
    for match in re.finditer(r"\[HEADING L(\d+)\]\s+(.+)\n?", full_text):
        level = int(match.group(1))
        title = match.group(2).strip()
        headings.append((match.start(), title, level))
        seen_offsets.add(match.start())
        seen_titles[title] = seen_titles.get(title, 0) + 1

    # Pass 2: regex-based fallback for section headings
    # Pattern 1: Numbered headings — "1. Introduction", "3.2 Results", "2.1.1 Detail"
    # Must be preceded by paragraph boundary, not just a page number.
    # Exclude single-digit-only numbers (page numbers) and limit title length.
    for match in re.finditer(
        r"(\n\n|^)(\d+(\.\d+)+)\s+([A-Z][A-Za-z\s\-,'/&]+?)\s*$",
        full_text,
        re.MULTILINE,
    ):
        number = match.group(2)
        title_text = match.group(4).strip()
        if len(title_text) > 100 or len(title_text) < 2:
            continue
        level = number.count(".") + 1
        offset = match.start(2)
        if offset not in seen_offsets:
            headings.append((offset, title_text, level))
            seen_offsets.add(offset)
            seen_titles[title_text] = seen_titles.get(title_text, 0) + 1

    # Pattern 2: Known section keywords on their own line
    for match in re.finditer(
        r"(\n\n|^)("
        + "|".join(re.escape(k) for k in _SECTION_KEYWORDS)
        + r")(\n\n|\n|$)",
        full_text,
        re.MULTILINE | re.IGNORECASE,
    ):
        title_text = match.group(2).strip()
        title_text = title_text.title()
        offset = match.start(2)
        if offset not in seen_offsets:
            headings.append((offset, title_text, 1))
            seen_offsets.add(offset)
            seen_titles[title_text] = seen_titles.get(title_text, 0) + 1

    # Pattern 3: Title-case standalone lines that look like section headings.
    # Criteria: 15-80 chars, title-case, on its own line, not a sentence.
    # Must not be a running header (deduped later).
    for match in re.finditer(
        r"\n\n([A-Z][A-Za-z\s\-,'/&()]+?)\n\n",
        full_text,
    ):
        title_text = match.group(1).strip()
        # Must be reasonable length
        if len(title_text) < 15 or len(title_text) > 80:
            continue
        # Must not contain sentence-ending punctuation mid-text
        if re.search(r"[.!?]\s", title_text):
            continue
        # Must be title-case or all-caps (common for academic headings)
        words = title_text.split()
        if len(words) < 2:
            continue
        is_title_case = all(w[0].isupper() for w in words if w[0].isalpha())
        is_all_caps = all(w.isupper() for w in words if w.isalpha())
        if not (is_title_case or is_all_caps):
            continue
        offset = match.start(1)
        if offset not in seen_offsets:
            headings.append((offset, title_text, 2))
            seen_offsets.add(offset)
            seen_titles[title_text] = seen_titles.get(title_text, 0) + 1

    # Remove headings that appear too many times (likely running headers)
    # A title appearing >3 times is almost certainly a running header/footer
    max_occurrences = 3
    headings = [
        (offset, title, level)
        for offset, title, level in headings
        if seen_titles.get(title, 0) <= max_occurrences
    ]

    headings.sort(key=lambda h: h[0])
    return headings


def _find_sentence_boundary(text: str, search_start: int, search_end: int) -> int:
    """Find the best sentence boundary in [search_start, search_end).

    Returns the position AFTER the sentence end (including trailing space).
    Returns -1 if no suitable boundary found.
    """
    pattern = r"[.!?]\s+(?=[A-Z])"

    best_pos = -1
    for match in re.finditer(pattern, text[search_start:search_end]):
        pos = search_start + match.end()
        abs_start = search_start + match.start()
        before = text[max(0, abs_start - 10) : abs_start]
        is_abbreviation = any(
            before.rstrip().lower().endswith(abbr) for abbr in _ABBREVIATIONS
        )
        if not is_abbreviation:
            best_pos = pos

    return best_pos


def _find_sentence_boundary_reverse(
    text: str, search_start: int, search_end: int
) -> int:
    """Find the start of a sentence going backwards from search_end.

    Returns the position AFTER a sentence-ending punctuation, or -1 if none found.
    """
    pattern = r"[.!?]\s+(?=[A-Z])"
    segment = text[search_start:search_end]
    matches = list(re.finditer(pattern, segment))
    if matches:
        last_match = matches[-1]
        return search_start + last_match.end()
    return -1


def _is_quality_chunk(content: str) -> bool:
    """Check if a chunk has enough substance to be worth embedding."""
    stripped = content.strip()
    if not stripped:
        return False

    if len(stripped) < 50:
        return False

    has_structured_content = any(
        marker in stripped
        for marker in ("[TABLE]", "[FIGURE CAPTION]", "[TABLE CAPTION]")
    )
    if has_structured_content:
        return True

    if not re.search(r"[.!?]", stripped):
        return False

    if len(stripped.split()) < 8:
        return False

    if len(stripped) < 80 and stripped.endswith(tuple(str(i) for i in range(10))):
        return False

    return True


def _get_page_for_offset(offset: int, page_boundaries: list[tuple[int, int]]) -> int:
    """Get the page number for a given character offset."""
    page_num = page_boundaries[0][1]
    for off, pn in page_boundaries:
        if off <= offset:
            page_num = pn
        else:
            break
    return page_num


def _get_section_at_offset(
    offset: int, headings: list[tuple[int, str, int]]
) -> tuple[str | None, int | None]:
    """Get the current section title and level for a given offset.

    Returns (section_title, section_level) of the most recent heading
    before or at the given offset.
    """
    current_title = None
    current_level = None
    for heading_offset, title, level in headings:
        if heading_offset <= offset:
            current_title = title
            current_level = level
        else:
            break
    return current_title, current_level


def _is_heading_marker(text: str) -> tuple[bool, str | None, int | None]:
    """Check if text is a [HEADING L{level}] marker.

    Returns (is_heading, heading_text, level).
    """
    match = _HEADING_RE.match(text.strip())
    if match:
        return True, match.group(2).strip(), int(match.group(1))
    return False, None, None


def _iter_paragraphs(full_text: str):
    """Yield ``(start_offset, end_offset, text)`` for each non-empty paragraph.

    Paragraphs are split on double newlines. Offsets index into ``full_text``
    and are used to look up page attribution and regex-detected headings. A
    cursor-based scan (not ``str.find``) is used so duplicate paragraph text
    does not confuse offset tracking.
    """
    cursor = 0
    length = len(full_text)
    while cursor < length:
        idx = full_text.find("\n\n", cursor)
        if idx == -1:
            remaining = full_text[cursor:].strip()
            if remaining:
                yield (cursor, length, remaining)
            break
        para = full_text[cursor:idx].strip()
        if para:
            yield (cursor, idx, para)
        cursor = idx + 2


def _push_section(stack: list[tuple[int, str]], level: int, title: str) -> None:
    """Maintain the heading stack: pop deeper-or-equal levels, then push."""
    while stack and stack[-1][0] >= level:
        stack.pop()
    stack.append((level, title))


def _select_overlap(paras: list[_BufferPara], overlap_tokens: int) -> list[_BufferPara]:
    """Pick trailing paragraphs to carry into the next chunk as overlap.

    Overlap is paragraph-aware (whole paragraphs only). The trailing paragraph
    is always included so consecutive chunks share context; earlier paragraphs
    are prepended while they fit within the token budget. Overlap naturally
    stays within a section because it is drawn from a just-flushed buffer that
    lives in one section (headings flush before overlap is taken).
    """
    selected: list[_BufferPara] = []
    total = 0
    for para in reversed(paras):
        n = _ntokens(para.text)
        if selected and total + n > overlap_tokens:
            break
        total += n
        selected.insert(0, para)
    return selected


# Maximum length of a real section heading. Extractors occasionally push a
# misclassified block (an algorithm/code body or a long caption) onto a block's
# ``section_path``; such values are not headings, read as garbage in retrieval
# metadata, and -- critically -- overflow ``pdf_chunks.section_title
# varchar(500)``, which aborts indexing for the whole paper (seen on PeerQA
# papers with large pseudocode blocks). Reject implausible titles at the chunk
# boundary (uniform across every extractor) and fall back to the nearest valid
# ancestor heading. 200 chars is generous: real section titles are far shorter.
_MAX_SECTION_TITLE_CHARS = 200


def _valid_section_title(title: str | None) -> str | None:
    """Return ``title`` if it is a plausible section heading, else ``None``."""
    if not title:
        return None
    t = title.strip()
    if not t or len(t) > _MAX_SECTION_TITLE_CHARS:
        return None
    return t


def chunk_document(doc: ExtractedDocument) -> list[Chunk]:
    """Walk an ``ExtractedDocument``'s blocks and emit typed, token-bounded chunks.

    Atomicity rules (override the size budget):
      * ``table``, ``equation`` and ``code`` blocks are NEVER split — each
        becomes its own chunk even if oversized (splitting a markdown pipe-table
        mid-row, orphaning a display equation, or breaking a code listing loses
        information).
      * ``caption`` blocks attach to the nearest preceding
        table/equation/code chunk when nothing has accumulated since; otherwise
        they flush and stand alone.
      * ``heading`` blocks flush the running paragraph buffer and update the
        section context (derived from each block's ``section_path``). The
        heading itself is not emitted as a chunk.
      * ``paragraph`` blocks accumulate into a buffer until the token budget
        is exceeded, then flush at a paragraph boundary with token-bounded
        overlap drawn from the same section.

    Reference / bibliography sections are skipped once a reference heading is
    encountered (matches the legacy chunker). A run of list items may extend a
    chunk up to 2x the budget to avoid splitting a list mid-run. Paragraph
    chunks pass :func:`_is_quality_chunk`; atomic chunks bypass it.
    """
    chunk_size = settings.CHUNK_SIZE_TOKENS
    chunk_overlap = settings.CHUNK_OVERLAP_TOKENS

    chunks: list[Chunk] = []
    buffer: list[_BufferPara] = []
    chunk_start_page: int | None = None
    current_end_page: int | None = None
    in_references = False

    def _section_of(block: RawBlock) -> tuple[str | None, int | None]:
        # An extractor may push a misclassified block (algorithm/code body, long
        # caption) onto ``section_path``; such a value overflows
        # ``pdf_chunks.section_title`` and aborts indexing. Walk back to the
        # most recent *valid* (short) heading so chunk metadata always carries a
        # real section title, regardless of which extractor produced the blocks.
        path = block.section_path or []
        for i in range(len(path) - 1, -1, -1):
            title = _valid_section_title(path[i])
            if title is not None:
                return title, i + 1
        return None, None

    def _flush_buffer() -> None:
        nonlocal buffer, chunk_start_page, current_end_page
        if not buffer:
            return
        text = "\n\n".join(p.text for p in buffer).strip()
        if text and _is_quality_chunk(text):
            last = buffer[-1]
            chunks.append(
                Chunk(
                    chunk_index=0,
                    page_number=(
                        chunk_start_page if chunk_start_page is not None else last.page
                    ),
                    end_page_number=(
                        current_end_page if current_end_page is not None else last.page
                    ),
                    content=text,
                    section_title=last.section_title,
                    section_level=last.section_level,
                    chunk_type="paragraph",
                )
            )
        buffer = []
        chunk_start_page = None
        current_end_page = None

    def _append_para(para: _BufferPara) -> None:
        nonlocal chunk_start_page, current_end_page
        if chunk_start_page is None:
            chunk_start_page = para.page
        current_end_page = para.page
        buffer.append(para)

    for block in doc.blocks:
        btype = block.block_type
        sec_title, sec_level = _section_of(block)

        if btype == "heading":
            # A reference heading flushes and puts us in skip mode for the
            # reference list (back-matter that is rarely worth embedding).
            if sec_title is not None and _is_reference_heading(sec_title):
                _flush_buffer()
                in_references = True
                continue
            if in_references:
                # Resume indexing when an appendix/supplementary heading
                # appears: ML-conference papers place a large appendix *after*
                # References, and it must be indexed (gold evidence lives there).
                if sec_title is not None and _is_appendix_heading(sec_title):
                    in_references = False
                    _flush_buffer()
                    continue
                continue
            _flush_buffer()
            continue

        if in_references:
            continue

        if btype == "table" or btype == "equation" or btype == "code":
            _flush_buffer()
            content = block.content.strip()
            if content:
                chunks.append(
                    Chunk(
                        chunk_index=0,
                        page_number=block.page_number,
                        end_page_number=block.page_number,
                        content=content,
                        section_title=sec_title,
                        section_level=sec_level,
                        chunk_type=btype,
                    )
                )
            continue

        if btype == "caption":
            content = block.content.strip()
            if not content:
                continue
            # Attach to the nearest preceding table/equation/code chunk when
            # nothing has accumulated since it was emitted.
            if (
                not buffer
                and chunks
                and chunks[-1].chunk_type
                in (
                    "table",
                    "equation",
                    "code",
                )
            ):
                last = chunks[-1]
                last.content = last.content + "\n\n" + content
                last.end_page_number = max(last.end_page_number, block.page_number)
                continue
            _flush_buffer()
            chunks.append(
                Chunk(
                    chunk_index=0,
                    page_number=block.page_number,
                    end_page_number=block.page_number,
                    content=content,
                    section_title=sec_title,
                    section_level=sec_level,
                    chunk_type="caption",
                )
            )
            continue

        # paragraph: flow into the buffer (code/table/equation are atomic above).
        text = block.content.strip()
        if not text:
            continue
        para = _BufferPara(
            text=text,
            page=block.page_number,
            section_title=sec_title,
            section_level=sec_level,
        )

        if buffer:
            tentative = "\n\n".join(p.text for p in buffer) + "\n\n" + text
            if _ntokens(tentative) > chunk_size:
                # List preservation: a run of list items may extend the chunk
                # up to 2x the budget rather than splitting mid-list.
                in_list = (
                    _has_list_content([(0, 0, p.text) for p in buffer])
                    and _is_list_item(text)
                    and _ntokens(tentative) <= chunk_size * 2
                )
                if not in_list:
                    prev_paras = list(buffer)
                    _flush_buffer()
                    for op in _select_overlap(prev_paras, chunk_overlap):
                        _append_para(op)
                    _append_para(para)
                    continue

        _append_para(para)

    _flush_buffer()

    for i, chunk in enumerate(chunks):
        chunk.chunk_index = i
    return chunks


def _legacy_text_to_document(text_with_markers: str) -> ExtractedDocument:
    """Build an ``ExtractedDocument`` from legacy ``--- PAGE N ---`` marker text.

    This is the adapter that lets :func:`chunk_text_with_pages` delegate to
    :func:`chunk_document`. It reproduces the classification the legacy chunker
    performed inline, including the regex heading fallback (moved here from the
    old chunker per Phase C decision #7) so headings the font heuristics missed
    are still recovered as ``heading`` blocks.

    Recognised markers (emitted by the legacy ``extract_text_with_pages``):
      * ``[HEADING L{level}] title``        -> heading block
      * regex-detected section headings     -> heading block (3-pass fallback)
      * ``References`` / numbered ref heads -> heading block (triggers skip)
      * ``[TABLE] ... [/TABLE]``            -> table block (markers stripped)
      * ``[FIGURE CAPTION] / [TABLE CAPTION]`` -> caption block
      * everything else                     -> paragraph block
    """
    page_blocks: list[tuple[int, str]] = []
    for match in re.finditer(
        r"--- PAGE (\d+) ---\n(.*?)(?=--- PAGE \d+ ---|\Z)",
        text_with_markers,
        re.DOTALL,
    ):
        page_num = int(match.group(1))
        page_text = match.group(2).strip()
        if page_text:
            page_blocks.append((page_num, page_text))

    if not page_blocks:
        return ExtractedDocument(blocks=[], page_count=0, extraction_backend="pymupdf")

    full_text = ""
    page_boundaries: list[tuple[int, int]] = []
    for page_num, page_text in page_blocks:
        page_boundaries.append((len(full_text), page_num))
        full_text += page_text + "\n\n"
    full_text = full_text.rstrip()

    page_count = max(page_num for page_num, _ in page_blocks)
    if not full_text.strip():
        return ExtractedDocument(
            blocks=[], page_count=page_count, extraction_backend="pymupdf"
        )

    headings = _parse_headings(full_text)
    heading_at: dict[int, tuple[str, int]] = {
        offset: (title, level) for offset, title, level in headings
    }

    # Reference section start offsets: headings whose title is a reference
    # heading, plus a raw-text scan for "6. References"-style headings the
    # regex fallback does not classify as section headings.
    reference_offsets: set[int] = {
        offset for offset, title, _ in headings if _is_reference_heading(title)
    }
    for match in re.finditer(
        r"(\n\n|^)("
        + "|".join(re.escape(k) for k in _REFERENCE_HEADINGS)
        + r")(\n\n|\n|$)",
        full_text,
        re.MULTILINE | re.IGNORECASE,
    ):
        reference_offsets.add(match.start(2))

    blocks: list[RawBlock] = []
    section_stack: list[tuple[int, str]] = []

    for para_start, _para_end, para_text in _iter_paragraphs(full_text):
        page_num = _get_page_for_offset(para_start, page_boundaries)

        is_heading, heading_text, heading_level = _is_heading_marker(para_text)
        if is_heading:
            _push_section(section_stack, heading_level, heading_text)
            blocks.append(
                RawBlock(
                    block_type="heading",
                    content=heading_text,
                    page_number=page_num,
                    section_path=[t for _, t in section_stack],
                )
            )
            continue

        if para_start in heading_at:
            title, level = heading_at[para_start]
            _push_section(section_stack, level, title)
            blocks.append(
                RawBlock(
                    block_type="heading",
                    content=title,
                    page_number=page_num,
                    section_path=[t for _, t in section_stack],
                )
            )
            continue

        if para_start in reference_offsets or _is_reference_heading(para_text):
            title = para_text.strip()
            _push_section(section_stack, 1, title)
            blocks.append(
                RawBlock(
                    block_type="heading",
                    content=title,
                    page_number=page_num,
                    section_path=[t for _, t in section_stack],
                )
            )
            continue

        if para_text.startswith("[TABLE]"):
            inner = _TABLE_RE.search(para_text)
            content = inner.group(1).strip() if inner else para_text
            blocks.append(
                RawBlock(
                    block_type="table",
                    content=content,
                    page_number=page_num,
                    section_path=[t for _, t in section_stack],
                )
            )
            continue

        if para_text.startswith(_CAPTION_PREFIXES):
            blocks.append(
                RawBlock(
                    block_type="caption",
                    content=para_text,
                    page_number=page_num,
                    section_path=[t for _, t in section_stack],
                )
            )
            continue

        blocks.append(
            RawBlock(
                block_type="paragraph",
                content=para_text,
                page_number=page_num,
                section_path=[t for _, t in section_stack],
            )
        )

    return ExtractedDocument(
        title=None,
        blocks=blocks,
        page_count=page_count,
        extraction_backend="pymupdf",
    )


def chunk_text_with_pages(text_with_markers: str) -> list[Chunk]:
    """Legacy entry point: chunk ``--- PAGE N ---`` marker text.

    Retained for the ``pymupdf`` extraction backend and the golden-corpus
    harness. Builds a minimal :class:`ExtractedDocument` from the marker text
    (via :func:`_legacy_text_to_document`) and delegates to
    :func:`chunk_document`.
    """
    doc = _legacy_text_to_document(text_with_markers)
    return chunk_document(doc)
