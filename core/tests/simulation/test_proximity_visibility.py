"""About/plan.md M5: perception is proximity-gated (About/spec.md §9.1's
`perception_radius`), not "everyone in the world is visible" — the M2/M3
abstract-room model this replaces (About/runtime/scheduler.py's
`_materialise_new_encounters`)."""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime

import pytest

from otherworld.config import settings
from otherworld.llm.providers.mock import MockLLMProvider
from otherworld.models.agent import Agent, AgentStatus, Position
from otherworld.models.persona import PersonaObject, TraitVector, VoiceProfile
from otherworld.persona.compiler import Compiler
from otherworld.runtime.clock import tick_to_datetime
from otherworld.runtime.scheduler import MultiAgentTickScheduler
from otherworld.social.engine import get_edge

NOW = datetime.now(UTC)
AGENT_A_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
AGENT_B_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
WAKING_TICK = 40


def _persona() -> PersonaObject:
    return PersonaObject(
        id=uuid.uuid4(), owner_id=uuid.uuid4(), version=1,
        voice=VoiceProfile(verbosity=0.4, formality=0.5, humour_style="dry", profanity_baseline=0.1),
        values=TraitVector(), source_methods=["A"], created_at=NOW,
    )


def _agent(agent_id: uuid.UUID, world_id: uuid.UUID, name: str, x: int, y: int) -> Agent:
    return Agent(
        id=agent_id, owner_id=uuid.uuid4(), persona_version=1, world_id=world_id,
        display_name=name, status=AgentStatus.ACTIVE, position=Position(x=x, y=y, facing="s"),
        goals=[], current_path=[], last_tick=0, created_at=tick_to_datetime(0),
    )


@pytest.mark.asyncio
async def test_agents_far_apart_never_meet(db_session):
    world_id = uuid.uuid4()
    radius = settings.world.perception_radius
    agents = [
        _agent(AGENT_A_ID, world_id, "Nyx", 0, 0),
        _agent(AGENT_B_ID, world_id, "Vale", radius + 5, radius + 5),
    ]
    bundles = {a.id: Compiler.compile(_persona()) for a in agents}
    scheduler = MultiAgentTickScheduler(
        db_session, MockLLMProvider(), random.Random(1), world_id, agents, bundles
    )

    await scheduler.run(20, start_tick=WAKING_TICK)

    edge = await get_edge(db_session, world_id, AGENT_A_ID, AGENT_B_ID)
    assert edge is None


@pytest.mark.asyncio
async def test_agents_within_radius_do_meet(db_session):
    world_id = uuid.uuid4()
    radius = settings.world.perception_radius
    agents = [
        _agent(AGENT_A_ID, world_id, "Nyx", 0, 0),
        _agent(AGENT_B_ID, world_id, "Vale", radius - 1, 0),
    ]
    bundles = {a.id: Compiler.compile(_persona()) for a in agents}
    scheduler = MultiAgentTickScheduler(
        db_session, MockLLMProvider(), random.Random(1), world_id, agents, bundles
    )

    await scheduler.run_tick(WAKING_TICK)

    edge = await get_edge(db_session, world_id, AGENT_A_ID, AGENT_B_ID)
    assert edge is not None
