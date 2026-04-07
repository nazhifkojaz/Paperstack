"""add_google_oauth_and_drive

Revision ID: e9f0a1b2c3d4
Revises: a8f3e2b1c9d5
Create Date: 2026-03-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = 'e9f0a1b2c3d4'
down_revision: Union[str, Sequence[str], None] = 'a8f3e2b1c9d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add new columns to users
    op.add_column('users', sa.Column('email', sa.String(255), nullable=True))
    op.add_column('users', sa.Column('storage_provider', sa.String(10), nullable=False, server_default=sa.text("'github'")))

    # 2. Make old provider-specific columns nullable (for rollback safety)
    op.alter_column('users', 'github_id', nullable=True)
    op.alter_column('users', 'github_login', nullable=True)
    op.alter_column('users', 'access_token', nullable=True)

    # 3. Create user_oauth_accounts table
    op.create_table(
        'user_oauth_accounts',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider', sa.String(10), nullable=False),
        sa.Column('provider_user_id', sa.String(255), nullable=False),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('encrypted_access_token', sa.Text(), nullable=False),
        sa.Column('encrypted_refresh_token', sa.Text(), nullable=True),
        sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('extra_data', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.UniqueConstraint('provider', 'provider_user_id', name='uq_oauth_provider_user'),
    )
    op.create_index('ix_user_oauth_accounts_user_id', 'user_oauth_accounts', ['user_id'])

    # 4. Backfill existing GitHub users into user_oauth_accounts
    op.execute("""
        INSERT INTO user_oauth_accounts
            (user_id, provider, provider_user_id, encrypted_access_token, extra_data)
        SELECT
            id,
            'github',
            github_id::TEXT,
            access_token,
            jsonb_build_object(
                'github_login', github_login,
                'repo_created', repo_created
            )
        FROM users
        WHERE github_id IS NOT NULL AND access_token IS NOT NULL
    """)

    # 5. Add drive_file_id to pdfs
    op.add_column('pdfs', sa.Column('drive_file_id', sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column('pdfs', 'drive_file_id')

    op.drop_index('ix_user_oauth_accounts_user_id', table_name='user_oauth_accounts')
    op.drop_table('user_oauth_accounts')

    op.alter_column('users', 'access_token', nullable=False)
    op.alter_column('users', 'github_login', nullable=False)
    op.alter_column('users', 'github_id', nullable=False)

    op.drop_column('users', 'storage_provider')
    op.drop_column('users', 'email')
