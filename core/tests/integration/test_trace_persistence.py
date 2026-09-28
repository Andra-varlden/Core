"""M6 T6.7: decision traces persist to the DB, not just the in-memory
`TraceLog`, so a cost dashboard has something durable to query."""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from otherworld.llm.providers.mock import MockLLMProvider
from otherworld.models.agent import agent_to_orm
from otherworld.models.persona import PersonaObject, TraitVector, VoiceProfile
from otherworld.models.trace import DecisionTraceORM
from otherworld.owner.service import get_or_create_owner
from otherworld.persona.binder import Binder
from otherworld.persona.compiler import Compiler
from otherworld.persona.service import save_persona
from otherworld.runtime.clock import tick_to_datetime
from otherworld.runtime.scheduler import MultiAgentTickScheduler, TickScheduler

NOW = datetime.now(UTC)


def _persona(owner_id: uuid.UUID) -> PersonaObject:
    return PersonaObject(
        id=uuid.uuid4(), owner_id=owner_id, version=1,
        voice=VoiceProfile(verbosity=0.4, formality=0.5, humour_style="dry", profanity_baseline=0.1),
        values=TraitVector(), source_methods=["A"], created_at=NOW,
    )


async def _bound_agent(db_session, handle: str, world_id: uuid.UUID):
    owner = await get_or_create_owner(db_session, handle, f"{handle.lower()}@example.com")
    persona = _persona(owner.id)
    await save_persona(db_session, persona)
    bundle = Compiler.compile(persona)
    agent = Binder.bind(
        bundle, owner_id=owner.id, persona_version=1, world_id=world_id,
        display_name=handle, spawned_at=tick_to_datetime(0),
    )
    db_session.add(agent_to_orm(agent))
    return agent, bundle


@pytest.mark.asyncio
async def test_single_agent_scheduler_persists_a_decision_trace_row(db_session):
    world_id = uuid.uuid4()
    agent, bundle = await _bound_agent(db_session, "Solo", world_id)
    await db_session.commit()

    # Tick 40 (10 min/tick -> hour 6, past the sleep window) forces a real
    # Tier 1 decision, not a cost-free `sleep` short-circuit — otherwise no
    # trace would be recorded.
    scheduler = TickScheduler(db_session, MockLLMProvider(), random.Random(0), world_id, agent, bundle)
    await scheduler.run_tick(40)
    await db_session.commit()

    rows = (
        await db_session.execute(select(DecisionTraceORM).where(DecisionTraceORM.agent_id == agent.id))
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].tick == 40
    assert rows[0].estimated_cost_usd > 0
    assert rows[0].input_tokens > 0
    assert rows[0].output_tokens > 0


@pytest.mark.asyncio
async def test_multi_agent_scheduler_persists_one_trace_row_per_deciding_agent(db_session):
    world_id = uuid.uuid4()
    agent_a, bundle_a = await _bound_agent(db_session, "MultiA", world_id)
    agent_b, bundle_b = await _bound_agent(db_session, "MultiB", world_id)
    await db_session.commit()

    scheduler = MultiAgentTickScheduler(
        db_session, MockLLMProvider(), random.Random(0), world_id,
        [agent_a, agent_b], {agent_a.id: bundle_a, agent_b.id: bundle_b},
    )
    await scheduler.run_tick(40)
    await db_session.commit()

    rows = (await db_session.execute(select(DecisionTraceORM))).scalars().all()
    assert {row.agent_id for row in rows} == {agent_a.id, agent_b.id}
    assert all(row.estimated_cost_usd > 0 for row in rows)
