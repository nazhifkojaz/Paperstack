"""add_openrouter_usage_cache

Revision ID: d4f5a6b7c8e9
Revises: c3e7d8a1b2f4
Create Date: 2026-04-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d4f5a6b7c8e9"
down_revision = "c3e7d8a1b2f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "openrouter_usage_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_count_today", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "day_started_at",
            sa.Date(),
            nullable=False,
            server_default=sa.text("(now() AT TIME ZONE 'UTC')::date"),
        ),
        sa.Column("last_request_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_key_response", postgresql.JSONB(), nullable=True),
        sa.Column("last_key_fetched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("INSERT INTO openrouter_usage_cache (id) VALUES (1)")


def downgrade() -> None:
    op.drop_table("openrouter_usage_cache")
