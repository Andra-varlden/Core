"""M6 scope (About/plan.md T6.1/T6.2): the unattended worker's per-world tick
logic — the piece Railway's worker service actually runs in production,
distinct from `cli.run_world`'s manual/test-batch tool.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from otherworld.llm.providers.mock import MockLLMProvider
from otherworld.models.agent import agent_to_orm
from otherworld.models.persona import PersonaObject, TraitVector, VoiceProfile
from otherworld.models.world import World, WorldORM, world_to_orm
from otherworld.owner.service import get_or_create_owner
from otherworld.persona.binder import Binder
from otherworld.persona.compiler import Compiler
from otherworld.persona.service import save_persona
from otherworld.runtime.clock import tick_to_datetime
from otherworld.worker import _load_world_agents, _run_one_world_tick

NOW = datetime.now(UTC)


def _persona(owner_id: uuid.UUID) -> PersonaObject:
    return PersonaObject(
        id=uuid.uuid4(), owner_id=owner_id, version=1,
        voice=VoiceProfile(verbosity=0.4, formality=0.5, humour_style="dry", profanity_baseline=0.1),
        values=TraitVector(), source_methods=["A"], created_at=NOW,
    )


@pytest.mark.asyncio
async def test_load_world_agents_returns_none_for_a_world_with_no_agents(db_session):
    assert await _load_world_agents(db_session, uuid.uuid4()) is None


@pytest.mark.asyncio
async def test_run_one_world_tick_skips_a_world_with_no_agents(db_session):
    world = World(
        id=uuid.uuid4(), name="empty-world", width=1, height=1, current_tick=0,
        population=0, population_cap=2, status="open", created_at=NOW,
    )
    db_session.add(world_to_orm(world))
    await db_session.commit()

    world_row = await db_session.get(WorldORM, world.id)
    tick_ran = await _run_one_world_tick(db_session, MockLLMProvider(), world_row)
    assert tick_ran == -1


@pytest.mark.asyncio
async def test_run_one_world_tick_advances_and_resumes_from_the_last_committed_tick(db_session):
    """T6.2: kill-and-restart resumes from the last committed tick, no
    duplicate events — proven here by two sequential calls, matching what a
    real restart between them would see (a fresh query of max(tick))."""
    world = World(
        id=uuid.uuid4(), name="worker-test-world", width=1, height=1, current_tick=0,
        population=0, population_cap=2, status="open", created_at=NOW,
    )
    db_session.add(world_to_orm(world))

    for i in range(2):
        owner = await get_or_create_owner(db_session, f"Worker{i}", f"worker{i}@example.com")
        persona = _persona(owner.id)
        await save_persona(db_session, persona)
        bundle = Compiler.compile(persona)
        agent = Binder.bind(
            bundle, owner_id=owner.id, persona_version=1, world_id=world.id,
            display_name=f"Worker{i}", spawned_at=tick_to_datetime(0),
        )
        db_session.add(agent_to_orm(agent))
    await db_session.commit()

    world_row = await db_session.get(WorldORM, world.id)

    first_tick = await _run_one_world_tick(db_session, MockLLMProvider(), world_row)
    assert first_tick == 0

    second_tick = await _run_one_world_tick(db_session, MockLLMProvider(), world_row)
    assert second_tick == 1  # resumed from the last committed tick, didn't redo tick 0


@pytest.mark.asyncio
async def test_run_one_world_tick_skips_an_agent_with_a_missing_persona_version(db_session):
    """An agent referencing a persona version that no longer exists (e.g. a
    data inconsistency) must not crash the whole world's tick — it's logged
    and skipped, the rest of the world keeps running."""
    world = World(
        id=uuid.uuid4(), name="dangling-persona-world", width=1, height=1, current_tick=0,
        population=0, population_cap=1, status="open", created_at=NOW,
    )
    db_session.add(world_to_orm(world))
    owner = await get_or_create_owner(db_session, "Dangling", "dangling@example.com")
    persona = _persona(owner.id)
    bundle = Compiler.compile(persona)
    agent = Binder.bind(
        bundle, owner_id=owner.id, persona_version=99, world_id=world.id,
        display_name="Dangling", spawned_at=tick_to_datetime(0),
    )  # note: persona never saved, so version 99 doesn't exist
    db_session.add(agent_to_orm(agent))
    await db_session.commit()

    world_row = await db_session.get(WorldORM, world.id)
    tick_ran = await _run_one_world_tick(db_session, MockLLMProvider(), world_row)
    assert tick_ran == 0  # ran without raising, even though its one agent had no bundle
