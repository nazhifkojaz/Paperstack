"""add pages JSONB column to auto_highlight_cache

Revision ID: e7f8a9b0c1d2
Revises: d4f5a6b7c8e9
Create Date: 2026-04-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "e7f8a9b0c1d2"
down_revision = "d4f5a6b7c8e9"
branch_labels = None
depends_on = None

_DEFAULT_PAGES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]


def upgrade() -> None:
    op.execute("DELETE FROM auto_highlight_cache")

    op.add_column(
        "auto_highlight_cache",
        sa.Column("pages", JSONB, nullable=False, server_default=str(_DEFAULT_PAGES)),
    )

    op.drop_constraint(
        "uq_auto_highlight_cache_pdf_user_cats",
        "auto_highlight_cache",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_auto_highlight_cache_pdf_user_cats_pages",
        "auto_highlight_cache",
        ["pdf_id", "user_id", "categories", "pages"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_auto_highlight_cache_pdf_user_cats_pages",
        "auto_highlight_cache",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_auto_highlight_cache_pdf_user_cats",
        "auto_highlight_cache",
        ["pdf_id", "user_id", "categories"],
    )
    op.drop_column("auto_highlight_cache", "pages")
