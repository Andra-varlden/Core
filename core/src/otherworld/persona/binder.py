"""The binder. See About/architecture.md §3.

Attaches a compiled `AgentBundle` to a spawnable `Agent` row. This is the
step ADR-002 calls out as where containment is "applied": the agent's only
callable surface from here on is `ActionRegistry`, enforced downstream by
the Validator's world-legality filter (safety/validator.py) — the binder
itself does no capability wiring, because there is no capability to wire.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from otherworld.models.agent import Agent, AgentStatus, Position
from otherworld.persona.compiler import AgentBundle


class Binder:
    @staticmethod
    def bind(
        bundle: AgentBundle,
        owner_id: uuid.UUID,
        persona_version: int,
        world_id: uuid.UUID,
        display_name: str,
        spawned_at: datetime,
        spawn_position: Position | None = None,
    ) -> Agent:
        # bundle itself is not stored on Agent — it is recompiled from
        # persona_version whenever a decision needs it (architecture §3).
        return Agent(
            id=uuid.uuid4(),
            owner_id=owner_id,
            persona_version=persona_version,
            world_id=world_id,
            display_name=display_name,
            status=AgentStatus.ACTIVE,
            position=spawn_position or Position(x=0, y=0, facing="s"),
            goals=[],
            current_path=[],
            last_tick=0,
            created_at=spawned_at,
        )
