"""revise_chunk_type_and_backend

Add pdf_chunks.chunk_type (NOT NULL DEFAULT 'paragraph') and
pdf_index_status.extraction_backend (nullable), plus a composite index on
(pdf_id, chunk_type) to support chunk_type-filtered retrieval (Phase 5).

server_default='paragraph' means legacy chunks auto-classify as paragraph —
no backfill, no reindex. Nothing reads these columns yet, so this revision is
behavior-neutral on its own.

Revision ID: c5d6e7f8a9b0
Revises: a2c3d4e5f6a7
Create Date: 2026-06-16 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, Sequence[str], None] = "a2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pdf_chunks",
        sa.Column(
            "chunk_type",
            sa.String(length=16),
            nullable=False,
            server_default="paragraph",
        ),
    )
    op.add_column(
        "pdf_index_status",
        sa.Column("extraction_backend", sa.String(length=32), nullable=True),
    )
    op.create_index(
        "idx_pdf_chunks_pdf_type", "pdf_chunks", ["pdf_id", "chunk_type"], unique=False
    )


def downgrade() -> None:
    op.drop_index("idx_pdf_chunks_pdf_type", table_name="pdf_chunks")
    op.drop_column("pdf_index_status", "extraction_backend")
    op.drop_column("pdf_chunks", "chunk_type")
