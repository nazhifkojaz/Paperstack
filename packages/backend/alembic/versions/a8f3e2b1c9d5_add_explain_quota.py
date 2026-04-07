"""add_explain_quota

Revision ID: a8f3e2b1c9d5
Revises: 2c55ac30360c
Create Date: 2026-03-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8f3e2b1c9d5'
down_revision: Union[str, Sequence[str], None] = '2c55ac30360c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add explain_uses_remaining column to user_usage_quotas."""
    op.add_column(
        'user_usage_quotas',
        sa.Column('explain_uses_remaining', sa.Integer(), server_default=sa.text('20'), nullable=False),
    )


def downgrade() -> None:
    """Remove explain_uses_remaining column from user_usage_quotas."""
    op.drop_column('user_usage_quotas', 'explain_uses_remaining')
