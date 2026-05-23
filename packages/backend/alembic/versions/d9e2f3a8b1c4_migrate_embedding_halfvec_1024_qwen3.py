"""migrate_embedding_halfvec_1024_qwen3

Switches embedding model from Nemotron (2048-dim) to Qwen3-Embedding-8B (1024-dim via Matryoshka).

- Clears context_chunks in chat_messages (old chunk_id references become dangling).
- Clears auto_highlight_cache (results derived from old embeddings).
- Truncates pdf_chunks (old Nemotron vectors are incompatible with the new model).
- Recreates the embedding column as halfvec(1024).
- Resets pdf_index_status so lazy re-indexing triggers on next PDF access.

Revision ID: d9e2f3a8b1c4
Revises: 2fda7121f905
Create Date: 2026-05-23
"""
from alembic import op

revision = "d9e2f3a8b1c4"
down_revision = "2fda7121f905"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE chat_messages SET context_chunks = NULL")
    op.execute("DELETE FROM auto_highlight_cache")

    op.drop_index("idx_pdf_chunks_embedding", table_name="pdf_chunks")
    op.drop_column("pdf_chunks", "embedding")
    op.execute("TRUNCATE TABLE pdf_chunks")
    op.execute("ALTER TABLE pdf_chunks ADD COLUMN embedding halfvec(1024)")
    op.execute(
        "CREATE INDEX idx_pdf_chunks_embedding ON pdf_chunks "
        "USING hnsw (embedding halfvec_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )
    op.execute(
        "UPDATE pdf_index_status SET status = 'not_indexed', "
        "chunk_count = NULL, indexed_at = NULL, error_message = NULL"
    )


def downgrade() -> None:
    op.drop_index("idx_pdf_chunks_embedding", table_name="pdf_chunks")
    op.execute("ALTER TABLE pdf_chunks DROP COLUMN embedding")
    op.execute("TRUNCATE TABLE pdf_chunks")
    op.execute("ALTER TABLE pdf_chunks ADD COLUMN embedding halfvec(2048)")
    op.execute(
        "CREATE INDEX idx_pdf_chunks_embedding ON pdf_chunks "
        "USING hnsw (embedding halfvec_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )
    op.execute(
        "UPDATE pdf_index_status SET status = 'not_indexed', "
        "chunk_count = NULL, indexed_at = NULL, error_message = NULL"
    )
