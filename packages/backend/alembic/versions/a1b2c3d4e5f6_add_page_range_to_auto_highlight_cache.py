"""add page_start/page_end to auto_highlight_cache

Revision ID: a1b2c3d4e5f6
Revises: d4f5a6b7c8e9
Create Date: 2026-04-23
"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "d4f5a6b7c8e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Delete stale cache entries — they predate page range and can't be migrated accurately
    op.execute("DELETE FROM auto_highlight_cache")

    op.add_column(
        "auto_highlight_cache",
        sa.Column("page_start", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "auto_highlight_cache",
        sa.Column("page_end", sa.Integer(), nullable=False, server_default="10"),
    )

    op.drop_constraint(
        "uq_auto_highlight_cache_pdf_user_cats",
        "auto_highlight_cache",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_auto_highlight_cache_pdf_user_cats_pages",
        "auto_highlight_cache",
        ["pdf_id", "user_id", "categories", "page_start", "page_end"],
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
    op.drop_column("auto_highlight_cache", "page_end")
    op.drop_column("auto_highlight_cache", "page_start")
