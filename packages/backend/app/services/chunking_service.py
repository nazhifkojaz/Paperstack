"""Chunking service: splits page-marked PDF text into overlapping chunks."""

import re
from dataclasses import dataclass

from app.core.config import settings

CHUNK_SIZE = (
    800  # characters (~200 words, ~160 tokens) — deprecated, use settings.CHUNK_SIZE
)
CHUNK_OVERLAP = 150  # characters — deprecated, use settings.CHUNK_OVERLAP

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


@dataclass
class Chunk:
    chunk_index: int
    page_number: int
    content: str


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


def chunk_text_with_pages(text_with_markers: str) -> list[Chunk]:
    """Split page-marked text into overlapping chunks with page attribution.

    Input: output of extract_text_with_pages() — text with "--- PAGE N ---" markers.
    Output: list of Chunk, each attributed to the page it starts on.

    Algorithm:
    1. Parse page blocks from markers
    2. Concatenate all text, recording page-start byte offsets
    3. Slide a window of CHUNK_SIZE, breaking at sentence boundaries
    4. Overlap each chunk with the previous by CHUNK_OVERLAP characters
    """
    # Parse page blocks
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

    # Concatenate all text, tracking page-start character offsets
    full_text = ""
    page_boundaries: list[tuple[int, int]] = []  # [(char_offset, page_num)]
    for page_num, page_text in page_blocks:
        page_boundaries.append((len(full_text), page_num))
        full_text += page_text + "\n\n"

    full_text = full_text.rstrip()
    if not full_text:
        return []

    # Sliding window chunking
    chunks: list[Chunk] = []
    start = 0
    chunk_idx = 0

    chunk_size = settings.CHUNK_SIZE
    chunk_overlap = settings.CHUNK_OVERLAP

    while start < len(full_text):
        end = min(start + chunk_size, len(full_text))

        # Try to break at a sentence boundary in the latter half of the window
        if end < len(full_text):
            boundary = _find_sentence_boundary(full_text, start + chunk_size // 2, end)
            if boundary != -1:
                end = boundary

        chunk_content = full_text[start:end].strip()
        if chunk_content:
            # Attribute chunk to the page its start position falls on
            page_num = page_boundaries[0][1]
            for offset, pn in page_boundaries:
                if offset <= start:
                    page_num = pn
                else:
                    break

            chunks.append(
                Chunk(
                    chunk_index=chunk_idx, page_number=page_num, content=chunk_content
                )
            )
            chunk_idx += 1

        next_start = end - chunk_overlap
        # Guard: if overlap would not advance us, force forward to avoid infinite loop
        if next_start <= start:
            next_start = start + 1
        start = next_start

        # Stop if only overlap-sized text remains (it was already included)
        if start >= len(full_text) - chunk_overlap and start > 0:
            break

    # Filter low-quality chunks and re-index
    chunks = [c for c in chunks if _is_quality_chunk(c.content)]
    for i, chunk in enumerate(chunks):
        chunk.chunk_index = i

    return chunks
