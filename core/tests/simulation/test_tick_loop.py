"""T2.1, T2.2, T2.3, T2.6, T2.7, T2.8, T2.9 — About/plan.md M2 acceptance tests."""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select

from otherworld.llm.protocol import Completion, Prompt
from otherworld.llm.providers.mock import MockLLMProvider
from otherworld.models.agent import Agent, AgentStatus, Position
from otherworld.models.events import EventRecordORM
from otherworld.models.memory import MemoryRecordORM
from otherworld.models.persona import PersonaObject, TraitVector, VoiceProfile
from otherworld.persona.compiler import Compiler
from otherworld.runtime.clock import tick_to_datetime
from otherworld.runtime.scheduler import TickScheduler, in_sleep_window

NOW = datetime.now(UTC)
FIXED_AGENT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


def _persona() -> PersonaObject:
    return PersonaObject(
        id=uuid.uuid4(), owner_id=uuid.uuid4(), version=1,
        voice=VoiceProfile(verbosity=0.4, formality=0.5, humour_style="dry", profanity_baseline=0.1),
        values=TraitVector(), source_methods=["A"], created_at=NOW,
    )


def _agent(world_id: uuid.UUID, owner_id: uuid.UUID) -> Agent:
    return Agent(
        id=FIXED_AGENT_ID, owner_id=owner_id, persona_version=1, world_id=world_id,
        display_name="Nyx", status=AgentStatus.ACTIVE, position=Position(x=0, y=0, facing="s"),
        goals=[], current_path=[], last_tick=0, created_at=tick_to_datetime(0),
    )


class SpyLLMProvider:
    """Wraps a real provider, counting calls per tier (T2.8)."""

    def __init__(self, inner):
        self.inner = inner
        self.tier1_calls = 0
        self.tier2_calls = 0

    async def tier1(self, prompt: Prompt) -> Completion:
        self.tier1_calls += 1
        return await self.inner.tier1(prompt)

    async def tier2(self, prompt: Prompt) -> Completion:
        self.tier2_calls += 1
        return await self.inner.tier2(prompt)

    async def embed(self, text: str) -> list[float]:
        return await self.inner.embed(text)


class AlwaysDangerousProvider:
    """A malicious/broken provider that only ever proposes an unregistered
    action — used to exercise T2.6 (double rejection -> idle) and T2.7
    (containment) together.
    """

    async def tier1(self, prompt: Prompt) -> Completion:
        return Completion(
            text='{"action": "execute_code", "targets": [], "reasoning": "try to escape"}',
            input_tokens=10, output_tokens=10, model="mock-dangerous",
        )

    async def tier2(self, prompt: Prompt) -> Completion:
        return await self.tier1(prompt)

    async def embed(self, text: str) -> list[float]:
        return await MockLLMProvider().embed(text)


@pytest.mark.asyncio
async def test_100_ticks_no_crash_and_100_events_written(db_session):
    world_id = uuid.uuid4()
    persona = _persona()
    bundle = Compiler.compile(persona)
    agent = _agent(world_id, persona.owner_id)
    scheduler = TickScheduler(db_session, MockLLMProvider(), random.Random(1), world_id, agent, bundle)

    events = await scheduler.run(100)

    assert len(events) == 100
    row_count = (
        await db_session.execute(select(EventRecordORM).where(EventRecordORM.world_id == world_id))
    ).scalars().all()
    assert len(row_count) == 100


@pytest.mark.asyncio
async def test_every_event_produces_a_memory(db_session):
    """T2.3 — every tick's event has importance >= MIN_IMPORTANCE_TO_REMEMBER (0.0),
    so every tick produces exactly one memory record too."""
    world_id = uuid.uuid4()
    persona = _persona()
    bundle = Compiler.compile(persona)
    agent = _agent(world_id, persona.owner_id)
    scheduler = TickScheduler(db_session, MockLLMProvider(), random.Random(2), world_id, agent, bundle)

    await scheduler.run(20)

    memories = (
        await db_session.execute(select(MemoryRecordORM).where(MemoryRecordORM.agent_id == agent.id))
    ).scalars().all()
    assert len(memories) == 20


