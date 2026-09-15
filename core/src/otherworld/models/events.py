"""Actions and events. See About/architecture.md §9.7.

ProposedAction, ValidatedAction and Rejection are runtime-only types — they
never touch the database. Only EventRecord (the append-only output of a
resolved action) is persisted.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from otherworld.db import Base
from otherworld.models.agent import Position

FailedFilter = Literal["boundary", "policy", "real_person", "legality"]


class ActionCategory(StrEnum):
    MOVEMENT = "movement"
    SOCIAL = "social"
    RELATIONAL = "relational"
    MATERIAL = "material"
    INTERNAL = "internal"


class ProposedAction(BaseModel):
    agent_id: uuid.UUID
    action: str  # must exist in the registry
    category: ActionCategory
    targets: list[uuid.UUID] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)
    reasoning: str = ""  # for the trace log, never shown raw to users
    tier_used: Literal[0, 1, 2]


class ValidatedAction(ProposedAction):
    """Only the Validator may construct this type. Invariant I1."""

    validated_at: datetime
    filters_passed: list[str] = Field(default_factory=list)


class Rejection(BaseModel):
    agent_id: uuid.UUID
    proposed: ProposedAction
    failed_filter: FailedFilter
    reason: str


class EventRecord(BaseModel):
    id: uuid.UUID
    world_id: uuid.UUID
    tick: int
    actor_id: uuid.UUID
    action: str
    targets: list[uuid.UUID] = Field(default_factory=list)
    witnesses: list[uuid.UUID] = Field(default_factory=list)
    position: Position
    relationship_deltas: list[dict[str, Any]] = Field(default_factory=list)
    importance: float = Field(ge=0.0, le=1.0)
    owner_override: bool = False  # rendered visibly if True (ADR-006)
    created_at: datetime


class EventRecordORM(Base):
    __tablename__ = "event_records"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    world_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    tick: Mapped[int] = mapped_column(Integer, index=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    action: Mapped[str] = mapped_column(String)
    targets: Mapped[list[str]] = mapped_column(JSON, default=list)
    witnesses: Mapped[list[str]] = mapped_column(JSON, default=list)
    position: Mapped[dict[str, Any]] = mapped_column(JSON)
    relationship_deltas: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    importance: Mapped[float] = mapped_column(Float, index=True)
    owner_override: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def event_to_orm(event: EventRecord) -> EventRecordORM:
    return EventRecordORM(
        id=event.id,
        world_id=event.world_id,
        tick=event.tick,
        actor_id=event.actor_id,
        action=event.action,
        targets=[str(t) for t in event.targets],
        witnesses=[str(w) for w in event.witnesses],
        position=event.position.model_dump(mode="json"),
        relationship_deltas=event.relationship_deltas,
        importance=event.importance,
        owner_override=event.owner_override,
        created_at=event.created_at,
    )


def event_from_orm(row: EventRecordORM) -> EventRecord:
    return EventRecord(
        id=row.id,
        world_id=row.world_id,
        tick=row.tick,
        actor_id=row.actor_id,
        action=row.action,
        targets=[uuid.UUID(t) for t in row.targets],
        witnesses=[uuid.UUID(w) for w in row.witnesses],
        position=Position.model_validate(row.position),
        relationship_deltas=row.relationship_deltas,
        importance=row.importance,
        owner_override=row.owner_override,
        created_at=row.created_at,
    )
