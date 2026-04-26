"""migrate_embedding_halfvec_2048

Revision ID: c3e7d8a1b2f4
Revises: b1c2d3e4f5a6
Create Date: 2026-04-23
"""
from alembic import op

revision = "c3e7d8a1b2f4"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("idx_pdf_chunks_embedding", table_name="pdf_chunks")
    op.drop_column("pdf_chunks", "embedding")
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


def downgrade() -> None:
    op.drop_index("idx_pdf_chunks_embedding", table_name="pdf_chunks")
    op.execute("ALTER TABLE pdf_chunks DROP COLUMN embedding")
    op.execute("TRUNCATE TABLE pdf_chunks")
    op.execute("ALTER TABLE pdf_chunks ADD COLUMN embedding vector(768)")
    op.execute(
        "CREATE INDEX idx_pdf_chunks_embedding ON pdf_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "UPDATE pdf_index_status SET status = 'not_indexed', "
        "chunk_count = NULL, indexed_at = NULL, error_message = NULL"
    )
