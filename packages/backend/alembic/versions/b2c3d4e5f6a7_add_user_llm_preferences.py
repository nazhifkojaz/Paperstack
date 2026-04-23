"""add user_llm_preferences

Revision ID: b2c3d4e5f6a7
Revises: e7f8a9b0c1d2
Create Date: 2026-04-24 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'e7f8a9b0c1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_llm_preferences',
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('chat_model', sa.String(100), nullable=True),
        sa.Column('auto_highlight_model', sa.String(100), nullable=True),
        sa.Column('explain_model', sa.String(100), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('user_id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )


def downgrade() -> None:
    op.drop_table('user_llm_preferences')
