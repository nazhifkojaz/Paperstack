"""add_full_text_search_index

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-04-07 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE pdf_chunks ADD COLUMN search_vector tsvector
            GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
        """
    )
    op.execute(
        "CREATE INDEX idx_pdf_chunks_search ON pdf_chunks USING GIN(search_vector)"
    )


def downgrade() -> None:
    op.drop_index("idx_pdf_chunks_search", table_name="pdf_chunks")
    op.drop_column("pdf_chunks", "search_vector")
