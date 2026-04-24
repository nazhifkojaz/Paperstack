import io
import logging
from pypdf import PdfReader
from typing import Optional

logger = logging.getLogger(__name__)


def extract_page_count(file_bytes: bytes) -> Optional[int]:
    """Extracts the number of pages from a PDF byte stream."""
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        page_count = len(reader.pages)
        logger.debug("Extracted page count: %d pages", page_count)
        return page_count
    except Exception as exc:
        logger.warning("Failed to extract page count from PDF: %s", exc)
        return None

def extract_title_from_bytes(file_bytes: bytes) -> Optional[str]:
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        if reader.metadata:
            return reader.metadata.get("/Title")
    except Exception:
        pass
    return None

def get_pdf_file_size(file_bytes: bytes) -> int:
    """Returns the size of the PDF byte stream in bytes."""
    return len(file_bytes)
