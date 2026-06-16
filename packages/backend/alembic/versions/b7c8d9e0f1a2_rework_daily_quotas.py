"""rework daily quotas

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f7
Create Date: 2026-06-10
"""

from alembic import op
import sqlalchemy as sa


revision = "b7c8d9e0f1a2"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_usage_quotas",
        sa.Column(
            "auto_highlight_quick_remaining",
            sa.Integer(),
            server_default=sa.text("5"),
            nullable=False,
        ),
    )
    op.add_column(
        "user_usage_quotas",
        sa.Column(
            "auto_highlight_thorough_remaining",
            sa.Integer(),
            server_default=sa.text("3"),
            nullable=False,
        ),
    )
    op.add_column(
        "user_usage_quotas",
        sa.Column(
            "reset_at",
            sa.Date(),
            server_default=sa.text("(now() AT TIME ZONE 'UTC')::date"),
            nullable=False,
        ),
    )
    op.alter_column(
        "user_usage_quotas",
        "chat_uses_remaining",
        existing_type=sa.Integer(),
        server_default=sa.text("50"),
        existing_nullable=False,
    )
    op.alter_column(
        "user_usage_quotas",
        "explain_uses_remaining",
        existing_type=sa.Integer(),
        server_default=sa.text("30"),
        existing_nullable=False,
    )
    op.drop_column("user_usage_quotas", "free_uses_remaining")

    op.execute(
        sa.text(
            "UPDATE user_usage_quotas "
            "SET chat_uses_remaining = 50, "
            "    explain_uses_remaining = 30, "
            "    auto_highlight_quick_remaining = 5, "
            "    auto_highlight_thorough_remaining = 3, "
            "    reset_at = (now() AT TIME ZONE 'UTC')::date"
        )
    )


def downgrade() -> None:
    op.add_column(
        "user_usage_quotas",
        sa.Column(
            "free_uses_remaining",
            sa.Integer(),
            server_default=sa.text("5"),
            nullable=False,
        ),
    )
    op.alter_column(
        "user_usage_quotas",
        "explain_uses_remaining",
        existing_type=sa.Integer(),
        server_default=sa.text("20"),
        existing_nullable=False,
    )
    op.alter_column(
        "user_usage_quotas",
        "chat_uses_remaining",
        existing_type=sa.Integer(),
        server_default=sa.text("20"),
        existing_nullable=False,
    )
    op.drop_column("user_usage_quotas", "reset_at")
    op.drop_column("user_usage_quotas", "auto_highlight_thorough_remaining")
    op.drop_column("user_usage_quotas", "auto_highlight_quick_remaining")
