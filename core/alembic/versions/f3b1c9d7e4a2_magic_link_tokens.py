"""magic_link_tokens table (M6 auth)

Revision ID: f3b1c9d7e4a2
Revises: a1c4f3e9b2d7
Create Date: 2026-09-27 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f3b1c9d7e4a2'
down_revision: Union[str, None] = 'a1c4f3e9b2d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'magic_link_tokens',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_magic_link_tokens_owner_id', 'magic_link_tokens', ['owner_id'])
    op.create_index('ix_magic_link_tokens_token_hash', 'magic_link_tokens', ['token_hash'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_magic_link_tokens_token_hash', table_name='magic_link_tokens')
    op.drop_index('ix_magic_link_tokens_owner_id', table_name='magic_link_tokens')
    op.drop_table('magic_link_tokens')
