"""add_training_data_schema

Revision ID: e2a4c6f8b0d1
Revises: c8f1e2d3a4b5
Create Date: 2026-06-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import HALFVEC


revision: str = "e2a4c6f8b0d1"
down_revision: Union[str, Sequence[str], None] = "c8f1e2d3a4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE SCHEMA IF NOT EXISTS training_data")

    op.create_table(
        "rag_interactions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "assistant_message_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("query_embedding", HALFVEC(1024), nullable=True),
        sa.Column("embedding_model", sa.Text(), nullable=False),
        sa.Column(
            "embedding_dimensions",
            sa.Integer(),
            server_default=sa.text("1024"),
            nullable=False,
        ),
        sa.Column("scope_type", sa.String(length=20), nullable=False),
        sa.Column("pdf_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "retrieved_chunks", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("retrieval_top_k", sa.Integer(), nullable=False),
        sa.Column(
            "retrieval_config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("prompt_context", sa.Text(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("system_prompt_hash", sa.Text(), nullable=False),
        sa.Column(
            "prompt_messages", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("llm_model", sa.Text(), nullable=False),
        sa.Column("llm_provider", sa.Text(), nullable=False),
        sa.Column(
            "generation_config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("assistant_reply", sa.Text(), nullable=False),
        sa.Column(
            "cited_chunk_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=True,
        ),
        sa.Column("cited_page_nums", postgresql.ARRAY(sa.Integer()), nullable=True),
        sa.Column(
            "citation_events",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "citation_parse_status",
            sa.String(length=20),
            server_default=sa.text("'parsed'"),
            nullable=False,
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column(
            "training_eligible",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("consent_version", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "scope_type IN ('single_pdf', 'collection')",
            name="ck_training_rag_interactions_scope_type",
        ),
        sa.ForeignKeyConstraint(
            ["assistant_message_id"], ["chat_messages.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["collection_id"], ["collections.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["chat_conversations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["pdf_id"], ["pdfs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["user_message_id"], ["chat_messages.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="training_data",
    )
    op.create_index(
        "idx_rag_interactions_user",
        "rag_interactions",
        ["user_id"],
        schema="training_data",
    )
    op.create_index(
        "idx_rag_interactions_created",
        "rag_interactions",
        ["created_at"],
        schema="training_data",
    )
    op.create_index(
        "idx_rag_interactions_pdf",
        "rag_interactions",
        ["pdf_id"],
        schema="training_data",
    )
    op.create_index(
        "idx_rag_interactions_conversation",
        "rag_interactions",
        ["conversation_id"],
        schema="training_data",
    )
    op.create_index(
        "idx_rag_interactions_assistant_message",
        "rag_interactions",
        ["assistant_message_id"],
        unique=True,
        schema="training_data",
    )

    op.create_table(
        "chunk_feedback",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("interaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("retrieval_rank", sa.Integer(), nullable=False),
        sa.Column("retrieval_score", sa.Float(), nullable=False),
        sa.Column(
            "included_in_prompt",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("prompt_rank", sa.Integer(), nullable=True),
        sa.Column(
            "was_cited",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("citation_rank", sa.Integer(), nullable=True),
        sa.Column("citation_text", sa.Text(), nullable=True),
        sa.Column("user_rating", sa.SmallInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["chunk_id"], ["pdf_chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["interaction_id"],
            ["training_data.rag_interactions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "interaction_id",
            "chunk_id",
            name="uq_training_chunk_feedback_interaction_chunk",
        ),
        schema="training_data",
    )
    op.create_index(
        "idx_chunk_feedback_interaction",
        "chunk_feedback",
        ["interaction_id"],
        schema="training_data",
    )
    op.create_index(
        "idx_chunk_feedback_chunk",
        "chunk_feedback",
        ["chunk_id"],
        schema="training_data",
    )

    op.create_table(
        "interaction_feedback",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("interaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thumbs_up", sa.Boolean(), nullable=True),
        sa.Column("feedback_text", sa.Text(), nullable=True),
        sa.Column(
            "follow_up_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "copied_answer",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("expanded_citations", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["interaction_id"],
            ["training_data.rag_interactions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "interaction_id",
            name="uq_training_interaction_feedback_interaction",
        ),
        schema="training_data",
    )


def downgrade() -> None:
    op.drop_table("interaction_feedback", schema="training_data")
    op.drop_index(
        "idx_chunk_feedback_chunk",
        table_name="chunk_feedback",
        schema="training_data",
    )
    op.drop_index(
        "idx_chunk_feedback_interaction",
        table_name="chunk_feedback",
        schema="training_data",
    )
    op.drop_table("chunk_feedback", schema="training_data")
    op.drop_index(
        "idx_rag_interactions_assistant_message",
        table_name="rag_interactions",
        schema="training_data",
    )
    op.drop_index(
        "idx_rag_interactions_conversation",
        table_name="rag_interactions",
        schema="training_data",
    )
    op.drop_index(
        "idx_rag_interactions_pdf",
        table_name="rag_interactions",
        schema="training_data",
    )
    op.drop_index(
        "idx_rag_interactions_created",
        table_name="rag_interactions",
        schema="training_data",
    )
    op.drop_index(
        "idx_rag_interactions_user",
        table_name="rag_interactions",
        schema="training_data",
    )
    op.drop_table("rag_interactions", schema="training_data")
    op.execute("DROP SCHEMA IF EXISTS training_data")
