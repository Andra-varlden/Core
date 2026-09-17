"""Plane 3 — Memory. See About/architecture.md §9.4."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Float, Index, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from otherworld.db import Base

# [TUNE] Must match the embedding provider chosen in About/spec.md §15.3.
EMBEDDING_DIM = 1536


class MemoryKind(StrEnum):
    EPISODIC = "episodic"
    BELIEF = "belief"


class MemoryRecord(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    kind: MemoryKind
    content: str
    embedding: list[float]
    importance: float = Field(ge=0.0, le=1.0)  # assigned at write, see spec.md §5.1
    tick: int
    subjects: list[uuid.UUID] = Field(default_factory=list)
    source_event_id: uuid.UUID | None = None
    derived_from: list[uuid.UUID] = Field(default_factory=list)  # beliefs: memories synthesised
    # Beliefs only (About/spec.md §8.1, §8.2). hop_count=0 is a belief formed
    # directly (reflection, compression) — never gossiped. valence in
    # [-1, 1], 0.0 for episodics/unassessed beliefs; drives pile-on damping
    # (needs a *negative* inherited belief, About/spec.md §8.2), not just any.
    hop_count: int = 0
    valence: float = Field(0.0, ge=-1.0, le=1.0)
    created_at: datetime


class MemoryRecordORM(Base):
    __tablename__ = "memory_records"
    __table_args__ = (
        # `runtime/retrieval.py`'s bounded candidate-pool queries — one
        # index per (agent, ordering) pair it actually filters+sorts by.
        Index("ix_memory_records_agent_tick", "agent_id", "tick"),
        Index("ix_memory_records_agent_importance", "agent_id", "importance"),
        # `social/gossip.py`'s pile-on check filters by array-contains on
        # `subjects`, across *all* agents (it's a question about who holds a
        # belief about someone, not scoped to one agent's own memories) — a
        # plain btree index can't serve that; GIN can.
        Index("ix_memory_records_subjects_gin", "subjects", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    kind: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(String)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    importance: Mapped[float] = mapped_column(Float)
    tick: Mapped[int] = mapped_column(Integer)
    subjects: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(PGUUID(as_uuid=True)), default=list)
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    derived_from: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(PGUUID(as_uuid=True)), default=list)
    hop_count: Mapped[int] = mapped_column(Integer, default=0)
    valence: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def memory_to_orm(memory: MemoryRecord) -> MemoryRecordORM:
    return MemoryRecordORM(
        id=memory.id,
        agent_id=memory.agent_id,
        kind=memory.kind.value,
        content=memory.content,
        embedding=memory.embedding,
        importance=memory.importance,
        tick=memory.tick,
        subjects=memory.subjects,
        source_event_id=memory.source_event_id,
        derived_from=memory.derived_from,
        hop_count=memory.hop_count,
        valence=memory.valence,
        created_at=memory.created_at,
    )


def memory_from_orm(row: MemoryRecordORM) -> MemoryRecord:
    return MemoryRecord(
        id=row.id,
        agent_id=row.agent_id,
        kind=MemoryKind(row.kind),
        content=row.content,
        embedding=list(row.embedding),
        importance=row.importance,
        tick=row.tick,
        subjects=list(row.subjects),
        source_event_id=row.source_event_id,
        derived_from=list(row.derived_from),
        hop_count=row.hop_count,
        valence=row.valence,
        created_at=row.created_at,
    )
