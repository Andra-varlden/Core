"""Regression test for the M4 real-trial post-mortem audit: spec.md §5.1's
modifiers row ("-0.20 if the same event class occurred for this agent
within 50 ticks") was entirely unimplemented, so an agent that mostly
repeats the same routine action (exactly this trial's behaviour pattern)
had every repeat scored as independently fresh.
"""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime

import pytest

from otherworld.llm.providers.mock import MockLLMProvider
from otherworld.models.agent import Position
from otherworld.runtime.resolver import Resolver

NOW = datetime.now(UTC)
ACTOR_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
TARGET_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
OTHER_TARGET_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
POSITION = Position(x=0, y=0, facing="s")


@pytest.mark.asyncio
async def test_repeating_the_same_action_within_50_ticks_is_damped(db_session):
    rng = random.Random(1)
    world_id = uuid.uuid4()

    await Resolver.resolve(
        db_session, MockLLMProvider(), rng, world_id, ACTOR_ID, POSITION, tick=100,
        action="idle", targets=[], reasoning="test",
    )
    second = await Resolver.resolve(
        db_session, MockLLMProvider(), rng, world_id, ACTOR_ID, POSITION, tick=130,
        action="idle", targets=[], reasoning="test",
    )

    assert second.importance == pytest.approx(0.0)  # 0.05 base - 0.20, floored at 0.0


@pytest.mark.asyncio
async def test_repeating_after_the_damping_window_is_not_damped(db_session):
    rng = random.Random(2)
    world_id = uuid.uuid4()

    await Resolver.resolve(
        db_session, MockLLMProvider(), rng, world_id, ACTOR_ID, POSITION, tick=100,
        action="idle", targets=[], reasoning="test",
    )
    second = await Resolver.resolve(
        db_session, MockLLMProvider(), rng, world_id, ACTOR_ID, POSITION, tick=151,
        action="idle", targets=[], reasoning="test",
    )

    assert second.importance == pytest.approx(0.05)


@pytest.mark.asyncio
async def test_a_different_action_is_not_damped_by_an_unrelated_repeat(db_session):
    rng = random.Random(3)
    world_id = uuid.uuid4()

    await Resolver.resolve(
        db_session, MockLLMProvider(), rng, world_id, ACTOR_ID, POSITION, tick=100,
        action="idle", targets=[], reasoning="test",
    )
    second = await Resolver.resolve(
        db_session, MockLLMProvider(), rng, world_id, ACTOR_ID, POSITION, tick=110,
        action="sleep", targets=[], reasoning="test",
    )

    assert second.importance == pytest.approx(0.05)


@pytest.mark.asyncio
async def test_damping_never_overrides_a_higher_importance_tier(db_session):
    """A repeated action that also happens to be a genuine first direct
    contact (or any other higher tier) must still get the higher tier —
    repetition damping only reduces the routine BASE importance, before
    the milestone floors apply."""
    rng = random.Random(4)
    world_id = uuid.uuid4()

    await Resolver.resolve(
        db_session, MockLLMProvider(), rng, world_id, ACTOR_ID, POSITION, tick=100,
        action="greet", targets=[], reasoning="test",  # no target: doesn't touch the TARGET_ID edge
    )
    event = await Resolver.resolve(
        db_session, MockLLMProvider(), rng, world_id, ACTOR_ID, POSITION, tick=110,
        action="greet", targets=[TARGET_ID], reasoning="test",  # first-ever contact with TARGET_ID
    )

    assert event.importance == pytest.approx(0.75)  # first-contact -> state change tier wins
