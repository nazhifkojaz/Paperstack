"""collection_insights table

Revision ID: b3c4d5e6f7a8
Revises: a82f8894adb4
Create Date: 2026-07-10 22:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, Sequence[str], None] = "a82f8894adb4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "collection_insights",
        sa.Column(
            "id",
            sa.UUID(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "collection_id",
            sa.UUID(),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'generating'"),
        ),
        sa.Column(
            "progress_pct", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "is_stale",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("payload", JSONB()),
        sa.Column("error_message", sa.Text()),
        sa.Column("model", sa.String(100)),
        sa.Column("generated_at", sa.DateTime(timezone=True)),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "collection_id",
            "kind",
            name="uq_collection_insight_kind",
        ),
        sa.CheckConstraint(
            "kind IN ('synthesis', 'gaps', 'graph', 'comparison')",
            name="ck_collection_insight_kind",
        ),
        sa.CheckConstraint(
            "status IN ('generating', 'complete', 'failed')",
            name="ck_collection_insight_status",
        ),
    )
    op.create_index(
        "ix_collection_insights_collection_id",
        "collection_insights",
        ["collection_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_collection_insights_collection_id", table_name="collection_insights"
    )
    op.drop_table("collection_insights")
