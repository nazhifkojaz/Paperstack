"""Chunking service: splits page-marked PDF text into overlapping chunks.

Phase 2 improvements:
- Paragraph-aware chunking (2.1)
- Section/heading boundary detection (2.2)
- Heading context preservation (2.3)
- Context-aware overlap (2.4)

Phase 3 improvements:
- Reference section handling (3.2)

Phase 4 improvements:
- List structure preservation (4.4)
"""

import re
from dataclasses import dataclass

from app.core.config import settings

CHUNK_SIZE = (
    800  # characters (~200 words, ~160 tokens) — deprecated, use settings.CHUNK_SIZE
)
CHUNK_OVERLAP = 150  # characters — deprecated, use settings.CHUNK_OVERLAP

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


@dataclass
class Chunk:
    chunk_index: int
    page_number: int
    end_page_number: int
    content: str
    section_title: str | None = None
    section_level: int | None = None


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


def _compute_overlap_start(full_text: str, chunk_end: int, overlap_chars: int) -> int:
    """Find overlap start that begins at a sentence boundary.

    Searches for a sentence boundary near the desired overlap position.
    Falls back to the raw position if no boundary is found.
    """
    raw_start = chunk_end - overlap_chars
    if raw_start <= 0:
        return max(raw_start, 0)

    search_start = max(0, raw_start - 50)
    search_end = min(len(full_text), raw_start + 50)
    boundary = _find_sentence_boundary_reverse(full_text, search_start, search_end)
    if boundary != -1 and boundary >= raw_start - 50:
        return boundary

    return max(raw_start, 0)


def _is_heading_marker(text: str) -> tuple[bool, str | None, int | None]:
    """Check if text is a [HEADING L{level}] marker.

    Returns (is_heading, heading_text, level).
    """
    match = _HEADING_RE.match(text.strip())
    if match:
        return True, match.group(2).strip(), int(match.group(1))
    return False, None, None


