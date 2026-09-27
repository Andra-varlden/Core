"""Regression test for the M4 real-trial trust-decay bug (see
`social/engine.py`'s `apply_trust_decay` docstring and `test_social_engine.py`):
`runtime/resolver.py` must reset `last_decay_tick` to None on every contact,
so a revived relationship's decay clock restarts from the new contact
instead of continuing to accrue from a stale anchor.
"""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime

import pytest

from otherworld.llm.providers.mock import MockLLMProvider
from otherworld.models.agent import Position
from otherworld.social.engine import get_edge, get_or_create_edge, save_edge
from otherworld.runtime.resolver import Resolver

NOW = datetime.now(UTC)
ACTOR_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
TARGET_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
POSITION = Position(x=0, y=0, facing="s")


@pytest.mark.asyncio
async def test_contact_clears_a_previously_set_last_decay_tick(db_session):
    world_id = uuid.uuid4()
    rng = random.Random(1)
    edge, _ = await get_or_create_edge(db_session, world_id, ACTOR_ID, TARGET_ID, uuid.uuid4(), tick=0)
    edge = edge.model_copy(update={"last_decay_tick": 500, "last_contact_tick": 0})
    await save_edge(db_session, edge)

    await Resolver.resolve(
        db_session, MockLLMProvider(), rng, world_id, ACTOR_ID, POSITION, tick=1000,
        action="greet", targets=[TARGET_ID], reasoning="test",
    )

    updated = await get_edge(db_session, world_id, ACTOR_ID, TARGET_ID)
    assert updated is not None
    assert updated.last_decay_tick is None
    assert updated.last_contact_tick == 1000
