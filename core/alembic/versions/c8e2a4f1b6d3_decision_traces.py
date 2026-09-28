"""decision_traces table (M6 cost instrumentation, T6.7)

Revision ID: c8e2a4f1b6d3
Revises: f3b1c9d7e4a2
Create Date: 2026-09-28 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c8e2a4f1b6d3'
down_revision: Union[str, None] = 'f3b1c9d7e4a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'decision_traces',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tick', sa.Integer(), nullable=False),
        sa.Column('observation_summary', sa.String(), nullable=False),
        sa.Column('retrieved_memory_ids', sa.JSON(), nullable=False),
        sa.Column('prompt_hash', sa.String(), nullable=False),
        sa.Column('tier_used', sa.Integer(), nullable=False),
        sa.Column('raw_completion', sa.String(), nullable=False),
        sa.Column('parsed_action', sa.String(), nullable=False),
        sa.Column('validator_result', sa.String(), nullable=False),
        sa.Column('latency_ms', sa.Float(), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=False),
        sa.Column('output_tokens', sa.Integer(), nullable=False),
        sa.Column('estimated_cost_usd', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_decision_traces_agent_id', 'decision_traces', ['agent_id'])
    op.create_index('ix_decision_traces_tick', 'decision_traces', ['tick'])
    op.create_index('ix_decision_traces_tier_used', 'decision_traces', ['tier_used'])
    op.create_index('ix_decision_traces_created_at', 'decision_traces', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_decision_traces_created_at', table_name='decision_traces')
    op.drop_index('ix_decision_traces_tier_used', table_name='decision_traces')
    op.drop_index('ix_decision_traces_tick', table_name='decision_traces')
    op.drop_index('ix_decision_traces_agent_id', table_name='decision_traces')
    op.drop_table('decision_traces')
