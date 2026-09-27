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

from otherworld.models.persona import BoundaryRule, PersonaObject, TraitVector
from otherworld.safety.registry import REGISTRY_VERSION

# [TUNE] Traits above this seed an initial goal description. Real goal
# *objects* (with id/tick/priority) require the GoalStack service, which is
# M5 scope — these are just seed text for that service to pick up later.
_GOAL_SEED_THRESHOLD = 0.6

# spec.md §3's own "Low expression / High expression" table for each
# trait — reused verbatim (adapted to "you..." phrasing) rather than
# invented, so the identity prompt describes the same behavioural model the
# mechanics (trust deltas, conflict thresholds, goal formation) already
# encode. Found missing entirely during the M4 real trial's recognition
# post-mortem: `_identity_prompt` only ever surfaced voice tone (verbosity/
# profanity/humour) and the boundary list — every one of these 12 traits
# was compiled into `decision_weights` and used purely as background math,
# but the text a real model actually reads never mentioned them. All 5 real
# people's compiled prompts came out nearly identical as a result ("You
# speak with none humour, low verbosity, and rare profanity...") — the
# model had almost nothing personalised to improvise from, which is a much
# more fundamental cause of weak/failed recognition scores than anything in
# the quiz itself.
_TRAIT_PHRASES: dict[str, tuple[str, str]] = {
    "loyalty": ("you side with whoever's actually right, even against your own people",
                "you side with your own people no matter what"),
    "honesty": ("you say what's expedient more than what's strictly true",
                "you say what's true, bluntly, even when it's unwelcome"),
    "risk_tolerance": ("you avoid exposing yourself to real risk",
                        "you seek the upside even when you could lose something"),
    "conflict_directness": ("you withdraw rather than confront a conflict",
                             "you confront conflict immediately, head-on"),
    "forgiveness": ("you rarely repair a rift once it's happened",
                     "you repair rifts readily"),
    "grudge_retention": ("you forget grievances quickly",
                          "you hold onto grudges indefinitely"),
    "generosity": ("you keep what's yours",
                    "you give unprompted, without being asked"),
    "ambition": ("you rarely set goals for yourself",
                 "you're constantly forming your own goals"),
    "sociability": ("you avoid others",
                     "you seek out contact with others constantly"),
    "curiosity": ("you ignore what's unfamiliar to you",
                   "you investigate anything unfamiliar"),
    "independence": ("you tend to adopt others' goals as your own",
                       "you pursue your own path regardless of others"),
    "emotional_expressiveness": ("you show nothing of what you feel",
                                   "you show everything you feel"),
}
_TRAIT_HIGH_THRESHOLD = 0.65
_TRAIT_LOW_THRESHOLD = 0.35


def _trait_clauses(values: TraitVector) -> list[str]:
    """Only genuinely distinctive traits (clearly above/below the 0.5
    default) get surfaced — a trait sitting near-neutral carries little
    real signal and would just bloat the prompt without adding anything
    a model could act on differently.
    """
    clauses = []
    for trait, (low_phrase, high_phrase) in _TRAIT_PHRASES.items():
        value = getattr(values, trait)
        if value >= _TRAIT_HIGH_THRESHOLD:
            clauses.append(high_phrase)
        elif value <= _TRAIT_LOW_THRESHOLD:
            clauses.append(low_phrase)
    return clauses


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
    lines = []
    trait_clauses = _trait_clauses(persona.values)
    if trait_clauses:
        lines.append("You are someone who: " + "; ".join(trait_clauses) + ".")
    lines.append(
        f"You speak with {voice.humour_style} humour, {verbosity_word} verbosity, "
        f"and {profanity_word} profanity."
    )
    # `voice.diction_notes` is deliberately NOT surfaced here — checked its
    # real content during the M4 identity-prompt fix and found it's the
    # RAW, verbatim answer to capture's A25 ("describe a disagreement you
    # had and how it ended"), not the extracted "diction/conflict narrative
    # style" spec.md §2.2 actually calls for. `capture/interview.py`'s own
    # docstring confirms extraction is a deterministic keyword matcher, not
    # an LLM step — nothing has ever actually summarised this field. Piping
    # it straight into a prompt sent to a third-party model would mean
    # unvetted personal narratives (one real answer literally states intent
    # to "harm in a physical way") land verbatim in a live LLM call. Needs a
    # real extraction step before this field is safe to use for anything.
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
        # Method D's trained overrides win where they disagree with the
        # trait-derived defaults (About/spec.md §2.5) — everything Method D
        # has no evidence for just falls through to `values` unchanged.
        decision_weights = {**persona.values.model_dump(), **persona.decision_weight_overrides}
        return AgentBundle(
            identity_prompt=_identity_prompt(persona),
            decision_weights=decision_weights,
            initial_goals=_initial_goals(persona),
            boundary_ruleset=list(persona.boundaries),
            action_space_ref=REGISTRY_VERSION,
        )
