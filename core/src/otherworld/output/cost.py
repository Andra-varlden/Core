"""Cost instrumentation. See About/plan.md M6 T6.7: "Cost dashboard: Reports
cost per agent-day and tier shares live" — the aggregation queries a
dashboard reads from, built directly on `models.trace.DecisionTraceORM`
(About/architecture.md §17's persisted trace log).
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import cast, func, select
from sqlalchemy.dialects.postgresql import DATE
from sqlalchemy.ext.asyncio import AsyncSession

from otherworld.models.trace import DecisionTraceORM


async def cost_per_agent_day(
    session: AsyncSession, agent_id: uuid.UUID | None = None
) -> dict[tuple[uuid.UUID, date], float]:
    """Sum of `estimated_cost_usd`, grouped by agent and the UTC calendar
    day its traces were created on. `agent_id` narrows to one agent when
    given, otherwise covers everyone with a trace."""
    day = cast(DecisionTraceORM.created_at, DATE)
    query = (
        select(DecisionTraceORM.agent_id, day.label("day"), func.sum(DecisionTraceORM.estimated_cost_usd))
        .group_by(DecisionTraceORM.agent_id, day)
    )
    if agent_id is not None:
        query = query.where(DecisionTraceORM.agent_id == agent_id)

    rows = (await session.execute(query)).all()
    return {(row.agent_id, row.day): float(row[2]) for row in rows}


async def tier_share(session: AsyncSession) -> dict[int, float]:
    """Fraction of all recorded decisions that used each tier — e.g.
    `{1: 0.97, 2: 0.03}` matches the ~3% Tier-2 target from
    `config.TieringConfig`."""
    query = select(DecisionTraceORM.tier_used, func.count()).group_by(DecisionTraceORM.tier_used)
    rows = (await session.execute(query)).all()
    total = sum(count for _tier, count in rows)
    if total == 0:
        return {}
    return {tier: count / total for tier, count in rows}
