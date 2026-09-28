"""M6 T6.7: cost-per-agent-day and tier-share aggregation queries."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from otherworld.models.trace import DecisionTraceORM
from otherworld.output.cost import cost_per_agent_day, tier_share

NOW = datetime.now(UTC)


def _trace(agent_id: uuid.UUID, tier: int, cost: float, created_at: datetime) -> DecisionTraceORM:
    return DecisionTraceORM(
        id=uuid.uuid4(), agent_id=agent_id, tick=0, observation_summary="", retrieved_memory_ids=[],
        prompt_hash="h", tier_used=tier, raw_completion="{}", parsed_action="idle",
        validator_result="accepted", latency_ms=10.0, input_tokens=100, output_tokens=16,
        estimated_cost_usd=cost, created_at=created_at,
    )


@pytest.mark.asyncio
async def test_cost_per_agent_day_sums_same_day_traces_and_keeps_days_separate(db_session):
    agent_id = uuid.uuid4()
    day_one = datetime(2026, 9, 1, 10, tzinfo=UTC)
    day_two = datetime(2026, 9, 2, 10, tzinfo=UTC)
    db_session.add_all(
        [
            _trace(agent_id, 1, 0.01, day_one),
            _trace(agent_id, 1, 0.02, day_one.replace(hour=20)),
            _trace(agent_id, 1, 0.05, day_two),
        ]
    )
    await db_session.commit()

    result = await cost_per_agent_day(db_session, agent_id=agent_id)

    assert result[(agent_id, day_one.date())] == pytest.approx(0.03)
    assert result[(agent_id, day_two.date())] == pytest.approx(0.05)


@pytest.mark.asyncio
async def test_cost_per_agent_day_filters_to_the_requested_agent_when_given(db_session):
    agent_a, agent_b = uuid.uuid4(), uuid.uuid4()
    db_session.add_all([_trace(agent_a, 1, 0.01, NOW), _trace(agent_b, 1, 0.02, NOW)])
    await db_session.commit()

    result = await cost_per_agent_day(db_session, agent_id=agent_a)

    assert set(agent_id for agent_id, _day in result) == {agent_a}


@pytest.mark.asyncio
async def test_tier_share_reports_fraction_of_decisions_per_tier(db_session):
    agent_id = uuid.uuid4()
    db_session.add_all(
        [
            _trace(agent_id, 1, 0.01, NOW),
            _trace(agent_id, 1, 0.01, NOW),
            _trace(agent_id, 1, 0.01, NOW),
            _trace(agent_id, 2, 0.02, NOW),
        ]
    )
    await db_session.commit()

    result = await tier_share(db_session)

    assert result[1] == pytest.approx(0.75)
    assert result[2] == pytest.approx(0.25)


@pytest.mark.asyncio
async def test_tier_share_is_empty_when_no_traces_exist(db_session):
    assert await tier_share(db_session) == {}
