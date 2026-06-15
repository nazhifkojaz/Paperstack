"""add_content_for_embedding_to_pdf_chunks

Adds a nullable `content_for_embedding` column to `pdf_chunks`.
When non-null, this is the text that was actually embedded (i.e., the raw
chunk content with a contextual prefix: "Paper: <title>\nSection: <section>").
When null (legacy chunks, or when CONTEXTUAL_RETRIEVAL_ENABLED=False), the
embedding was computed from the raw `content` column.

The TSVECTOR `search_vector` continues to be generated from `content` (raw),
so keyword search is unaffected by contextualization.

Revision ID: a2c3d4e5f6a7
Revises: e2a4c6f8b0d1
Create Date: 2026-06-15 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "e2a4c6f8b0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pdf_chunks",
        sa.Column("content_for_embedding", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pdf_chunks", "content_for_embedding")
