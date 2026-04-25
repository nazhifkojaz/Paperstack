"""add tier and progress_pct to auto_highlight_cache

Revision ID: c4d5e6f7a8b9
Revises: b2c3d4e5f6a7
Create Date: 2026-04-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("auto_highlight_cache",
        sa.Column("progress_pct", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column("auto_highlight_cache",
        sa.Column("tier", sa.String(16), nullable=False, server_default=sa.text("'quick'")))


def downgrade() -> None:
    op.drop_column("auto_highlight_cache", "tier")
    op.drop_column("auto_highlight_cache", "progress_pct")
