"""Extraction backend package.

Select a backend with :func:`get_extractor` using the ``EXTRACTION_BACKEND``
setting (``"pymupdf"`` legacy, ``"pymupdf4llm"`` new). Backends are cheap to
construct; all work happens in :meth:`DocumentExtractor.extract`.
"""

from __future__ import annotations

from app.services.extractors.base import (
    BlockType,
    DocumentExtractor,
    ExtractedDocument,
    RawBlock,
)
from app.services.extractors.pymupdf4llm_extractor import PyMuPdf4LlmExtractor
from app.services.extractors.pymupdf_extractor import PyMuPdfExtractor

__all__ = [
    "BlockType",
    "DocumentExtractor",
    "ExtractedDocument",
    "RawBlock",
    "PyMuPdfExtractor",
    "PyMuPdf4LlmExtractor",
    "get_extractor",
]


def get_extractor(backend: str) -> DocumentExtractor:
    """Return the extractor for a backend name.

    Raises:
        ValueError: if ``backend`` is not a known backend name.
    """
    if backend == "pymupdf":
        return PyMuPdfExtractor()
    if backend == "pymupdf4llm":
        return PyMuPdf4LlmExtractor()
    raise ValueError(
        f"Unknown extraction backend: {backend!r}. "
        f"Expected one of: 'pymupdf', 'pymupdf4llm'."
    )
