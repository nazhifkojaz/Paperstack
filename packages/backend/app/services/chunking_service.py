"""Chunking service: splits page-marked PDF text into overlapping chunks."""
import re
from dataclasses import dataclass

CHUNK_SIZE = 800    # characters (~200 words, ~160 tokens)
CHUNK_OVERLAP = 150  # characters


@dataclass
class Chunk:
    chunk_index: int
    page_number: int
    content: str


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

    while start < len(full_text):
        end = min(start + CHUNK_SIZE, len(full_text))

        # Try to break at a sentence boundary (". ") in the latter half of the window
        if end < len(full_text):
            last_period = full_text.rfind(". ", start + CHUNK_SIZE // 2, end)
            if last_period != -1:
                end = last_period + 2  # include the period and space

        chunk_content = full_text[start:end].strip()
        if chunk_content:
            # Attribute chunk to the page its start position falls on
            page_num = page_boundaries[0][1]
            for offset, pn in page_boundaries:
                if offset <= start:
                    page_num = pn
                else:
                    break

            chunks.append(Chunk(chunk_index=chunk_idx, page_number=page_num, content=chunk_content))
            chunk_idx += 1

        next_start = end - CHUNK_OVERLAP
        # Guard: if overlap would not advance us, force forward to avoid infinite loop
        if next_start <= start:
            next_start = start + 1
        start = next_start

        # Stop if only overlap-sized text remains (it was already included)
        if start >= len(full_text) - CHUNK_OVERLAP and start > 0:
            break

    return chunks
