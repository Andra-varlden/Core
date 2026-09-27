"""Method D — scenario replay. See About/spec.md §2.5.

"10-15 in-world scenarios rendered as the agent would face them. Owner
selects the action they would take from the actual action registry. [...]
Output: `decision_weights` that override trait-derived defaults where they
disagree."

Unlike Methods A/B/C (which produce `TraitVector` scores merged by
`persona/service.py`'s confidence-weighted average), this produces
`decision_weight_overrides` directly — the same keys `persona/compiler.py`
already reads via `AgentBundle.decision_weights`, but recorded as trained,
observed choices rather than derived from self-reported trait answers.
That's the point spec.md makes calling this "the highest-signal method":
it trains the decision policy directly instead of describing it.

Deliberately built now, ahead of spec.md's own "Phase 2+" placement note
for this method — the interpretation table in the same document (§14)
explicitly calls for adding Method D specifically when a real Recognition
Metric trial comes back "weak" (56-69%), which is what happened during
the M4 real trial (About/plan.md, 2026-09-18). Those two lines in spec.md
disagree with each other on timing; a weak result is the one case the
table itself says to pull it forward for.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from otherworld.persona.scoring import TRAIT_NAMES, clamp01
from otherworld.safety.registry import ActionRegistry

# Same convention as questionnaire.py's TRAIT_SCALE — how strongly a fully
# consistent set of choices pulls a weight away from the neutral 0.5
# default. Kept identical so a Method D override and a Method A/B trait
# score are on a comparable scale before persona/service.py blends them.
WEIGHT_SCALE = 0.35


@dataclass(frozen=True)
class ScenarioItem:
    id: str
    prompt: str
    # option key -> (action name from the real registry, short framing)
    options: dict[str, tuple[str, str]]
    effects: dict[str, dict[str, float]] = field(default_factory=dict)


SCENARIOS: tuple[ScenarioItem, ...] = (
    ScenarioItem(
        "D1", "Someone you've never met greets you first in a new place.",
        {"a": ("greet", "greet them back warmly"), "b": ("speak_to", "respond, but keep it brief"),
         "c": ("ignore", "avoid engaging")},
        {"a": {"sociability": 1.0}, "b": {"sociability": 0.0}, "c": {"sociability": -1.0}},
    ),
    ScenarioItem(
        "D2", "Someone in your group criticises you unfairly, in front of others.",
        {"a": ("criticise", "push back hard, right there"),
         "b": ("apologise", "de-escalate even though you disagree"),
         "c": ("reject", "cut them off and walk away")},
        {"a": {"conflict_directness": 1.0, "emotional_expressiveness": 0.5},
         "b": {"conflict_directness": -1.0, "honesty": -0.5},
         "c": {"conflict_directness": 0.3, "sociability": -0.5}},
    ),
    ScenarioItem(
        "D3", "A friend breaks a promise to you for the second time.",
        {"a": ("forgive", "let it go, they're still your friend"),
         "b": ("criticise", "tell them plainly it's not okay"),
         "c": ("reject", "distance yourself from them")},
        {"a": {"forgiveness": 1.0, "grudge_retention": -0.5},
         "b": {"forgiveness": 0.0, "conflict_directness": 0.7},
         "c": {"forgiveness": -1.0, "grudge_retention": 1.0}},
    ),
    ScenarioItem(
        "D4", "Someone you just met asks for something you'd rather keep for yourself.",
        {"a": ("give", "give it to them anyway"), "b": ("request", "offer a trade instead"),
         "c": ("reject", "say no")},
        {"a": {"generosity": 1.0}, "b": {"generosity": 0.2, "risk_tolerance": 0.2},
         "c": {"generosity": -1.0}},
    ),
    ScenarioItem(
        "D5", "You find out a close friend lied to you about something small.",
        {"a": ("confide", "talk it through with them directly"), "b": ("criticise", "call it out sharply"),
         "c": ("ignore", "let it go without saying anything")},
        {"a": {"honesty": 0.7, "conflict_directness": 0.3},
         "b": {"honesty": 1.0, "conflict_directness": 1.0},
         "c": {"honesty": -0.5, "conflict_directness": -1.0}},
    ),
    ScenarioItem(
        "D6", "A real opportunity appears, but taking it risks something you already have.",
        {"a": ("take", "go for it"), "b": ("trade", "negotiate a safer version"),
         "c": ("reject", "pass on it")},
        {"a": {"risk_tolerance": 1.0, "ambition": 0.5},
         "b": {"risk_tolerance": 0.2, "ambition": 0.2},
         "c": {"risk_tolerance": -1.0, "ambition": -0.3}},
    ),
    ScenarioItem(
        "D7", "No one has claimed the lead on a shared project everyone wants done.",
        {"a": ("build", "take the initiative yourself"), "b": ("join_group", "support whoever steps up"),
         "c": ("idle", "wait and see")},
        {"a": {"ambition": 1.0, "independence": 0.5},
         "b": {"ambition": -0.2, "sociability": 0.5},
         "c": {"ambition": -1.0}},
    ),
    ScenarioItem(
        "D8", "A new person joins your usual circle.",
        {"a": ("compliment", "make an effort to make them feel welcome"),
         "b": ("greet", "a simple, polite hello"),
         "c": ("ignore", "carry on as normal")},
        {"a": {"sociability": 1.0, "generosity": 0.3}, "b": {"sociability": 0.2}, "c": {"sociability": -0.7}},
    ),
    ScenarioItem(
        "D9", "You're holding a secret that could help you personally if you shared it.",
        {"a": ("confide", "share it with someone"), "b": ("ignore", "keep it to yourself")},
        {"a": {"loyalty": -1.0}, "b": {"loyalty": 1.0}},
    ),
    ScenarioItem(
        "D10", "You've been unusually quiet, and someone asks if you're okay.",
        {"a": ("speak_to", "actually open up about it"), "b": ("ignore", "deflect and change the subject")},
        {"a": {"emotional_expressiveness": 1.0}, "b": {"emotional_expressiveness": -1.0}},
    ),
    ScenarioItem(
        "D11", "Something unfamiliar catches your attention, but exploring it costs you time.",
        {"a": ("move_to", "go check it out"), "b": ("gather", "stay focused on what's practical"),
         "c": ("idle", "not interested either way")},
        {"a": {"curiosity": 1.0}, "b": {"curiosity": -0.5, "ambition": 0.3}, "c": {"curiosity": -1.0}},
    ),
    ScenarioItem(
        "D12", "Someone who wronged you before is now asking for your help.",
        {"a": ("forgive", "help them anyway"),
         "b": ("request", "help, but only if they do something for you first"),
         "c": ("reject", "refuse")},
        {"a": {"forgiveness": 1.0, "grudge_retention": -1.0},
         "b": {"forgiveness": 0.0, "grudge_retention": 0.2},
         "c": {"forgiveness": -1.0, "grudge_retention": 1.0}},
    ),
)


def _validate_scenarios() -> None:
    """Every option must name a real, currently-registered action — the
    whole point of Method D per spec.md §2.5 ("from the actual action
    registry"), checked once at import time rather than trusting the
    hand-written table above to stay in sync with `safety/registry.py`
    forever.
    """
    for scenario in SCENARIOS:
        for action_name, _framing in scenario.options.values():
            if not ActionRegistry.exists(action_name):
                raise ValueError(f"{scenario.id}: {action_name!r} is not a registered action")


_validate_scenarios()


@dataclass
class ScenarioReplayResult:
    decision_weight_overrides: dict[str, float]
    confidences: dict[str, float]


def score_scenario_replay(answers: dict[str, str]) -> ScenarioReplayResult:
    """answers: scenario id -> option letter (e.g. {"D1": "a", ...}).

    A weight with no answered scenario touching it gets no override at all
    (absent from the returned dict, not defaulted to 0.5) — Method D only
    ever overrides what it actually has trained evidence for; every other
    weight keeps falling back to the trait-derived default.
    """
    accum: dict[str, list[float]] = {name: [] for name in TRAIT_NAMES}
    for scenario in SCENARIOS:
        option = answers.get(scenario.id)
        if option is None:
            continue
        for weight, delta in scenario.effects.get(option, {}).items():
            accum[weight].append(delta)

    overrides: dict[str, float] = {}
    confidences: dict[str, float] = {}
    for name in TRAIT_NAMES:
        deltas = accum[name]
        if not deltas:
            continue
        avg = sum(deltas) / len(deltas)
        overrides[name] = clamp01(0.5 + WEIGHT_SCALE * avg)
        # More scenarios touching the same weight is more directly-observed
        # evidence, not more dilution — confidence rises with count, capped
        # at 0.95 (never fully certain from 10-15 scenarios alone).
        confidences[name] = min(0.95, 0.6 + 0.1 * (len(deltas) - 1))
    return ScenarioReplayResult(decision_weight_overrides=overrides, confidences=confidences)
