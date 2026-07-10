"""reset index status for pymupdf4llm reindex

Phase 6 lazy reindex: flip the default extraction backend to ``pymupdf4llm``
and reset every PDF's index status so the next access through
``ensure_indexed`` rebuilds chunks with the new backend. Existing chunks are
left in place until re-index (they are replaced per-PDF by ``index_pdf``);
the schema itself is unchanged.

Revision ID: cbc91cf1ac88
Revises: c5d6e7f8a9b0
Create Date: 2026-06-17 00:55:41.010637

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "cbc91cf1ac88"
down_revision: Union[str, Sequence[str], None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Reset all PDF index statuses so they are re-indexed lazily."""
    op.execute(
        "UPDATE pdf_index_status SET "
        "status = 'not_indexed', "
        "chunk_count = NULL, "
        "indexed_at = NULL, "
        "error_message = NULL, "
        "extraction_backend = NULL"
    )


def downgrade() -> None:
    """Cannot restore previous index status; reset again to be safe."""
    op.execute(
        "UPDATE pdf_index_status SET "
        "status = 'not_indexed', "
        "chunk_count = NULL, "
        "indexed_at = NULL, "
        "error_message = NULL, "
        "extraction_backend = NULL"
    )
