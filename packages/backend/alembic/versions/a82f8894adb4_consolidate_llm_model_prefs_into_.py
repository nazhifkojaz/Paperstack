"""consolidate llm model prefs into conversation and analysis knobs

Replaces the per-feature model columns (chat_model, explain_model,
auto_highlight_model) with two task-category columns:
  - conversation_model  (chat + explain)
  - analysis_model      (auto-highlight + summaries)

Revision ID: a82f8894adb4
Revises: e009df6a4380
Create Date: 2026-07-10 21:57:16.883296

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a82f8894adb4"
down_revision: Union[str, Sequence[str], None] = "e009df6a4380"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "user_llm_preferences",
        sa.Column("conversation_model", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "user_llm_preferences",
        sa.Column("analysis_model", sa.String(length=100), nullable=True),
    )
    # Backfill: conversation <- first non-null of chat/explain;
    # analysis <- auto_highlight.
    op.execute(
        "UPDATE user_llm_preferences "
        "SET conversation_model = COALESCE(chat_model, explain_model), "
        "analysis_model = auto_highlight_model"
    )
    op.drop_column("user_llm_preferences", "chat_model")
    op.drop_column("user_llm_preferences", "explain_model")
    op.drop_column("user_llm_preferences", "auto_highlight_model")


def downgrade() -> None:
    """Downgrade schema: restore the three per-feature columns."""
    op.add_column(
        "user_llm_preferences",
        sa.Column("chat_model", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "user_llm_preferences",
        sa.Column("explain_model", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "user_llm_preferences",
        sa.Column("auto_highlight_model", sa.String(length=100), nullable=True),
    )
    # Reverse mapping: both conversation features point at the shared knob.
    op.execute(
        "UPDATE user_llm_preferences "
        "SET chat_model = conversation_model, "
        "explain_model = conversation_model, "
        "auto_highlight_model = analysis_model"
    )
    op.drop_column("user_llm_preferences", "conversation_model")
    op.drop_column("user_llm_preferences", "analysis_model")
