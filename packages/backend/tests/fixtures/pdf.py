"""PDF-related test fixtures and helpers."""
from datetime import datetime, timezone
import uuid


def mock_pdf_data(
    id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    title: str = "Test PDF",
    filename: str = "test.pdf",
    github_sha: str | None = "abc123def456",
    file_size: int | None = 12345,
    page_count: int | None = 10,
    doi: str | None = "10.1234/test.doi.12345",
) -> dict:
    """Generate mock PDF metadata."""
    return {
        "id": id or uuid.uuid4(),
        "user_id": user_id or uuid.uuid4(),
        "title": title,
        "filename": filename,
        "github_sha": github_sha,
        "file_size": file_size,
        "page_count": page_count,
        "doi": doi,
        "isbn": None,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def sample_pdf_bytes() -> bytes:
    """Generate a minimal valid PDF for testing.

    This is a minimal valid PDF according to PDF 1.4 specification.
    It contains one empty page.
    """
    return b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Resources <<
/Font <<
/F1 <<
/Type /Font
/Subtype /Type1
/BaseFont /Helvetica
>>
>>
>>
>>
endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer
<<
/Size 4
/Root 1 0 R
>>
startxref
210
%%EOF
"""


def multi_page_pdf_bytes(page_count: int = 3) -> bytes:
    """Generate a PDF with multiple pages for testing.

    Args:
        page_count: Number of pages to generate (max 10 for simplicity)

    Returns:
        PDF document bytes
    """
    page_count = min(page_count, 10)

    # Build pages objects
    page_objects = []
    kids_refs = []

    # Catalog (1 0 obj) and Pages (2 0 obj) are fixed
    # Page objects start from 3 0 obj
    for i in range(page_count):
        page_num = i + 3
        page_objects.append(f"""{page_num} 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Resources <<
/Font <<
/F1 {page_num} 0 R
>>
>>
>>
endobj
""")
        kids_refs.append(f"{page_num} 0 R")

    kids_str = " ".join(kids_refs)

    pdf_body = f"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [{kids_str}]
/Count {page_count}
>>
endobj
{''.join(page_objects)}
xref
0 {page_count + 3}
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
trailer
<<
/Size {page_count + 3}
/Root 1 0 R
>>
startxref
"""

    pdf_content = pdf_body + f"{len(pdf_body.encode())}\n%%EOF\n"

    return pdf_content.encode()


def pdf_with_doi_bytes(doi: str = "10.1234/test.doi.12345") -> bytes:
    """Generate a PDF with DOI metadata for testing citation extraction.

    This PDF includes a DOI in the content that can be extracted.
    """
    # Create a PDF with DOI visible in text layer
    return f"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Contents 4 0 R
/Resources <<
/Font <<
/F1 <<
/Type /Font
/Subtype /Type1
/BaseFont /Helvetica
>>
>>
>>
endobj
4 0 obj
<<
/Length {len(doi) + 50}
>>
stream
BT
/F1 12 Tf
50 700 Td
(DOI: {doi}) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000270 00000 n
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
400
%%EOF
""".encode()
