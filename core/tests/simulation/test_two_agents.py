"""T3.1-T3.4, T3.7, T3.8 — About/plan.md M3 acceptance tests: two (and three) agents."""

from __future__ import annotations

import asyncio
import random
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from otherworld.llm.protocol import Completion, Prompt
from otherworld.llm.providers.mock import MockLLMProvider
from otherworld.models.agent import Agent, AgentStatus, Position
from otherworld.models.events import EventRecordORM
from otherworld.models.memory import MemoryRecordORM
from otherworld.models.persona import PersonaObject, TraitVector, VoiceProfile
from otherworld.models.relationship import BondState, RelationshipEdgeORM
from otherworld.persona.compiler import Compiler
from otherworld.runtime.clock import tick_to_datetime
from otherworld.runtime.scheduler import MultiAgentTickScheduler
from otherworld.social.engine import get_edge

NOW = datetime.now(UTC)

AGENT_A_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
AGENT_B_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
AGENT_C_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

# tick 40 -> 400 in-world minutes -> hour 6, just past the default sleep window.
WAKING_TICK = 40


def _persona() -> PersonaObject:
    return PersonaObject(
        id=uuid.uuid4(), owner_id=uuid.uuid4(), version=1,
        voice=VoiceProfile(verbosity=0.4, formality=0.5, humour_style="dry", profanity_baseline=0.1),
        values=TraitVector(), source_methods=["A"], created_at=NOW,
    )


def _agent(agent_id: uuid.UUID, world_id: uuid.UUID, name: str) -> Agent:
    return Agent(
        id=agent_id, owner_id=uuid.uuid4(), persona_version=1, world_id=world_id,
        display_name=name, status=AgentStatus.ACTIVE, position=Position(x=0, y=0, facing="s"),
        goals=[], current_path=[], last_tick=0, created_at=tick_to_datetime(0),
    )


def _make_scheduler(
    session, provider, seed: int, world_id: uuid.UUID, agent_ids_and_names: list[tuple[uuid.UUID, str]]
):
    agents = [_agent(aid, world_id, name) for aid, name in agent_ids_and_names]
    bundles = {a.id: Compiler.compile(_persona()) for a in agents}
    return MultiAgentTickScheduler(session, provider, random.Random(seed), world_id, agents, bundles)


@pytest.mark.asyncio
async def test_two_agents_reach_acquaintance_over_500_ticks(db_session):
    """T3.1"""
    world_id = uuid.uuid4()
    scheduler = _make_scheduler(
        db_session, MockLLMProvider(), 10, world_id, [(AGENT_A_ID, "Nyx"), (AGENT_B_ID, "Vale")]
    )

    await scheduler.run(500)

    edge = await get_edge(db_session, world_id, AGENT_A_ID, AGENT_B_ID)
    assert edge is not None
    assert edge.bond_state in (BondState.ACQUAINTANCE, BondState.FRIEND)


@pytest.mark.asyncio
async def test_determinism_with_two_agents(db_session):
    """T3.2"""
    world_id = uuid.uuid4()

    scheduler1 = _make_scheduler(
        db_session, MockLLMProvider(), 99, world_id, [(AGENT_A_ID, "Nyx"), (AGENT_B_ID, "Vale")]
    )
    events1 = await scheduler1.run(60)

    await db_session.execute(EventRecordORM.__table__.delete())
    await db_session.execute(MemoryRecordORM.__table__.delete())
    await db_session.execute(RelationshipEdgeORM.__table__.delete())
    await db_session.flush()

    scheduler2 = _make_scheduler(
        db_session, MockLLMProvider(), 99, world_id, [(AGENT_A_ID, "Nyx"), (AGENT_B_ID, "Vale")]
    )
    events2 = await scheduler2.run(60)

    assert events1 == events2


