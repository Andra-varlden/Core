"""A richer, still-deterministic mock provider for exercising M5's full
mechanics at scale (About/plan.md T5.1's 20-agent/10,000-tick run).

`llm/providers/mock.py`'s `MockLLMProvider` deliberately only ever greets a
stranger or idles — enough to exercise the M2/M3 tick loop and stay
byte-identical across runs, but relationships never progress past first
contact, so nothing here ever forms a Friend edge, opens a conflict, or
produces a belief worth gossiping about. This provider draws from a wider,
weighted slice of the action registry so a large-scale run actually
produces the distributions About/plan.md's T5.3-T5.8 measure — still a pure
function of prompt content, no external RNG state, so determinism (T5.2)
holds exactly as it does for `MockLLMProvider`.

Not a general-purpose replacement for `MockLLMProvider`: it doesn't attempt
to be "smart" (no relationship-state awareness — About/runtime/decision.py
doesn't surface that to the prompt yet either), just varied enough to
exercise every mechanical system at least some of the time.
"""

from __future__ import annotations

import hashlib
import json
import re

from otherworld.llm.protocol import Completion, Prompt
from otherworld.llm.providers.mock import MockLLMProvider

_UNMET_AGENTS_RE = re.compile(r"never interacted with before: \[([^\]]*)\]")
_VISIBLE_AGENTS_RE = re.compile(r"Visible agents: \[([^\]]*)\]")
_BELIEFS_RE = re.compile(r"Beliefs you could share: (.+?)\.(?:\s|$)")
_BELIEF_ENTRY_RE = re.compile(r"([0-9a-fA-F-]{36}) \(about ([0-9a-fA-F-]{36}):")
_GOAL_NONE_MARKER = "You currently have no active goals."
_REFLECTION_MARKER = "Memories since your last reflection"

# Weighted pool of (action, weight) for an ordinary social tick. Rough mix
# favouring ambient interaction, with enough conflict/repair/material
# variety that all five triggers and all three terminal transitions have a
# real chance of appearing over a long run.
_ACTION_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("greet", 14), ("speak_to", 14), ("compliment", 10), ("ignore", 5),
    ("criticise", 6), ("reject", 4), ("betray", 3), ("take", 4),
    ("apologise", 7), ("forgive", 7), ("give", 4), ("request", 3),
    ("trade", 2), ("idle", 5), ("move_to", 16),
)
_NO_TARGET_ACTIONS = ("idle", "gather", "move_to")
_TOTAL_WEIGHT = sum(w for _, w in _ACTION_WEIGHTS)
_GOAL_ROLL_MODULUS = 23  # ~1-in-23 ordinary ticks attempts a goal action
_CONFIDE_ROLL_MODULUS = 5  # ~1-in-5 ticks with a shareable belief actually shares it


def _weighted_choice(roll: int) -> str:
    upto = 0
    bounded = roll % _TOTAL_WEIGHT
    for action, weight in _ACTION_WEIGHTS:
        upto += weight
        if bounded < upto:
            return action
    return "idle"  # unreachable; defensive only


def _completion(
    model: str, joined: str, action: str, targets: list[str], params: dict[str, object]
) -> Completion:
    digest = hashlib.sha256(joined.encode()).hexdigest()[:8]
    text = json.dumps(
        {"action": action, "targets": targets, "params": params, "reasoning": f"scenario-{digest}"}
    )
    return Completion(text=text, input_tokens=len(joined) // 4, output_tokens=16, model=model)


class ScenarioMockProvider:
    """Deterministic (hash-of-prompt-driven), no network access."""

    def __init__(self) -> None:
        self._base = MockLLMProvider()

    async def tier1(self, prompt: Prompt) -> Completion:
        return self._respond(prompt, model="scenario-mock-tier1")

    async def tier2(self, prompt: Prompt) -> Completion:
        return self._respond(prompt, model="scenario-mock-tier2")

    async def embed(self, text: str) -> list[float]:
        return await self._base.embed(text)

    def _respond(self, prompt: Prompt, model: str) -> Completion:
        joined = prompt.system + "".join(m.get("content", "") for m in prompt.messages)

        if _REFLECTION_MARKER in joined:
            # Belief formation itself doesn't need extra variety — reuse
            # MockLLMProvider's already-tested, hash-driven belief response.
            return self._base._respond(prompt, model)  # noqa: SLF001

        digest_int = int(hashlib.sha256(joined.encode()).hexdigest()[:8], 16)

        unmet_match = _UNMET_AGENTS_RE.search(joined)
        unmet_ids = [s.strip() for s in unmet_match.group(1).split(",") if s.strip()] if unmet_match else []
        if unmet_ids:
            return _completion(model, joined, "greet", [unmet_ids[0]], {})

        visible_match = _VISIBLE_AGENTS_RE.search(joined)
        visible_ids = (
            [s.strip() for s in visible_match.group(1).split(",") if s.strip()] if visible_match else []
        )

        if not visible_ids:
            action = "idle" if digest_int % 2 == 0 else "gather"
            return _completion(model, joined, action, [], {})

        # Occasionally attempt a goal action instead of a social one.
        if digest_int % _GOAL_ROLL_MODULUS == 0:
            if _GOAL_NONE_MARKER in joined:
                # About/spec.md §7.1's VALUE_CLASH needs two agents' goals to
                # target the same third party exclusively — two different
                # agents rolling `form_goal` only land on the same target by
                # chance if that target is chosen the same way regardless of
                # whose prompt it's computed from. `min(visible_ids)` (the
                # most broadly-visible/"prominent" agent locally, a stand-in
                # for "who everyone's chasing") does that; `visible_ids[0]`
                # (a per-agent, list-order-dependent pick) mostly didn't,
                # which is why a real 20-agent run never observed a single
                # VALUE_CLASH despite the mechanism being correct in
                # isolation (`tests/simulation/test_maintenance.py`).
                # Exclusive about half the time so it's a real chance, not a
                # certainty, over a long run.
                exclusive = digest_int % 2 == 0
                return _completion(
                    model, joined, "form_goal", [],
                    {
                        "description": "pursue something new (scenario)", "priority": 0.6,
                        "target_agent_id": min(visible_ids), "exclusive": exclusive,
                    },
                )
            # Goals exist but we don't know their ids from this prompt
            # section alone without a second regex; skip abandon_goal here
            # rather than guess an id — a legitimate omission, not a bug.

        target = visible_ids[digest_int % len(visible_ids)]

        beliefs_match = _BELIEFS_RE.search(joined)
        if beliefs_match and digest_int % _CONFIDE_ROLL_MODULUS == 0:
            entry_match = _BELIEF_ENTRY_RE.search(beliefs_match.group(1))
            if entry_match:
                belief_id, about_agent_id = entry_match.group(1), entry_match.group(2)
                return _completion(
                    model, joined, "confide", [target],
                    {"belief_id": belief_id, "about_agent_id": about_agent_id},
                )

        action = _weighted_choice(digest_int // max(len(visible_ids), 1))
        targets = [] if action in _NO_TARGET_ACTIONS else [target]
        params: dict[str, object] = (
            {"x": digest_int % 60, "y": (digest_int // 60) % 60} if action == "move_to" else {}
        )
        return _completion(model, joined, action, targets, params)
