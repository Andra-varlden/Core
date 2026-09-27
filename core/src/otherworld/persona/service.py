"""Assembling and persisting `PersonaObject`s from capture results.

See About/architecture.md §3: "Later methods refine earlier values rather
than replacing them; each field records its source_method and confidence."
And invariant I5: `PersonaObject` is immutable once created — an edit always
creates version n+1, never mutates version n.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from otherworld.models.persona import (
    BoundaryRule,
    PersonaObject,
    PersonaObjectORM,
    TraitVector,
    VoiceProfile,
    persona_to_orm,
)
from otherworld.persona.boundaries import compile_free_text_boundary, default_boundaries
from otherworld.persona.capture.interview import INTERVIEW_PROMPTS, InterviewResult
from otherworld.persona.capture.questionnaire import TRAIT_ITEMS, QuestionnaireResult
from otherworld.persona.capture.scenario import ScenarioReplayResult
from otherworld.persona.scoring import TRAIT_NAMES, clamp01

_QUESTIONNAIRE_CONFIDENCE_ANSWERED = 0.8
# Not 0.5: an unanswered trait is zero evidence, not weak evidence — see the
# matching note on interview.py's score_interview for why this distinction
# matters once a persona is merged across capture methods.
_QUESTIONNAIRE_CONFIDENCE_DEFAULT = 0.0


def questionnaire_field_confidence(answers: dict[str, str]) -> dict[str, float]:
    answered_traits: set[str] = set()
    for item in TRAIT_ITEMS:
        option = answers.get(item.id)
        if option is not None:
            answered_traits.update(item.effects.get(option, {}).keys())
    return {
        trait: (
            _QUESTIONNAIRE_CONFIDENCE_ANSWERED
            if trait in answered_traits
            else _QUESTIONNAIRE_CONFIDENCE_DEFAULT
        )
        for trait in TraitVector.model_fields
    }


def build_persona_from_questionnaire(
    owner_id: uuid.UUID,
    answers: dict[str, str],
    result: QuestionnaireResult,
    enabled_boundaries: set[str] | None = None,
) -> PersonaObject:
    """Method A end to end (T1.1): a full PersonaObject, version 1."""
    boundaries: list[BoundaryRule] = default_boundaries(enabled_boundaries)
    if result.boundary_text:
        boundaries.append(compile_free_text_boundary(result.boundary_text))

    return PersonaObject(
        id=uuid.uuid4(),
        owner_id=owner_id,
        version=1,
        voice=VoiceProfile(
            characteristic_phrases=phrases_from_free_text(result.free_text),
            diction_notes=result.free_text.get("A25", ""),
            **result.voice_kwargs,
        ),
        values=TraitVector(**result.trait_scores),
        social=[],
        boundaries=boundaries,
        source_methods=["A"],
        field_confidence=questionnaire_field_confidence(answers),
        created_at=datetime.now(UTC),
        compiled_at=None,
    )


def _interview_field_confidence(result: InterviewResult) -> dict[str, float]:
    return dict(result.confidences)


def build_persona_from_interview(
    owner_id: uuid.UUID,
    result: InterviewResult,
    enabled_boundaries: set[str] | None = None,
) -> PersonaObject:
    """Method B end to end (T1.2): a full PersonaObject, version 1."""
    boundaries: list[BoundaryRule] = default_boundaries(enabled_boundaries)
    if result.boundary_text:
        boundaries.append(compile_free_text_boundary(result.boundary_text))

    return PersonaObject(
        id=uuid.uuid4(),
        owner_id=owner_id,
        version=1,
        voice=VoiceProfile(
            characteristic_phrases=[],
            diction_notes=result.free_text.get(INTERVIEW_PROMPTS[0].id, ""),
            **result.voice_kwargs,
        ),
        values=TraitVector(**result.trait_scores),
        social=[],
        boundaries=boundaries,
        source_methods=["B"],
        field_confidence=_interview_field_confidence(result),
        created_at=datetime.now(UTC),
        compiled_at=None,
    )


def phrases_from_free_text(free_text: dict[str, str]) -> list[str]:
    phrase = free_text.get("A27", "").strip()
    return [phrase] if phrase else []


def apply_writing_sample(persona: PersonaObject, voice_kwargs: dict[str, object]) -> PersonaObject:
    """Method C refines the voice layer only (spec.md §2.4) and bumps the
    version, per the same-owner append-only field_confidence rule.
    """
    merged_confidence = dict(persona.field_confidence)
    for field_name in ("verbosity", "formality", "humour_style", "profanity_baseline"):
        merged_confidence[f"voice.{field_name}"] = 0.7

    return persona.model_copy(
        update={
            "id": uuid.uuid4(),
            "version": persona.version + 1,
            "voice": persona.voice.model_copy(update=voice_kwargs),
            "source_methods": [*persona.source_methods, "C"],
            "field_confidence": merged_confidence,
            "created_at": datetime.now(UTC),
        }
    )


def apply_scenario_replay(persona: PersonaObject, result: ScenarioReplayResult) -> PersonaObject:
    """Method D refines `decision_weight_overrides` only (spec.md §2.5) and
    bumps the version, per the same-owner append-only field_confidence
    rule. Each touched weight is a confidence-weighted blend with any
    existing override — same formula as `merge_capture_into_persona`'s
    trait blending, so re-running Method D later refines rather than
    overwrites. Confidence for an override is tracked under
    `field_confidence["decision_weight.<trait>"]`, parallel to how
    `apply_writing_sample` tracks voice-field confidence under
    `"voice.<field>"`.
    """
    merged_overrides = dict(persona.decision_weight_overrides)
    merged_confidence = dict(persona.field_confidence)
    for trait, new_value in result.decision_weight_overrides.items():
        key = f"decision_weight.{trait}"
        old_value = merged_overrides.get(trait)
        new_confidence = result.confidences.get(trait, 0.0)
        if old_value is None:
            merged_overrides[trait] = new_value
            merged_confidence[key] = new_confidence
            continue
        old_confidence = merged_confidence.get(key, 0.0)
        total_confidence = old_confidence + new_confidence
        merged_overrides[trait] = (
            (old_value * old_confidence + new_value * new_confidence) / total_confidence
            if total_confidence > 0
            else new_value
        )
        merged_confidence[key] = clamp01(1 - (1 - old_confidence) * (1 - new_confidence))

    return persona.model_copy(
        update={
            "id": uuid.uuid4(),
            "version": persona.version + 1,
            "decision_weight_overrides": merged_overrides,
            "source_methods": [*persona.source_methods, "D"],
            "field_confidence": merged_confidence,
            "created_at": datetime.now(UTC),
        }
    )


def merge_capture_into_persona(
    existing: PersonaObject,
    trait_scores: dict[str, float],
    confidences: dict[str, float],
    voice_updates: dict[str, object],
    boundary_text: str | None,
    enabled_boundaries: set[str] | None,
    source_method: str,
) -> dict[str, object]:
    """Field updates (for `edit_persona`) that fold a new capture into an
    existing persona, per About/architecture.md §3: "Later methods refine
    earlier values rather than replacing them."

    Each trait becomes a confidence-weighted average of the old and new
    reading; confidence itself combines as `1 - (1-old)(1-new)` (more
    independent evidence should never lower confidence). Boundaries union
    by description rather than duplicating. Voice fields are overwritten by
    the new capture — unlike traits, there is no principled way to average
    "dry" and "sarcastic" humour styles, so the most recent read wins.
    """
    merged_values: dict[str, float] = {}
    merged_confidence = dict(existing.field_confidence)
    for trait in TRAIT_NAMES:
        old_value = getattr(existing.values, trait)
        old_confidence = existing.field_confidence.get(trait, 0.5)
        new_value = trait_scores[trait]
        new_confidence = confidences[trait]
        total_confidence = old_confidence + new_confidence
        merged_values[trait] = (
            (old_value * old_confidence + new_value * new_confidence) / total_confidence
            if total_confidence > 0
            else 0.5
        )
        merged_confidence[trait] = clamp01(1 - (1 - old_confidence) * (1 - new_confidence))

    boundaries = list(existing.boundaries)
    seen_descriptions = {b.description for b in boundaries}
    for rule in default_boundaries(enabled_boundaries):
        if rule.description not in seen_descriptions:
            boundaries.append(rule)
            seen_descriptions.add(rule.description)
    if boundary_text:
        new_rule = compile_free_text_boundary(boundary_text)
        if new_rule.description not in seen_descriptions:
            boundaries.append(new_rule)

    return {
        "values": TraitVector(**merged_values),
        "voice": existing.voice.model_copy(update=voice_updates),
        "boundaries": boundaries,
        "source_methods": [*existing.source_methods, source_method],
        "field_confidence": merged_confidence,
    }


async def get_latest_persona(session: AsyncSession, owner_id: uuid.UUID) -> PersonaObject | None:
    from sqlalchemy import select

    from otherworld.models.persona import persona_from_orm

    row = (
        await session.execute(
            select(PersonaObjectORM)
            .where(PersonaObjectORM.owner_id == owner_id)
            .order_by(PersonaObjectORM.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return persona_from_orm(row) if row else None


async def save_persona(session: AsyncSession, persona: PersonaObject) -> None:
    session.add(persona_to_orm(persona))
    await session.flush()


async def edit_persona(
    session: AsyncSession, current: PersonaObject, **field_updates: object
) -> PersonaObject:
    """Create version n+1. `current` (version n) is left untouched in the
    database — invariant I5, tested by T1.6.
    """
    updated = current.model_copy(
        update={
            "id": uuid.uuid4(),
            "version": current.version + 1,
            "created_at": datetime.now(UTC),
            **field_updates,
        }
    )
    await save_persona(session, updated)
    return updated


async def get_persona_version(
    session: AsyncSession, owner_id: uuid.UUID, version: int
) -> PersonaObject | None:
    from sqlalchemy import select

    from otherworld.models.persona import persona_from_orm

    row = (
        await session.execute(
            select(PersonaObjectORM).where(
                PersonaObjectORM.owner_id == owner_id, PersonaObjectORM.version == version
            )
        )
    ).scalar_one_or_none()
    return persona_from_orm(row) if row else None
