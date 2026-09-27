"""Plane 2 — Persona. See About/architecture.md §9.2."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import JSON, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from otherworld.db import Base

HumourStyle = Literal["dry", "warm", "absurd", "sarcastic", "none"]
CaptureMethod = Literal["A", "B", "C", "D"]
ClaimedBond = Literal["acquaintance", "friend", "close"]
BoundarySeverity = Literal["block", "block_and_notify"]


class TraitVector(BaseModel):
    """All values 0.0-1.0. See About/spec.md §3 for the meaning of each."""

    loyalty: float = Field(0.5, ge=0.0, le=1.0)
    honesty: float = Field(0.5, ge=0.0, le=1.0)
    risk_tolerance: float = Field(0.5, ge=0.0, le=1.0)
    conflict_directness: float = Field(0.5, ge=0.0, le=1.0)
    forgiveness: float = Field(0.5, ge=0.0, le=1.0)
    grudge_retention: float = Field(0.5, ge=0.0, le=1.0)
    generosity: float = Field(0.5, ge=0.0, le=1.0)
    ambition: float = Field(0.5, ge=0.0, le=1.0)
    sociability: float = Field(0.5, ge=0.0, le=1.0)
    curiosity: float = Field(0.5, ge=0.0, le=1.0)
    independence: float = Field(0.5, ge=0.0, le=1.0)
    emotional_expressiveness: float = Field(0.5, ge=0.0, le=1.0)


class VoiceProfile(BaseModel):
    verbosity: float = Field(ge=0.0, le=1.0)
    formality: float = Field(ge=0.0, le=1.0)
    humour_style: HumourStyle
    profanity_baseline: float = Field(ge=0.0, le=1.0)
    characteristic_phrases: list[str] = Field(default_factory=list)
    diction_notes: str = ""


class SeededRelationship(BaseModel):
    counterpart_owner_id: uuid.UUID
    claimed_bond: ClaimedBond
    mutual_accepted: bool = False  # MUST be True to take effect (ADR-007)
    accepted_at: datetime | None = None
    shared_context: list[str] = Field(default_factory=list)


class BoundaryRule(BaseModel):
    id: uuid.UUID
    description: str
    predicate: str  # compiled matcher expression
    severity: BoundarySeverity


class PersonaObject(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    version: int
    voice: VoiceProfile
    values: TraitVector
    social: list[SeededRelationship] = Field(default_factory=list)
    boundaries: list[BoundaryRule] = Field(default_factory=list)
    source_methods: list[CaptureMethod] = Field(default_factory=list)
    field_confidence: dict[str, float] = Field(default_factory=dict)
    # Method D only (spec.md §2.5) — trained overrides for
    # `persona.compiler.Compiler.compile`'s `decision_weights`, keyed by the
    # same trait names as `values` but populated from observed scenario
    # choices rather than derived from self-reported answers. Only the
    # weights Method D actually has evidence for are present; everything
    # else keeps falling back to `values`.
    decision_weight_overrides: dict[str, float] = Field(default_factory=dict)
    created_at: datetime
    compiled_at: datetime | None = None


class PersonaObjectORM(Base):
    __tablename__ = "persona_objects"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    version: Mapped[int] = mapped_column(Integer)
    voice: Mapped[dict[str, Any]] = mapped_column(JSON)
    values: Mapped[dict[str, Any]] = mapped_column(JSON)
    social: Mapped[list[Any]] = mapped_column(JSON, default=list)
    boundaries: Mapped[list[Any]] = mapped_column(JSON, default=list)
    source_methods: Mapped[list[Any]] = mapped_column(JSON, default=list)
    field_confidence: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    decision_weight_overrides: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    compiled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def persona_to_orm(persona: PersonaObject) -> PersonaObjectORM:
    return PersonaObjectORM(
        id=persona.id,
        owner_id=persona.owner_id,
        version=persona.version,
        voice=persona.voice.model_dump(mode="json"),
        values=persona.values.model_dump(mode="json"),
        social=[s.model_dump(mode="json") for s in persona.social],
        boundaries=[b.model_dump(mode="json") for b in persona.boundaries],
        source_methods=list(persona.source_methods),
        field_confidence=dict(persona.field_confidence),
        decision_weight_overrides=dict(persona.decision_weight_overrides),
        created_at=persona.created_at,
        compiled_at=persona.compiled_at,
    )


def persona_from_orm(row: PersonaObjectORM) -> PersonaObject:
    return PersonaObject(
        id=row.id,
        owner_id=row.owner_id,
        version=row.version,
        voice=VoiceProfile.model_validate(row.voice),
        values=TraitVector.model_validate(row.values),
        social=[SeededRelationship.model_validate(s) for s in row.social],
        boundaries=[BoundaryRule.model_validate(b) for b in row.boundaries],
        source_methods=list(row.source_methods),
        field_confidence=dict(row.field_confidence),
        decision_weight_overrides=dict(row.decision_weight_overrides),
        created_at=row.created_at,
        compiled_at=row.compiled_at,
    )
