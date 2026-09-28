"""Persona capture routes — Method A (questionnaire) and Method B
(interview), over HTTP. See About/plan.md M6 T6.6: "A non-technical person
completes method B unaided." Before this, the only driver for either method
was `cli.capture`'s blocking `input()` prompts — usable by whoever is
sitting at the terminal, not by a real person following a link.

Both methods reuse the exact scoring/build logic `cli.capture` already
proved out (`persona.capture.questionnaire`, `persona.capture.interview`,
`persona.service`) — this module only adds the HTTP surface: list the items/
prompts as data the frontend can render, accept a single all-answers
submission (matching how `cli.capture.run_questionnaire`/`run_interview`
already collect everything before scoring), and save.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from otherworld.api.deps import get_current_owner
from otherworld.db import get_session
from otherworld.models.owner import Owner
from otherworld.models.persona import PersonaObject
from otherworld.persona.boundaries import DEFAULT_BOUNDARY_TOGGLES
from otherworld.persona.capture.interview import ALL_PROMPTS, score_interview
from otherworld.persona.capture.questionnaire import TRAIT_ITEMS, score_questionnaire
from otherworld.persona.service import (
    build_persona_from_interview,
    build_persona_from_questionnaire,
    edit_persona,
    get_latest_persona,
    merge_capture_into_persona,
    phrases_from_free_text,
    questionnaire_field_confidence,
    save_persona,
)

router = APIRouter(prefix="/api/v1/persona", tags=["persona"])

# Only the toggles actually offered — "no romance" and "no violence" are
# always on platform-wide (persona.boundaries.default_boundaries) and never
# shown as a choice, matching cli.capture's OPTIONAL_BOUNDARY_KEYS.
_OPTIONAL_BOUNDARY_KEYS = [k for k in DEFAULT_BOUNDARY_TOGGLES if k not in ("no_romance", "no_violence")]

_FREE_TEXT_PROMPTS = {
    "A25": "Describe a disagreement you had and how it ended, in your own words.",
    "A26": "Describe a friend of yours without naming them.",
    "A27": "What's something you say a lot?",
    "A28": "Describe your ideal day, hour by hour.",
    "A29": "What would you never do, no matter what? (this becomes a hard boundary)",
    "A30": "What do people misunderstand about you?",
}

_A21_OPTIONS = {"a": "dry", "b": "warm", "c": "absurd", "d": "sarcastic", "e": "not funny"}
_A22_OPTIONS = {
    "a": "talk most", "b": "talk about equally", "c": "listen more", "d": "listen almost entirely"
}
_A23_OPTIONS = {"a": "constantly", "b": "when it fits", "c": "rarely", "d": "never"}
_A24_OPTIONS = {"a": "long", "b": "a few sentences", "c": "one line", "d": "a word or two"}


def _boundary_options() -> list[dict[str, str]]:
    return [{"key": k, "description": DEFAULT_BOUNDARY_TOGGLES[k][0]} for k in _OPTIONAL_BOUNDARY_KEYS]


def _persona_summary(persona: PersonaObject) -> dict[str, object]:
    return {
        "id": str(persona.id),
        "version": persona.version,
        "source_methods": persona.source_methods,
        "values": persona.values.model_dump(),
        "voice": persona.voice.model_dump(),
        "boundaries": [
            {"description": rule.description, "severity": rule.severity} for rule in persona.boundaries
        ],
    }


@router.get("/me")
async def get_my_persona(
    owner: Owner = Depends(get_current_owner), session: AsyncSession = Depends(get_session)
) -> dict[str, object] | None:
    persona = await get_latest_persona(session, owner.id)
    return _persona_summary(persona) if persona else None


@router.get("/method-a/items")
async def method_a_items() -> dict[str, object]:
    return {
        "choice_items": [
            {"id": item.id, "prompt": item.prompt, "options": item.options} for item in TRAIT_ITEMS
        ]
        + [
            {"id": "A21", "prompt": "Your humour is mostly:", "options": _A21_OPTIONS},
            {"id": "A22", "prompt": "In a conversation you typically:", "options": _A22_OPTIONS},
            {"id": "A23", "prompt": "You swear:", "options": _A23_OPTIONS},
            {"id": "A24", "prompt": "Your messages are usually:", "options": _A24_OPTIONS},
        ],
        "free_text_items": [
            {"id": item_id, "prompt": prompt} for item_id, prompt in _FREE_TEXT_PROMPTS.items()
        ],
        "boundary_options": _boundary_options(),
    }


class MethodABody(BaseModel):
    answers: dict[str, str]
    free_text: dict[str, str] = {}
    enabled_boundaries: list[str] = []


@router.post("/method-a")
async def submit_method_a(
    body: MethodABody,
    owner: Owner = Depends(get_current_owner),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    result = score_questionnaire(body.answers, body.free_text)
    enabled = {k for k in body.enabled_boundaries if k in DEFAULT_BOUNDARY_TOGGLES}
    existing = await get_latest_persona(session, owner.id)

    if existing is None:
        persona = build_persona_from_questionnaire(owner.id, body.answers, result, enabled)
        await save_persona(session, persona)
    else:
        voice_updates = {
            **result.voice_kwargs,
            "characteristic_phrases": phrases_from_free_text(result.free_text),
            "diction_notes": result.free_text.get("A25", ""),
        }
        updates = merge_capture_into_persona(
            existing,
            result.trait_scores,
            questionnaire_field_confidence(body.answers),
            voice_updates,
            result.boundary_text,
            enabled,
            "A",
        )
        persona = await edit_persona(session, existing, **updates)

    await session.commit()
    return _persona_summary(persona)


@router.get("/method-b/prompts")
async def method_b_prompts() -> dict[str, object]:
    return {
        "prompts": [{"id": p.id, "prompt": p.prompt} for p in ALL_PROMPTS],
        "boundary_options": _boundary_options(),
    }


class MethodBBody(BaseModel):
    answers: dict[str, str]
    enabled_boundaries: list[str] = []


@router.post("/method-b")
async def submit_method_b(
    body: MethodBBody,
    owner: Owner = Depends(get_current_owner),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    result = score_interview(body.answers)
    enabled = {k for k in body.enabled_boundaries if k in DEFAULT_BOUNDARY_TOGGLES}
    existing = await get_latest_persona(session, owner.id)

    if existing is None:
        persona = build_persona_from_interview(owner.id, result, enabled)
        await save_persona(session, persona)
    else:
        voice_updates = {**result.voice_kwargs, "diction_notes": result.free_text.get(ALL_PROMPTS[0].id, "")}
        updates = merge_capture_into_persona(
            existing, result.trait_scores, result.confidences, voice_updates,
            result.boundary_text, enabled, "B",
        )
        persona = await edit_persona(session, existing, **updates)

    await session.commit()
    return _persona_summary(persona)
