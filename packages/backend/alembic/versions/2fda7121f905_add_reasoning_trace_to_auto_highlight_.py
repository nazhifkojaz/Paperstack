"""add reasoning_trace to auto_highlight_cache

Revision ID: 2fda7121f905
Revises: c4d5e6f7a8b9
Create Date: 2026-05-05 11:19:12.021111

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2fda7121f905"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "auto_highlight_cache", sa.Column("reasoning_trace", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("auto_highlight_cache", "reasoning_trace")
