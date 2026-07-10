"""add pdf_summary and summary quota

Revision ID: e009df6a4380
Revises: cbc91cf1ac88
Create Date: 2026-07-10 21:00:30.372972

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e009df6a4380"
down_revision: Union[str, Sequence[str], None] = "cbc91cf1ac88"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "pdf_summaries",
        sa.Column(
            "pdf_id",
            sa.UUID(),
            sa.ForeignKey("pdfs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'not_generated'"),
        ),
        sa.Column(
            "progress_pct", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("error_message", sa.Text()),
        sa.Column("tldr", sa.Text()),
        sa.Column("problem", sa.Text()),
        sa.Column("method", sa.Text()),
        sa.Column("dataset", sa.Text()),
        sa.Column("result", sa.Text()),
        sa.Column("contribution", sa.Text()),
        sa.Column("key_claims", JSONB()),
        sa.Column(
            "edited_fields",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("openalex_id", sa.String(64)),
        sa.Column("referenced_openalex_ids", JSONB()),
        sa.Column("model", sa.String(100)),
        sa.Column("generated_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('not_generated', 'generating', 'complete', 'failed')",
            name="ck_pdf_summaries_status",
        ),
    )
    # halfvec column + HNSW index via raw SQL (mirrors d9e2f3a8b1c4)
    op.execute("ALTER TABLE pdf_summaries ADD COLUMN paper_embedding halfvec(1024)")
    op.execute(
        "CREATE INDEX idx_pdf_summaries_embedding ON pdf_summaries "
        "USING hnsw (paper_embedding halfvec_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )
    op.add_column(
        "user_usage_quotas",
        sa.Column(
            "summary_uses_remaining",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("10"),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("user_usage_quotas", "summary_uses_remaining")
    op.drop_index("idx_pdf_summaries_embedding", table_name="pdf_summaries")
    op.drop_table("pdf_summaries")