@pytest.mark.asyncio
async def test_witness_gets_a_memory_of_the_exchange(db_session):
    """T3.4 — a third, un-addressed agent present for a greet gets a memory of it."""
    world_id = uuid.uuid4()
    scheduler = _make_scheduler(
        db_session, MockLLMProvider(), 5, world_id,
        [(AGENT_A_ID, "Nyx"), (AGENT_B_ID, "Vale"), (AGENT_C_ID, "Rook")],
    )

    await scheduler.run_tick(WAKING_TICK)

    witness_memories = (
        await db_session.execute(select(MemoryRecordORM).where(MemoryRecordORM.agent_id == AGENT_C_ID))
    ).scalars().all()
    assert len(witness_memories) >= 1
    assert "saw" in witness_memories[0].content.lower()


@pytest.mark.asyncio
async def test_edge_uniqueness_regardless_of_query_order(db_session):
    """T3.7 — (a,b) and (b,a) resolve to the same single row."""
    world_id = uuid.uuid4()
    scheduler = _make_scheduler(
        db_session, MockLLMProvider(), 7, world_id, [(AGENT_A_ID, "Nyx"), (AGENT_B_ID, "Vale")]
    )
    await scheduler.run_tick(WAKING_TICK)

    forward = await get_edge(db_session, world_id, AGENT_A_ID, AGENT_B_ID)
    backward = await get_edge(db_session, world_id, AGENT_B_ID, AGENT_A_ID)
    assert forward is not None
    assert forward.id == backward.id

    rows = (
        await db_session.execute(select(RelationshipEdgeORM).where(RelationshipEdgeORM.world_id == world_id))
    ).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_first_encounter_escalates_to_tier2_exactly_once_per_pair(db_session):
    """T3.8"""
    world_id = uuid.uuid4()
    scheduler = _make_scheduler(
        db_session, MockLLMProvider(), 11, world_id, [(AGENT_A_ID, "Nyx"), (AGENT_B_ID, "Vale")]
    )

    await scheduler.run(20, start_tick=WAKING_TICK)  # well past the sleep window throughout

    tier2_traces = [t for t in scheduler.trace_log.entries if t.tier_used == 2]
    # Exactly one agent of the pair gets the first-encounter Tier-2 moment
    # (whichever is processed first in agent-id order creates the edge;
    # the other never sees a missing edge at all) — see scheduler.py docstring.
    assert len(tier2_traces) == 1


@pytest.mark.asyncio
async def test_apply_order_is_by_agent_id_regardless_of_completion_order(db_session):
    """T3.3 — a provider where the higher-id agent's call finishes first
    must not change the applied (resolved) order."""

    class UnevenLatencyProvider:
        """The first tier call *dispatched* deliberately finishes *last*, so
        completion order is the reverse of dispatch order — a real test of
        "apply order is agent-id order, not completion order".
        """

        def __init__(self) -> None:
            self.inner = MockLLMProvider()
            self._call_count = 0

        async def tier1(self, prompt: Prompt) -> Completion:
            self._call_count += 1
            if self._call_count == 1:
                await asyncio.sleep(0.05)
            return await self.inner.tier1(prompt)

        async def tier2(self, prompt: Prompt) -> Completion:
            return await self.inner.tier2(prompt)

        async def embed(self, text: str) -> list[float]:
            return await self.inner.embed(text)

    world_id = uuid.uuid4()
    scheduler = _make_scheduler(
        db_session, MockLLMProvider(), 13, world_id, [(AGENT_A_ID, "Nyx"), (AGENT_B_ID, "Vale")]
    )
    await scheduler.run_tick(WAKING_TICK)  # establishes the edge via first contact (Tier 2)

    # Both agents are acquainted now, so the next tick is plain Tier 1 for
    # both — a fair comparison where only completion timing differs.
    scheduler.provider = UnevenLatencyProvider()
    events = await scheduler.run_tick(WAKING_TICK + 1)

    assert [e.actor_id for e in events] == sorted([AGENT_A_ID, AGENT_B_ID], key=str)
