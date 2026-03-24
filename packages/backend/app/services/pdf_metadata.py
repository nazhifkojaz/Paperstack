import io
from pypdf import PdfReader
from typing import Optional

def extract_page_count(file_bytes: bytes) -> Optional[int]:
    """Extracts the number of pages from a PDF byte stream."""
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        return len(reader.pages)
    except Exception as e:
        print(f"Error extracting page count: {e}")
        return None

def get_pdf_file_size(file_bytes: bytes) -> int:
    """Returns the size of the PDF byte stream in bytes."""
    return len(file_bytes)
