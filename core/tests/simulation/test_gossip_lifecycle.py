"""T5.10, T5.11 — About/plan.md M5 acceptance tests: gossip hop limit and
pile-on damping, observed end-to-end through `runtime/resolver.py`'s
`confide` wiring against a real database."""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from otherworld.llm.providers.mock import MockLLMProvider
from otherworld.models.agent import Position
from otherworld.models.memory import MemoryKind, MemoryRecord, MemoryRecordORM, memory_to_orm
from otherworld.runtime.resolver import Resolver

NOW = datetime.now(UTC)
ACTOR_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
LISTENER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
SUBJECT_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
POSITION = Position(x=0, y=0, facing="s")


async def _seed_belief(
    session, agent_id: uuid.UUID, subject_id: uuid.UUID, importance: float, hop_count: int, valence: float
) -> uuid.UUID:
    belief_id = uuid.uuid4()
    record = MemoryRecord(
        id=belief_id, agent_id=agent_id, kind=MemoryKind.BELIEF, content="They can't be trusted.",
        embedding=await MockLLMProvider().embed("belief"), importance=importance, tick=0,
        subjects=[subject_id], hop_count=hop_count, valence=valence, created_at=NOW,
    )
    session.add(memory_to_orm(record))
    await session.flush()
    return belief_id


@pytest.mark.asyncio
async def test_confide_propagates_belief_to_listener_with_incremented_hop(db_session):
    world_id = uuid.uuid4()
    belief_id = await _seed_belief(
        db_session, ACTOR_ID, SUBJECT_ID, importance=0.8, hop_count=0, valence=-0.7
    )

    await Resolver.resolve(
        db_session, MockLLMProvider(), random.Random(1), world_id, ACTOR_ID, POSITION, tick=10,
        action="confide", targets=[LISTENER_ID], reasoning="test",
        params={"belief_id": str(belief_id), "about_agent_id": str(SUBJECT_ID)},
    )

    rows = (
        await db_session.execute(
            select(MemoryRecordORM).where(
                MemoryRecordORM.agent_id == LISTENER_ID, MemoryRecordORM.kind == MemoryKind.BELIEF.value
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].hop_count == 1
    assert rows[0].valence == -0.7
    assert SUBJECT_ID in rows[0].subjects


@pytest.mark.asyncio
async def test_confide_does_not_propagate_a_belief_at_the_hop_limit(db_session):
    world_id = uuid.uuid4()
    belief_id = await _seed_belief(
        db_session, ACTOR_ID, SUBJECT_ID, importance=0.8, hop_count=3, valence=-0.7
    )

    await Resolver.resolve(
        db_session, MockLLMProvider(), random.Random(1), world_id, ACTOR_ID, POSITION, tick=10,
        action="confide", targets=[LISTENER_ID], reasoning="test",
        params={"belief_id": str(belief_id), "about_agent_id": str(SUBJECT_ID)},
    )

    rows = (
        await db_session.execute(
            select(MemoryRecordORM).where(
                MemoryRecordORM.agent_id == LISTENER_ID, MemoryRecordORM.kind == MemoryKind.BELIEF.value
            )
        )
    ).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_confide_with_missing_gossip_params_is_a_harmless_noop(db_session):
    world_id = uuid.uuid4()
    event = await Resolver.resolve(
        db_session, MockLLMProvider(), random.Random(1), world_id, ACTOR_ID, POSITION, tick=10,
        action="confide", targets=[LISTENER_ID], reasoning="just talking", params={},
    )
    assert event.action == "confide"


@pytest.mark.asyncio
async def test_pileon_suppresses_further_propagation_above_threshold(db_session):
    world_id = uuid.uuid4()
    # 5 other agents already hold a negative, *inherited* belief about
    # SUBJECT_ID — above the pileon_agent_threshold (4).
    for _ in range(5):
        await _seed_belief(
            db_session, uuid.uuid4(), SUBJECT_ID, importance=0.8, hop_count=1, valence=-0.5
        )
    # The actor's own belief is hop_count=0 (formed directly, not gossiped)
    # so it doesn't itself count toward the "inherited belief" pileon check.
    belief_id = await _seed_belief(
        db_session, ACTOR_ID, SUBJECT_ID, importance=0.8, hop_count=0, valence=-0.7
    )

    await Resolver.resolve(
        db_session, MockLLMProvider(), random.Random(1), world_id, ACTOR_ID, POSITION, tick=10,
        action="confide", targets=[LISTENER_ID], reasoning="test",
        params={"belief_id": str(belief_id), "about_agent_id": str(SUBJECT_ID)},
    )

    rows = (
        await db_session.execute(
            select(MemoryRecordORM).where(
                MemoryRecordORM.agent_id == LISTENER_ID, MemoryRecordORM.kind == MemoryKind.BELIEF.value
            )
        )
    ).scalars().all()
    assert rows == []
