"""Add color_labels to users and migrate annotation colors

- Adds `color_labels` JSONB column to `users` table.
- Migrates annotation colors not in the unified 8-color palette to #FFFF00 (yellow).
- Sets NULL annotation colors to #FFFF00.

Revision ID: a1b2c3d4e5f7
Revises: d9e2f3a8b1c4
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "a1b2c3d4e5f7"
down_revision = "d9e2f3a8b1c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("color_labels", JSONB, nullable=True),
    )

    op.execute(
        sa.text(
            "UPDATE annotations SET color = '#FFFF00' "
            "WHERE color IS NULL "
            "OR color NOT IN ("
            "'#22c55e', '#3b82f6', '#a855f7', '#f97316', '#6b7280', "
            "'#FFFF00', '#EF4444', '#00FFFF'"
            ")"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("UPDATE annotations SET color = NULL WHERE color = '#FFFF00'")
    )
    op.drop_column("users", "color_labels")
