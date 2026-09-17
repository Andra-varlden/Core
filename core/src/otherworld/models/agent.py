"""Plane 3 — Agent. See About/architecture.md §9.3."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from otherworld.db import Base

Facing = Literal["n", "s", "e", "w"]
GoalOrigin = Literal["seeded", "self", "adopted"]


class AgentStatus(StrEnum):
    ACTIVE = "active"
    BACKGROUND = "background"  # lapsed owner, reduced tick rate
    RECALLED = "recalled"
    SUSPENDED = "suspended"


class Position(BaseModel):
    x: int
    y: int
    facing: Facing = "s"


class Goal(BaseModel):
    id: uuid.UUID
    description: str
    priority: float
    origin: GoalOrigin
    adopted_from_agent_id: uuid.UUID | None = None
    created_tick: int
    completed_tick: int | None = None


class Agent(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    persona_version: int
    world_id: uuid.UUID
    display_name: str
    status: AgentStatus = AgentStatus.ACTIVE
    position: Position
    goals: list[Goal] = Field(default_factory=list)
    current_path: list[tuple[int, int]] = Field(default_factory=list)
    last_tick: int = 0
    last_reflection_tick: int = 0
    created_at: datetime


class AgentORM(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    persona_version: Mapped[int] = mapped_column(Integer)
    world_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    display_name: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default=AgentStatus.ACTIVE.value)
    position: Mapped[dict[str, Any]] = mapped_column(JSON)
    goals: Mapped[list[Any]] = mapped_column(JSON, default=list)
    current_path: Mapped[list[Any]] = mapped_column(JSON, default=list)
    last_tick: Mapped[int] = mapped_column(Integer, default=0)
    last_reflection_tick: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def agent_to_orm(agent: Agent) -> AgentORM:
    return AgentORM(
        id=agent.id,
        owner_id=agent.owner_id,
        persona_version=agent.persona_version,
        world_id=agent.world_id,
        display_name=agent.display_name,
        status=agent.status.value,
        position=agent.position.model_dump(mode="json"),
        goals=[g.model_dump(mode="json") for g in agent.goals],
        current_path=[list(p) for p in agent.current_path],
        last_tick=agent.last_tick,
        last_reflection_tick=agent.last_reflection_tick,
        created_at=agent.created_at,
    )


def agent_from_orm(row: AgentORM) -> Agent:
    return Agent(
        id=row.id,
        owner_id=row.owner_id,
        persona_version=row.persona_version,
        world_id=row.world_id,
        display_name=row.display_name,
        status=AgentStatus(row.status),
        position=Position.model_validate(row.position),
        goals=[Goal.model_validate(g) for g in row.goals],
        current_path=[tuple(p) for p in row.current_path],
        last_tick=row.last_tick,
        last_reflection_tick=row.last_reflection_tick,
        created_at=row.created_at,
    )
