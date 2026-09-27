"""decision_weight_overrides on persona objects (Method D)

Revision ID: 8be52313d356
Revises: 30ca69dcbf65
Create Date: 2026-09-18 16:55:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8be52313d356'
down_revision: Union[str, None] = '30ca69dcbf65'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'persona_objects',
        sa.Column('decision_weight_overrides', sa.JSON(), nullable=False, server_default='{}'),
    )


def downgrade() -> None:
    op.drop_column('persona_objects', 'decision_weight_overrides')
