"""T5.9-adjacent — About/plan.md M5: reflection produces beliefs from
episodic memory on schedule, with mandatory persona re-grounding."""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from otherworld.llm.providers.mock import MockLLMProvider
from otherworld.models.memory import MemoryKind, MemoryRecordORM
from otherworld.models.persona import PersonaObject, TraitVector, VoiceProfile
from otherworld.persona.compiler import Compiler
from otherworld.runtime.clock import tick_to_datetime
from otherworld.runtime.reflection import ReflectionService, is_reflection_due

NOW = datetime.now(UTC)
AGENT_ID = uuid.uuid4()


def _bundle():
    persona = PersonaObject(
        id=uuid.uuid4(), owner_id=uuid.uuid4(), version=1,
        voice=VoiceProfile(verbosity=0.4, formality=0.5, humour_style="dry", profanity_baseline=0.1),
        values=TraitVector(), source_methods=["A"], created_at=NOW,
    )
    return Compiler.compile(persona)


async def _seed_episodic_memory(session, tick: int, importance: float = 0.5) -> None:
    from otherworld.models.memory import MemoryRecord, memory_to_orm

    record = MemoryRecord(
        id=uuid.uuid4(), agent_id=AGENT_ID, kind=MemoryKind.EPISODIC,
        content=f"Something happened at {tick}.",
        embedding=await MockLLMProvider().embed(f"tick-{tick}"), importance=importance, tick=tick,
        subjects=[AGENT_ID], created_at=tick_to_datetime(tick),
    )
    session.add(memory_to_orm(record))
    await session.flush()


@pytest.mark.asyncio
async def test_reflection_not_due_before_interval_or_importance_threshold(db_session):
    await _seed_episodic_memory(db_session, tick=10, importance=0.1)
    assert not await is_reflection_due(db_session, AGENT_ID, last_reflection_tick=0, tick=50)


@pytest.mark.asyncio
async def test_reflection_due_after_interval_elapses(db_session):
    assert await is_reflection_due(db_session, AGENT_ID, last_reflection_tick=0, tick=150)


@pytest.mark.asyncio
async def test_reflection_due_on_importance_sum_trigger(db_session):
    for tick in range(1, 11):  # 10 x 0.9 = 9.0, clears the 8.0 threshold
        await _seed_episodic_memory(db_session, tick=tick, importance=0.9)
    assert await is_reflection_due(db_session, AGENT_ID, last_reflection_tick=0, tick=15)


@pytest.mark.asyncio
async def test_reflect_writes_belief_derived_from_top_memories(db_session):
    for tick in range(1, 6):
        await _seed_episodic_memory(db_session, tick=tick, importance=0.9)

    beliefs = await ReflectionService.reflect(
        db_session, MockLLMProvider(), random.Random(1), AGENT_ID, _bundle(),
        last_reflection_tick=0, tick=100, created_at=NOW,
    )

    assert len(beliefs) == 1
    assert beliefs[0].kind == MemoryKind.BELIEF
    assert len(beliefs[0].derived_from) == 5

    rows = (
        await db_session.execute(
            select(MemoryRecordORM).where(
                MemoryRecordORM.agent_id == AGENT_ID, MemoryRecordORM.kind == MemoryKind.BELIEF.value
            )
        )
    ).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_reflect_is_a_noop_with_nothing_new_to_reflect_on(db_session):
    beliefs = await ReflectionService.reflect(
        db_session, MockLLMProvider(), random.Random(1), AGENT_ID, _bundle(),
        last_reflection_tick=100, tick=200, created_at=NOW,
    )
    assert beliefs == []
