"""last_decay_tick on relationship edges (trust-decay compounding fix)

Revision ID: a1c4f3e9b2d7
Revises: 8be52313d356
Create Date: 2026-09-19 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c4f3e9b2d7'
down_revision: Union[str, None] = '8be52313d356'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'relationship_edges',
        sa.Column('last_decay_tick', sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('relationship_edges', 'last_decay_tick')
