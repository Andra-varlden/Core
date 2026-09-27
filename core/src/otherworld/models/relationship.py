"""Plane 5 — Relationships. See About/architecture.md §9.5."""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import JSON, Boolean, Float, Integer
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import CheckConstraint, UniqueConstraint

from otherworld.db import Base

ConflictResolution = Literal["repaired", "broken", "feud"]


class BondState(StrEnum):
    STRANGER = "stranger"
    ACQUAINTANCE = "acquaintance"
    FRIEND = "friend"
    CLOSE_BOND = "close_bond"
    STRAINED = "strained"
    REPAIRED = "repaired"
    BROKEN = "broken"
    FEUD = "feud"


class ConflictTrigger(StrEnum):
    BETRAYAL = "betrayal"
    VALUE_CLASH = "value_clash"
    RESOURCE_COMPETITION = "resource_competition"
    NEGLECT = "neglect"
    CONTAGION = "contagion"


class ConflictRecord(BaseModel):
    """A scar. Permanent. Makes re-escalation on the same theme faster."""

    id: uuid.UUID
    trigger: ConflictTrigger
    theme: str
    severity: float = Field(ge=0.0)
    occurred_tick: int
    resolved_tick: int | None = None
    resolution: ConflictResolution | None = None


class RelationshipEdge(BaseModel):
    id: uuid.UUID
    world_id: uuid.UUID
    agent_a_id: uuid.UUID  # ordered: a_id < b_id, to keep edges unique
    agent_b_id: uuid.UUID
    trust: float = Field(ge=-1.0, le=1.0)
    bond_state: BondState = BondState.STRANGER
    seeded: bool = False
    conflict_log: list[ConflictRecord] = Field(default_factory=list)
    shared_memory_ids: list[uuid.UUID] = Field(default_factory=list)
    contact_count: int = 0
    last_contact_tick: int
    created_tick: int
    # Tick `apply_trust_decay` last subtracted decay at, so the next scan
    # accrues only the time elapsed since then instead of recomputing from
    # the full, ever-growing `ticks_since_last_contact` on every periodic
    # scan (the bug that slammed neglected pairs to trust=-1.0 within one or
    # two scans and pinned them there — About/spec.md §6.3). None until the
    # first decay application, and reset to None on fresh contact.
    last_decay_tick: int | None = None

    @model_validator(mode="after")
    def _ordered_pair(self) -> RelationshipEdge:
        if not (str(self.agent_a_id) < str(self.agent_b_id)):
            raise ValueError("agent_a_id must be < agent_b_id (see About/models/relationship.py)")
        return self


class RelationshipEdgeORM(Base):
    __tablename__ = "relationship_edges"
    __table_args__ = (
        UniqueConstraint("world_id", "agent_a_id", "agent_b_id", name="uq_edge_pair"),
        CheckConstraint("agent_a_id < agent_b_id", name="ck_edge_ordered_pair"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    world_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    agent_a_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    agent_b_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    trust: Mapped[float] = mapped_column(Float, default=0.0)
    bond_state: Mapped[str] = mapped_column(default=BondState.STRANGER.value)
    seeded: Mapped[bool] = mapped_column(Boolean, default=False)
    conflict_log: Mapped[list[Any]] = mapped_column(JSON, default=list)
    shared_memory_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    contact_count: Mapped[int] = mapped_column(Integer, default=0)
    last_contact_tick: Mapped[int] = mapped_column(Integer)
    created_tick: Mapped[int] = mapped_column(Integer)
    last_decay_tick: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)


def edge_to_orm(edge: RelationshipEdge) -> RelationshipEdgeORM:
    return RelationshipEdgeORM(
        id=edge.id,
        world_id=edge.world_id,
        agent_a_id=edge.agent_a_id,
        agent_b_id=edge.agent_b_id,
        trust=edge.trust,
        bond_state=edge.bond_state.value,
        seeded=edge.seeded,
        conflict_log=[c.model_dump(mode="json") for c in edge.conflict_log],
        shared_memory_ids=[str(m) for m in edge.shared_memory_ids],
        contact_count=edge.contact_count,
        last_contact_tick=edge.last_contact_tick,
        created_tick=edge.created_tick,
        last_decay_tick=edge.last_decay_tick,
    )


def edge_from_orm(row: RelationshipEdgeORM) -> RelationshipEdge:
    return RelationshipEdge(
        id=row.id,
        world_id=row.world_id,
        agent_a_id=row.agent_a_id,
        agent_b_id=row.agent_b_id,
        trust=row.trust,
        bond_state=BondState(row.bond_state),
        seeded=row.seeded,
        conflict_log=[ConflictRecord.model_validate(c) for c in row.conflict_log],
        shared_memory_ids=[uuid.UUID(m) for m in row.shared_memory_ids],
        contact_count=row.contact_count,
        last_contact_tick=row.last_contact_tick,
        created_tick=row.created_tick,
        last_decay_tick=row.last_decay_tick,
    )
