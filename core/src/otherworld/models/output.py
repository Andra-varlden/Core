"""Plane 6 — Output. See About/architecture.md §9.8."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import JSON, DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from otherworld.db import Base
from otherworld.models.owner import VisibilityScope


class Highlight(BaseModel):
    id: uuid.UUID
    world_id: uuid.UUID
    event_ids: list[uuid.UUID] = Field(default_factory=list)
    arc_id: uuid.UUID | None = None  # groups highlights into a storyline
    narration: str
    importance: float = Field(ge=0.0, le=1.0)
    participants: list[uuid.UUID] = Field(default_factory=list)
    visibility: VisibilityScope
    created_at: datetime


class RecognitionTrial(BaseModel):
    """One run of the core validation test. See About/spec.md §14."""

    id: uuid.UUID
    owner_id: uuid.UUID
    own_agent_action_ids: list[uuid.UUID] = Field(default_factory=list)
    decoy_action_ids: list[uuid.UUID] = Field(default_factory=list)
    owner_selections: list[uuid.UUID] = Field(default_factory=list)
    accuracy: float = Field(ge=0.0, le=1.0)
    run_at: datetime
    persona_version: int


class HighlightORM(Base):
    __tablename__ = "highlights"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    world_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    event_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    arc_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    narration: Mapped[str] = mapped_column(String)
    importance: Mapped[float] = mapped_column(Float)
    participants: Mapped[list[str]] = mapped_column(JSON, default=list)
    visibility: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RecognitionTrialORM(Base):
    __tablename__ = "recognition_trials"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    own_agent_action_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    decoy_action_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    owner_selections: Mapped[list[str]] = mapped_column(JSON, default=list)
    accuracy: Mapped[float] = mapped_column(Float)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    persona_version: Mapped[int] = mapped_column(Integer)


def highlight_to_orm(h: Highlight) -> HighlightORM:
    return HighlightORM(
        id=h.id,
        world_id=h.world_id,
        event_ids=[str(e) for e in h.event_ids],
        arc_id=h.arc_id,
        narration=h.narration,
        importance=h.importance,
        participants=[str(p) for p in h.participants],
        visibility=h.visibility.value,
        created_at=h.created_at,
    )


def highlight_from_orm(row: HighlightORM) -> Highlight:
    return Highlight(
        id=row.id,
        world_id=row.world_id,
        event_ids=[uuid.UUID(e) for e in row.event_ids],
        arc_id=row.arc_id,
        narration=row.narration,
        importance=row.importance,
        participants=[uuid.UUID(p) for p in row.participants],
        visibility=VisibilityScope(row.visibility),
        created_at=row.created_at,
    )


def recognition_trial_to_orm(t: RecognitionTrial) -> RecognitionTrialORM:
    return RecognitionTrialORM(
        id=t.id,
        owner_id=t.owner_id,
        own_agent_action_ids=[str(a) for a in t.own_agent_action_ids],
        decoy_action_ids=[str(a) for a in t.decoy_action_ids],
        owner_selections=[str(a) for a in t.owner_selections],
        accuracy=t.accuracy,
        run_at=t.run_at,
        persona_version=t.persona_version,
    )


def recognition_trial_from_orm(row: RecognitionTrialORM) -> RecognitionTrial:
    return RecognitionTrial(
        id=row.id,
        owner_id=row.owner_id,
        own_agent_action_ids=[uuid.UUID(a) for a in row.own_agent_action_ids],
        decoy_action_ids=[uuid.UUID(a) for a in row.decoy_action_ids],
        owner_selections=[uuid.UUID(a) for a in row.owner_selections],
        accuracy=row.accuracy,
        run_at=row.run_at,
        persona_version=row.persona_version,
    )
