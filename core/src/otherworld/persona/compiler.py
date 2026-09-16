"""The persona compiler. See About/architecture.md §3.

Turns an immutable `PersonaObject` into an `AgentBundle` — the prompt text
and decision weights a running agent actually uses. Not persisted: an
`Agent` row stores only `persona_version`, so the bundle is recompiled from
the versioned `PersonaObject` whenever needed (About/architecture.md §3
versioning rule — this is what keeps persona edits forward-only without
rewriting history, invariant I5).
"""

from __future__ import annotations

from pydantic import BaseModel

from otherworld.models.persona import BoundaryRule, PersonaObject
from otherworld.safety.registry import REGISTRY_VERSION

# [TUNE] Traits above this seed an initial goal description. Real goal
# *objects* (with id/tick/priority) require the GoalStack service, which is
# M5 scope — these are just seed text for that service to pick up later.
_GOAL_SEED_THRESHOLD = 0.6


class AgentBundle(BaseModel):
    identity_prompt: str
    decision_weights: dict[str, float]
    initial_goals: list[str]
    boundary_ruleset: list[BoundaryRule]
    action_space_ref: str


def _identity_prompt(persona: PersonaObject) -> str:
    voice = persona.voice
    verbosity_word = "high" if voice.verbosity > 0.6 else "low" if voice.verbosity < 0.4 else "moderate"
    if voice.profanity_baseline > 0.6:
        profanity_word = "frequent"
    elif voice.profanity_baseline > 0.3:
        profanity_word = "occasional"
    else:
        profanity_word = "rare"
    lines = [
        f"You speak with {voice.humour_style} humour, {verbosity_word} verbosity, "
        f"and {profanity_word} profanity.",
    ]
    if voice.characteristic_phrases:
        lines.append(f"You often say things like: {', '.join(voice.characteristic_phrases)}.")
    if persona.boundaries:
        lines.append(
            "You will never: " + "; ".join(b.description for b in persona.boundaries) + "."
        )
    return " ".join(lines)


def _initial_goals(persona: PersonaObject) -> list[str]:
    goals = []
    if persona.values.ambition >= _GOAL_SEED_THRESHOLD:
        goals.append("Work toward something of your own.")
    if persona.values.curiosity >= _GOAL_SEED_THRESHOLD:
        goals.append("Learn about the people and places around you.")
    return goals


class Compiler:
    @staticmethod
    def compile(persona: PersonaObject) -> AgentBundle:
        return AgentBundle(
            identity_prompt=_identity_prompt(persona),
            decision_weights=persona.values.model_dump(),
            initial_goals=_initial_goals(persona),
            boundary_ruleset=list(persona.boundaries),
            action_space_ref=REGISTRY_VERSION,
        )
