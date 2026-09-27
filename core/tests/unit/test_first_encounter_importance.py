"""Regression test for the M4 real-trial finding (see `runtime/resolver.py`'s
`Resolver.resolve` docstring): the first-encounter importance bonus must key
off the pair's actual first direct interaction (`contact_count == 0`), not
the one-tick-only visibility lottery passed in as `first_encounter` — in a
world where everyone's mutually visible from tick 0, most pairs never win
that lottery and were previously locked out of ever crossing the
Friend-promotion memory-importance threshold.
"""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime

import pytest

from otherworld.llm.providers.mock import MockLLMProvider
from otherworld.models.agent import Position
from otherworld.runtime.resolver import Resolver
from otherworld.social.engine import get_edge

NOW = datetime.now(UTC)
ACTOR_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
TARGET_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
POSITION = Position(x=0, y=0, facing="s")


@pytest.mark.asyncio
async def test_a_late_first_direct_contact_still_gets_the_encounter_bonus(db_session):
    """No pre-existing edge, first_encounter=False (simulating a pair that
    missed the one-tick visibility lottery ages ago) — their actual first
    direct interaction, whenever it happens, must still count. This also
    promotes Stranger -> Acquaintance (any first interaction does, per
    `state_machine.promote_if_eligible`), which is itself an even higher
    importance tier (0.75) than the plain first-encounter bonus (0.60) —
    either way, it clears the Recognition Metric's 0.3 floor, which a
    routine action stuck at 0.15 never would have."""
    world_id = uuid.uuid4()
    rng = random.Random(1)

    event = await Resolver.resolve(
        db_session, MockLLMProvider(), rng, world_id, ACTOR_ID, POSITION, tick=500,
        action="greet", targets=[TARGET_ID], reasoning="test", first_encounter=False,
    )

    assert event.importance == pytest.approx(0.75)


@pytest.mark.asyncio
async def test_a_second_interaction_does_not_repeat_the_encounter_bonus(db_session):
    """Tick spacing is deliberately > the repetition-damping window (50
    ticks, `resolver.py`'s `_REPETITION_WINDOW_TICKS`) so this isolates the
    first-encounter-bonus behaviour from that separate mechanic."""
    world_id = uuid.uuid4()
    rng = random.Random(1)

    await Resolver.resolve(
        db_session, MockLLMProvider(), rng, world_id, ACTOR_ID, POSITION, tick=500,
        action="greet", targets=[TARGET_ID], reasoning="test", first_encounter=False,
    )
    edge = await get_edge(db_session, world_id, ACTOR_ID, TARGET_ID)
    assert edge is not None and edge.contact_count == 1

    second_event = await Resolver.resolve(
        db_session, MockLLMProvider(), rng, world_id, ACTOR_ID, POSITION, tick=560,
        action="greet", targets=[TARGET_ID], reasoning="test", first_encounter=False,
    )

    assert second_event.importance == pytest.approx(0.15)
