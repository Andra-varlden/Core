"""About/plan.md M5: the periodic faction scan (About/spec.md §8.3) actually
runs inside the tick loop and finds cliques over a real, materialised
relationship graph."""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime

import pytest

from otherworld.config import settings
from otherworld.llm.providers.mock import MockLLMProvider
from otherworld.models.agent import Agent, AgentStatus, Position
from otherworld.models.persona import PersonaObject, TraitVector, VoiceProfile
from otherworld.models.relationship import BondState
from otherworld.persona.compiler import Compiler
from otherworld.runtime.clock import tick_to_datetime
from otherworld.runtime.scheduler import MultiAgentTickScheduler
from otherworld.social.engine import get_or_create_edge, save_edge

NOW = datetime.now(UTC)
A_ID, B_ID, C_ID = uuid.UUID(int=1), uuid.UUID(int=2), uuid.UUID(int=3)


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


@pytest.mark.asyncio
async def test_faction_scan_finds_a_clique_on_schedule(db_session):
    world_id = uuid.uuid4()
    agents = [_agent(A_ID, world_id, "A"), _agent(B_ID, world_id, "B"), _agent(C_ID, world_id, "C")]
    bundles = {a.id: Compiler.compile(_persona()) for a in agents}
    scheduler = MultiAgentTickScheduler(
        db_session, MockLLMProvider(), random.Random(1), world_id, agents, bundles
    )

    for x, y in ((A_ID, B_ID), (B_ID, C_ID), (A_ID, C_ID)):
        edge, _ = await get_or_create_edge(db_session, world_id, x, y, uuid.uuid4(), tick=0)
        edge = edge.model_copy(update={"bond_state": BondState.FRIEND, "trust": 0.6})
        await save_edge(db_session, edge)

    assert scheduler.cliques == []  # not scanned yet

    await scheduler.run_tick(0)  # tick 0 always scans (never scanned before)

    assert len(scheduler.cliques) == 1
    assert scheduler.cliques[0].members == frozenset({A_ID, B_ID, C_ID})


@pytest.mark.asyncio
async def test_faction_scan_does_not_rerun_before_the_interval_elapses(db_session):
    world_id = uuid.uuid4()
    agents = [_agent(A_ID, world_id, "A"), _agent(B_ID, world_id, "B")]
    bundles = {a.id: Compiler.compile(_persona()) for a in agents}
    scheduler = MultiAgentTickScheduler(
        db_session, MockLLMProvider(), random.Random(1), world_id, agents, bundles
    )

    await scheduler.run_tick(0)
    first_scan_tick = scheduler._last_faction_scan_tick

    await scheduler.run_tick(1)
    assert scheduler._last_faction_scan_tick == first_scan_tick

    await scheduler.run_tick(settings.factions.scan_interval_ticks)
    assert scheduler._last_faction_scan_tick == settings.factions.scan_interval_ticks
