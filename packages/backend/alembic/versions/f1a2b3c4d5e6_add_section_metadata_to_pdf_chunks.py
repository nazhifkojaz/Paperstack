"""add_section_metadata_to_pdf_chunks

Revision ID: f1a2b3c4d5e6
Revises: e9f0a1b2c3d4
Create Date: 2026-04-07 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e9f0a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pdf_chunks", sa.Column("section_title", sa.String(500), nullable=True)
    )
    op.add_column("pdf_chunks", sa.Column("section_level", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("pdf_chunks", "section_level")
    op.drop_column("pdf_chunks", "section_title")
