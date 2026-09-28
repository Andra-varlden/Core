"""Agent creation. See About/plan.md M6 T6.3 — this is the one real,
consent-gated path a signed-in owner spawns an agent through. `cli.run_world`
and its `_get_or_spawn_agent` remain dev/test-only tools that use the
placeholder consent record (`owner.service.get_or_create_owner`); this
endpoint is what actually enforces the gate for a real person.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from otherworld.api.deps import get_current_owner
from otherworld.db import get_session
from otherworld.models.agent import agent_to_orm
from otherworld.models.owner import Owner
from otherworld.models.world import WorldORM
from otherworld.owner.service import ConsentRequiredError, require_consent
from otherworld.persona.binder import Binder
from otherworld.persona.compiler import Compiler
from otherworld.persona.service import get_latest_persona
from otherworld.runtime.clock import tick_to_datetime

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


class CreateAgentBody(BaseModel):
    world_id: uuid.UUID
    display_name: str


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_agent(
    body: CreateAgentBody,
    owner: Owner = Depends(get_current_owner),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    try:
        require_consent(owner)
    except ConsentRequiredError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc

    persona = await get_latest_persona(session, owner.id)
    if persona is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "capture a persona before spawning an agent")

    world_row = await session.get(WorldORM, body.world_id)
    if world_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such world")

    bundle = Compiler.compile(persona)
    agent = Binder.bind(
        bundle, owner_id=owner.id, persona_version=persona.version, world_id=body.world_id,
        display_name=body.display_name, spawned_at=tick_to_datetime(world_row.current_tick),
    )
    session.add(agent_to_orm(agent))
    await session.commit()
    return {"agent_id": str(agent.id)}