def chunk_text_with_pages(text_with_markers: str) -> list[Chunk]:
    """Split page-marked text into overlapping chunks with page attribution.

    Input: output of extract_text_with_pages() — text with "--- PAGE N ---" markers
           and optional "[HEADING L{level}]" markers from Phase 0.3.

    Output: list of Chunk, each attributed to the page it starts on,
            with section_title and section_level metadata.

    Algorithm (Phase 2):
    1. Parse page blocks from markers
    2. Concatenate all text, recording page-start byte offsets
    3. Parse heading markers for section context tracking
    4. Split into paragraphs (double newlines)
    5. Accumulate paragraphs into chunks, respecting chunk size
    6. Use headings as hard boundaries — never split between heading and content
    7. Overlap at sentence boundaries when possible
    """
    page_blocks: list[tuple[int, str]] = []
    for match in re.finditer(
        r"--- PAGE (\d+) ---\n(.*?)(?=--- PAGE \d+ ---|$)",
        text_with_markers,
        re.DOTALL,
    ):
        page_num = int(match.group(1))
        page_text = match.group(2).strip()
        if page_text:
            page_blocks.append((page_num, page_text))

    if not page_blocks:
        return []

    full_text = ""
    page_boundaries: list[tuple[int, int]] = []
    for page_num, page_text in page_blocks:
        page_boundaries.append((len(full_text), page_num))
        full_text += page_text + "\n\n"

    full_text = full_text.rstrip()
    if not full_text:
        return []

    headings = _parse_headings(full_text)

    # Split text into paragraphs at double-newline boundaries.
    # We use a cursor-based approach to correctly track offsets
    # (str.find would always return the first occurrence of duplicate text).
    paragraphs: list[tuple[int, int, str]] = []
    cursor = 0
    while cursor < len(full_text):
        idx = full_text.find("\n\n", cursor)
        if idx == -1:
            remaining = full_text[cursor:].strip()
            if remaining:
                paragraphs.append((cursor, len(full_text), remaining))
            break
        para = full_text[cursor:idx].strip()
        if para:
            paragraphs.append((cursor, idx, para))
        cursor = idx + 2

    if not paragraphs:
        return []

    chunk_size = settings.CHUNK_SIZE
    chunk_overlap = settings.CHUNK_OVERLAP

    # Track paragraph list for overlap computation

    # Detect reference section start to skip bibliography content
    in_references = False
    reference_heading_offsets = {
        offset for offset, title, level in headings if _is_reference_heading(title)
    }
    # Also check raw text for reference headings not caught by font analysis
    for match in re.finditer(
        r"(\n\n|^)("
        + "|".join(re.escape(k) for k in _REFERENCE_HEADINGS)
        + r")(\n\n|\n|$)",
        full_text,
        re.MULTILINE | re.IGNORECASE,
    ):
        reference_heading_offsets.add(match.start(2))

    chunks: list[Chunk] = []
    current_text = ""
    chunk_start_page = _get_page_for_offset(paragraphs[0][0], page_boundaries)
    current_page = chunk_start_page
    current_section_title: str | None = None
    current_section_level: int | None = None
    # Track which paragraphs are in the current chunk for overlap
    current_chunk_paras: list[tuple[int, int, str]] = []
    chunk_idx = 0

    for para_start, para_end, para_text in paragraphs:
        para_page = _get_page_for_offset(para_start, page_boundaries)
        section_title, section_level = _get_section_at_offset(para_start, headings)

        is_heading, heading_text, heading_level = _is_heading_marker(para_text)
        if is_heading:
            current_section_title = heading_text
            current_section_level = heading_level
            continue

        # Check if this paragraph is a reference section heading
        if para_start in reference_heading_offsets or _is_reference_heading(para_text):
            in_references = True
            continue

        if in_references:
            continue

        separator = "\n\n" if current_text else ""
        combined_len = len(current_text) + len(separator) + len(para_text)

        if current_text and combined_len > chunk_size:
            # List preservation: allow list to extend past chunk_size
            # to avoid splitting mid-list, up to 2x chunk_size.
            in_list = (
                _has_list_content(current_chunk_paras)
                and _is_list_item(para_text)
                and combined_len <= chunk_size * 2
            )

            if not in_list:
                stripped = current_text.strip()
                if stripped and _is_quality_chunk(stripped):
                    chunks.append(
                        Chunk(
                            chunk_index=chunk_idx,
                            page_number=chunk_start_page,
                            end_page_number=current_page,
                            content=stripped,
                            section_title=current_section_title,
                            section_level=current_section_level,
                        )
                    )
                    chunk_idx += 1

                # Paragraph-aware overlap: take the last N paragraphs that fit
                # within the overlap budget, instead of raw character slicing.
                overlap_budget = chunk_overlap
                overlap_parts = []
                for p_start, p_end, p_text in reversed(current_chunk_paras):
                    if len(p_text) + (len(overlap_parts) * 2) > overlap_budget:
                        break
                    overlap_parts.insert(0, p_text)
                if overlap_parts:
                    current_text = "\n\n".join(overlap_parts) + "\n\n" + para_text
                    chunk_start_page = _get_page_for_offset(
                        current_chunk_paras[0][0], page_boundaries
                    )
                else:
                    # Fallback: if no single paragraph fits, take the last few chars
                    # of the last paragraph at a sentence boundary
                    last_para = current_chunk_paras[-1][2] if current_chunk_paras else ""
                    if len(last_para) > chunk_overlap:
                        overlap_start = _compute_overlap_start(
                            last_para, len(last_para), chunk_overlap
                        )
                        current_text = last_para[overlap_start:] + "\n\n" + para_text
                        chunk_start_page = _get_page_for_offset(
                            current_chunk_paras[-1][0], page_boundaries
                        )
                    else:
                        current_text = last_para + "\n\n" + para_text
                        chunk_start_page = _get_page_for_offset(
                            current_chunk_paras[-1][0], page_boundaries
                        )

                current_page = para_page
                current_chunk_paras = [(para_start, para_end, para_text)]
                if section_title:
                    current_section_title = section_title
                    current_section_level = section_level
            else:
                # Extend: add list item to current chunk despite exceeding size
                current_text = current_text + separator + para_text
                current_chunk_paras.append((para_start, para_end, para_text))
                current_page = para_page
                if section_title:
                    current_section_title = section_title
                    current_section_level = section_level
        else:
            current_text = current_text + separator + para_text
            current_chunk_paras.append((para_start, para_end, para_text))
            current_page = para_page
            if section_title:
                current_section_title = section_title
                current_section_level = section_level

    stripped = current_text.strip()
    if stripped and _is_quality_chunk(stripped):
        chunks.append(
            Chunk(
                chunk_index=chunk_idx,
                page_number=chunk_start_page,
                end_page_number=current_page,
                content=stripped,
                section_title=current_section_title,
                section_level=current_section_level,
            )
        )

    for i, chunk in enumerate(chunks):
        chunk.chunk_index = i

    return chunks
