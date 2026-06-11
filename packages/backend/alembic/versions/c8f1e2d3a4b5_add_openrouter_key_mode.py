"""add openrouter key mode

Revision ID: c8f1e2d3a4b5
Revises: b7c8d9e0f1a2
Create Date: 2026-06-11 10:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c8f1e2d3a4b5"
down_revision: Union[str, Sequence[str], None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_llm_preferences",
        sa.Column(
            "openrouter_key_mode",
            sa.String(length=10),
            server_default="app",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("user_llm_preferences", "openrouter_key_mode")
