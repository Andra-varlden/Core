"""T5.9 — About/plan.md M5 acceptance test: memory compression keeps the
episodic count under cap, accumulates beliefs, and protects memories tied
to a conflict."""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from otherworld.config import settings
from otherworld.llm.providers.mock import MockLLMProvider
from otherworld.models.memory import MemoryKind, MemoryRecord, MemoryRecordORM, memory_to_orm
from otherworld.models.relationship import BondState, ConflictRecord, ConflictTrigger
from otherworld.runtime.compression import compress_if_over_cap
from otherworld.social.engine import get_or_create_edge, save_edge

NOW = datetime.now(UTC)
AGENT_ID = uuid.uuid4()
OTHER_ID = uuid.uuid4()


async def _seed_episodics(session, count: int, start_tick: int = 0) -> list[uuid.UUID]:
    ids = []
    for i in range(count):
        record = MemoryRecord(
            id=uuid.uuid4(), agent_id=AGENT_ID, kind=MemoryKind.EPISODIC, content=f"event {i}",
            embedding=await MockLLMProvider().embed(f"event-{i}"), importance=0.1, tick=start_tick + i,
            subjects=[AGENT_ID], created_at=NOW,
        )
        session.add(memory_to_orm(record))
        ids.append(record.id)
    await session.flush()
    return ids


@pytest.mark.asyncio
async def test_no_compression_under_the_cap(db_session):
    await _seed_episodics(db_session, count=10)
    result = await compress_if_over_cap(
        db_session, MockLLMProvider(), random.Random(1), AGENT_ID, tick=100, created_at=NOW
    )
    assert result is None


@pytest.mark.asyncio
async def test_compression_synthesises_a_belief_and_deletes_the_batch(db_session):
    cap = settings.memory.episodic_cap
    batch = settings.memory.compression_batch
    await _seed_episodics(db_session, count=cap + 1)

    belief = await compress_if_over_cap(
        db_session, MockLLMProvider(), random.Random(1), AGENT_ID, tick=cap + 100, created_at=NOW
    )

    assert belief is not None
    assert belief.kind == MemoryKind.BELIEF
    assert len(belief.derived_from) == batch

    remaining = (
        await db_session.execute(
            select(MemoryRecordORM).where(
                MemoryRecordORM.agent_id == AGENT_ID, MemoryRecordORM.kind == MemoryKind.EPISODIC.value
            )
        )
    ).scalars().all()
    assert len(remaining) == cap + 1 - batch

    beliefs = (
        await db_session.execute(
            select(MemoryRecordORM).where(
                MemoryRecordORM.agent_id == AGENT_ID, MemoryRecordORM.kind == MemoryKind.BELIEF.value
            )
        )
    ).scalars().all()
    assert len(beliefs) == 1


@pytest.mark.asyncio
async def test_memories_tied_to_a_conflict_are_protected_from_compression(db_session):
    world_id = uuid.uuid4()
    cap = settings.memory.episodic_cap
    ids = await _seed_episodics(db_session, count=cap + 1)
    protected_id = ids[0]  # the oldest, lowest-importance — first in line otherwise

    edge, _ = await get_or_create_edge(db_session, world_id, AGENT_ID, OTHER_ID, uuid.uuid4(), tick=0)
    scar = ConflictRecord(
        id=uuid.uuid4(), trigger=ConflictTrigger.BETRAYAL, theme="test",
        severity=0.9, occurred_tick=0, resolved_tick=10, resolution="repaired",
    )
    edge = edge.model_copy(
        update={
            "bond_state": BondState.FRIEND,
            "conflict_log": [scar],
            "shared_memory_ids": [protected_id],
        }
    )
    await save_edge(db_session, edge)

    belief = await compress_if_over_cap(
        db_session, MockLLMProvider(), random.Random(1), AGENT_ID, tick=cap + 100, created_at=NOW
    )

    assert belief is not None
    assert protected_id not in belief.derived_from
    still_there = await db_session.get(MemoryRecordORM, protected_id)
    assert still_there is not None


@pytest.mark.asyncio
async def test_an_old_high_importance_memory_survives_over_newer_low_importance_ones(db_session):
    """Regression test for the M4 real-trial finding: compression must
    prioritise by importance, not by age. An early, significant memory (a
    first encounter, importance 0.60) is exactly the kind of memory that's
    both old AND meaningful — sorting oldest-first would delete it before
    any of the routine, low-importance chatter that came after it, even
    though spec.md §5.4 says to compress the LOWEST-importance ones."""
    cap = settings.memory.episodic_cap
    batch = settings.memory.compression_batch

    significant = MemoryRecord(
        id=uuid.uuid4(), agent_id=AGENT_ID, kind=MemoryKind.EPISODIC, content="a first encounter",
        embedding=await MockLLMProvider().embed("significant"), importance=0.60, tick=0,
        subjects=[AGENT_ID], created_at=NOW,
    )
    db_session.add(memory_to_orm(significant))
    await db_session.flush()

    # Enough newer, low-importance routine memories to push the agent over
    # cap without ever touching the significant one on tick-order alone.
    await _seed_episodics(db_session, count=cap, start_tick=1)

    belief = await compress_if_over_cap(
        db_session, MockLLMProvider(), random.Random(1), AGENT_ID, tick=cap + 100, created_at=NOW
    )

    assert belief is not None
    assert len(belief.derived_from) == batch
    assert significant.id not in belief.derived_from
    still_there = await db_session.get(MemoryRecordORM, significant.id)
    assert still_there is not None


@pytest.mark.asyncio
async def test_a_busy_conflicted_edge_does_not_block_compression_forever(db_session):
    """A regression guard for About/plan.md T5.1's pilot-run finding: an
    edge accumulates `shared_memory_ids` on every interaction forever, so
    protecting an ever-conflicted edge's *entire* shared history meant
    compression could never bring a busy agent back under cap at all —
    several agents were observed 1.5x+ over cap and still climbing before
    this fix. Only the most recent entries per edge should be protected.
    """
    world_id = uuid.uuid4()
    cap = settings.memory.episodic_cap
    batch = settings.memory.compression_batch
    ids = await _seed_episodics(db_session, count=cap + 1)

    edge, _ = await get_or_create_edge(db_session, world_id, AGENT_ID, OTHER_ID, uuid.uuid4(), tick=0)
    scar = ConflictRecord(
        id=uuid.uuid4(), trigger=ConflictTrigger.BETRAYAL, theme="test",
        severity=0.9, occurred_tick=0, resolved_tick=10, resolution="repaired",
    )
    # A busy pair's shared history covers *every* one of the agent's
    # episodics — the scenario that broke compression entirely.
    edge = edge.model_copy(
        update={"bond_state": BondState.FRIEND, "conflict_log": [scar], "shared_memory_ids": ids}
    )
    await save_edge(db_session, edge)

    belief = await compress_if_over_cap(
        db_session, MockLLMProvider(), random.Random(1), AGENT_ID, tick=cap + 100, created_at=NOW
    )

    assert belief is not None
    assert len(belief.derived_from) == batch  # compression still removed a full batch, not zero