@pytest.mark.asyncio
async def test_determinism_same_seed_byte_identical_events(db_session):
    """T2.2 — the non-negotiable one."""
    world_id = uuid.uuid4()
    persona = _persona()
    bundle = Compiler.compile(persona)

    agent1 = _agent(world_id, persona.owner_id)
    scheduler1 = TickScheduler(db_session, MockLLMProvider(), random.Random(42), world_id, agent1, bundle)
    events1 = await scheduler1.run(50)

    # Same ids will be generated again from the same seed — clear so the
    # second run's inserts don't collide with the first run's primary keys.
    await db_session.execute(delete(EventRecordORM))
    await db_session.execute(delete(MemoryRecordORM))
    await db_session.flush()

    agent2 = _agent(world_id, persona.owner_id)
    scheduler2 = TickScheduler(db_session, MockLLMProvider(), random.Random(42), world_id, agent2, bundle)
    events2 = await scheduler2.run(50)

    assert events1 == events2


@pytest.mark.asyncio
async def test_double_rejection_falls_back_to_idle_without_crashing(db_session):
    """T2.6 and T2.7 together: a provider that only ever proposes a
    containment-violating action must never crash the tick and must always
    resolve to the safe default."""
    world_id = uuid.uuid4()
    persona = _persona()
    bundle = Compiler.compile(persona)
    agent = _agent(world_id, persona.owner_id)
    scheduler = TickScheduler(
        db_session, AlwaysDangerousProvider(), random.Random(3), world_id, agent, bundle
    )

    # tick 50 is outside the sleep window (About/runtime/scheduler.py), so this exercises Tier 1.
    event = await scheduler.run_tick(50)

    assert event.action == "idle"


@pytest.mark.asyncio
async def test_tier2_never_called_without_an_escalation_trigger(db_session):
    """T2.8 — M2's world has no escalation trigger that can fire (no other
    agents, no goals, no conflicts, no reflection cycle yet)."""
    world_id = uuid.uuid4()
    persona = _persona()
    bundle = Compiler.compile(persona)
    agent = _agent(world_id, persona.owner_id)
    spy = SpyLLMProvider(MockLLMProvider())
    scheduler = TickScheduler(db_session, spy, random.Random(4), world_id, agent, bundle)

    await scheduler.run(200)  # > one full in-world day (144 ticks), covers sleep and waking hours

    assert spy.tier2_calls == 0
    assert spy.tier1_calls > 0  # sanity: Tier 1 actually got exercised on waking ticks


@pytest.mark.asyncio
async def test_trace_completeness_for_tier1_decisions(db_session):
    """T2.9 — every Tier 1/2 decision logs all About/architecture.md §17 fields."""
    world_id = uuid.uuid4()
    persona = _persona()
    bundle = Compiler.compile(persona)
    agent = _agent(world_id, persona.owner_id)
    scheduler = TickScheduler(db_session, MockLLMProvider(), random.Random(5), world_id, agent, bundle)

    await scheduler.run(50)  # crosses out of the sleep window (ticks 0-35), so Tier 1 actually fires

    tier1_traces = [t for t in scheduler.trace_log.entries if t.tier_used == 1]
    assert tier1_traces  # at least one waking (non-sleep-window) tick occurred

    for trace in tier1_traces:
        assert trace.agent_id == agent.id
        assert trace.tick >= 0
        assert trace.observation_summary
        assert isinstance(trace.retrieved_memory_ids, list)
        assert len(trace.prompt_hash) == 64
        assert trace.tier_used in (1, 2)
        assert trace.raw_completion
        assert trace.parsed_action
        assert trace.validator_result in ("accepted",) or trace.validator_result.startswith("rejected:")
        assert trace.latency_ms >= 0
        assert trace.input_tokens >= 0
        assert trace.output_tokens >= 0
        assert trace.created_at is not None


def test_sleep_window_covers_expected_hours():
    # tick 0 => hour 0 (midnight) with default config -> asleep
    assert in_sleep_window(0) is True
    # a tick well into the "day" -> awake
    assert in_sleep_window(60) is False
