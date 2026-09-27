"""The decision engine. See About/architecture.md §4, §12.

Only Tier 1/2 decisions go through here — Tier 0 (routine, sleep, walking a
stored path) is pure Python in the scheduler and never touches
`LLMProvider`, per architecture.md §12: "Tier 0 never touches this
interface."
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any, Literal

from otherworld.config import settings
from otherworld.llm.protocol import LLMProvider, Prompt
from otherworld.models.agent import Agent
from otherworld.models.events import ActionCategory, ProposedAction
from otherworld.models.memory import MemoryKind, MemoryRecord
from otherworld.models.relationship import BondState, RelationshipEdge
from otherworld.persona.compiler import AgentBundle
from otherworld.runtime.clock import tick_to_datetime
from otherworld.runtime.json_util import extract_json_object
from otherworld.runtime.perception import Observation
from otherworld.runtime.trace import DecisionTrace
from otherworld.safety.registry import ActionRegistry, UnknownActionError


def _response_instruction() -> str:
    # A real model given only "<registered action name>" will happily
    # invent a plausible-sounding action that doesn't exist (observed live:
    # a Groq-hosted model proposed "register_agent" on a first encounter —
    # correctly rejected by the Validator's legality filter, but avoidable
    # by just telling it the closed set up front instead of relying on
    # containment to catch every guess after the fact).
    actions = ", ".join(ActionRegistry.all_actions())
    return (
        "Respond with JSON only, no other text, no markdown code fences: "
        '{"action": "<one of the actions listed below>", "targets": [], "params": {}, "reasoning": "<why>"}. '
        f"Valid actions, and only these: {actions}. "
        'For "form_goal", set params to {"description": "<short goal>", "priority": <0-1>, '
        '"target_agent_id": "<id from visible agents, or null>", '
        '"exclusive": <true if this goal competes with anyone else pursuing the same target agent>}. '
        'For "abandon_goal", set params to {"goal_id": "<id of a goal from your current goal stack>"}. '
        'For "confide" when sharing one of your beliefs (see the beliefs listed above, if any), set '
        'params to {"belief_id": "<id of the belief>", "about_agent_id": "<id it is about>"}.'
    )


def _category_for(action_name: str) -> ActionCategory:
    try:
        return ActionRegistry.resolve(action_name).category
    except UnknownActionError:
        return ActionCategory.INTERNAL


def _parse_completion(text: str) -> tuple[str, list[uuid.UUID], dict[str, Any], str]:
    try:
        data = json.loads(extract_json_object(text))
    except (json.JSONDecodeError, TypeError):
        return "idle", [], {}, "unparseable completion"

    action = data.get("action")
    if not isinstance(action, str):
        return "idle", [], {}, "completion had no action field"

    targets: list[uuid.UUID] = []
    for raw in data.get("targets", []) or []:
        try:
            targets.append(uuid.UUID(str(raw)))
        except ValueError:
            continue

    params = data.get("params")
    if not isinstance(params, dict):
        params = {}

    reasoning = data.get("reasoning", "")
    return action, targets, params, str(reasoning) if reasoning is not None else ""


def _observation_summary(observation: Observation, tick: int) -> str:
    ids = ", ".join(str(a) for a in observation.visible_agents)
    return f"Tick {tick}. Zone: {observation.zone}. Visible agents: [{ids}]."


def _goal_stack_summary(agent: Agent) -> str:
    if not agent.goals:
        return "You currently have no active goals."
    goals = "; ".join(f"{g.id} ({g.description})" for g in agent.goals)
    return f"Your current goals: {goals}."


def _relationship_context_summary(
    visible_agents: list[uuid.UUID], relationships: dict[uuid.UUID, RelationshipEdge]
) -> str:
    """Without this, every visible agent is just an opaque UUID with no
    social stakes attached — About/plan.md M4's real-run finding (tried
    after `_recent_memory_summary` alone didn't change anything): a model
    with no sense of "this is a close friend" vs. "we've never really
    spoken" has no reason to treat anyone differently, so it reliably
    defaults to the same generic greet/idle regardless of who's actually
    there.

    Also flags whichever visible agent has the LOWEST `contact_count` among
    them, when the group isn't already even. About/plan.md's M4 real trial
    found this summary's own trust/bond_state framing turns any early,
    accidental imbalance into a self-reinforcing ratchet: the model has an
    explicit, rational reason to keep favouring whoever it already trusts
    and to keep avoiding whoever it's barely spoken to (doubly so once that
    edge's trust has decayed negative) — nothing in the prompt ever pushed
    back the other way. One real world ended up with a single hub bonded to
    everyone while the other agents almost never contacted each other
    directly. This doesn't override the trust framing, it just puts a
    thumb on the scale toward the agent being left out.
    """
    if not visible_agents:
        return ""

    known_counts = [relationships[a].contact_count for a in visible_agents if a in relationships]
    least_contacted_count = (
        min(known_counts) if len(known_counts) >= 2 and max(known_counts) > min(known_counts) else None
    )

    def _line(agent_id: uuid.UUID) -> str:
        edge = relationships.get(agent_id)
        if edge is None:
            return f"{agent_id} (no relationship history yet)"
        base = f"{agent_id} ({edge.bond_state.value}, trust {edge.trust:.2f})"
        # About/spec.md §6.5's Close bond formation needs a `give` action on
        # top of already-high trust (`social/state_machine.py`'s
        # `is_costly_loyalty_act`) — mentioned explicitly because it's easy
        # to miss it's even possible from the bond_state/trust numbers alone
        # (About/plan.md's M4 real trial: several relationships sat at
        # trust=1.0 "friend" for 2,000+ ticks without this ever being tried).
        close_bond_ready = (
            edge.bond_state == BondState.FRIEND
            and edge.trust >= settings.relationships.close_bond_trust_threshold
        )
        if close_bond_ready:
            base += " — a meaningful gesture like 'give' could deepen this into a close bond"
        elif least_contacted_count is not None and edge.contact_count == least_contacted_count:
            base += " — you interact with them far less than the others here; reaching out could be worth it"
        return base

    lines = [_line(agent_id) for agent_id in visible_agents]
    return f" Your relationships with visible agents: {'; '.join(lines)}."


def _recent_memory_summary(retrieved: list[MemoryRecord]) -> str:
    """Surfaces what `RetrievalService` actually retrieved (About/spec.md
    §5.2's recency+importance+relevance top-k) as narrative content the
    model can react to. Before this, `retrieved` was fetched every tick and
    then only ever used for `_shareable_beliefs_summary`'s narrow filter and
    `DecisionTrace` logging — its actual `.content` (what really happened:
    "Another agent did 'betray' to me at tick 10") never reached the
    prompt at all. About/plan.md's M4 real-run finding: with nothing to
    react to beyond a tick number and a list of opaque agent UUIDs, a real
    model reliably defaulted to generic greet/idle/sleep for an entire
    simulated week, across all five real personas — raising reasoning
    effort didn't change that (a real re-test), because the problem was
    never how much the model thought, it was that there was nothing to
    think *about*.
    """
    if not retrieved:
        return ""
    lines = "; ".join(f"(tick {m.tick}) {m.content}" for m in retrieved)
    return f" What you remember: {lines}."


def _shareable_beliefs_summary(retrieved: list[MemoryRecord], agent_id: uuid.UUID) -> str:
    """About/spec.md §8.1: only beliefs about someone else, strong enough to
    be worth propagating, are gossip-eligible — surfaced from whatever
    `RetrievalService` already retrieved for this tick (About/runtime/
    reflection.py's docstring: no separate omniscient belief dump)."""
    shareable = [
        m
        for m in retrieved
        if m.kind == MemoryKind.BELIEF
        and m.importance >= settings.gossip.min_importance_to_propagate
        and m.subjects
        and m.subjects[0] != agent_id
    ]
    if not shareable:
        return ""
    lines = "; ".join(f"{m.id} (about {m.subjects[0]}: {m.content})" for m in shareable)
    return f" Beliefs you could share: {lines}."


class DecisionEngine:
    @staticmethod
    async def decide(
        agent: Agent,
        bundle: AgentBundle,
        observation: Observation,
        retrieved: list[MemoryRecord],
        provider: LLMProvider,
        tick: int,
        tier: Literal[1, 2],
        constraint_note: str | None = None,
        unmet_agent_ids: list[uuid.UUID] | None = None,
        relationships: dict[uuid.UUID, RelationshipEdge] | None = None,
    ) -> tuple[ProposedAction, DecisionTrace]:
        summary = _observation_summary(observation, tick)
        user_content = (
            summary
            + " "
            + _goal_stack_summary(agent)
            + _relationship_context_summary(observation.visible_agents, relationships or {})
            + _recent_memory_summary(retrieved)
            + _shareable_beliefs_summary(retrieved, agent.id)
        )
        if unmet_agent_ids:
            ids = ", ".join(str(a) for a in unmet_agent_ids)
            user_content += f" Agents you have never interacted with before: [{ids}]."
        if constraint_note:
            user_content += f" Constraint: {constraint_note}"
        user_content += " " + _response_instruction()

        prompt = Prompt(system=bundle.identity_prompt, messages=[{"role": "user", "content": user_content}])

        start = time.perf_counter()
        completion = await (provider.tier2(prompt) if tier == 2 else provider.tier1(prompt))
        latency_ms = (time.perf_counter() - start) * 1000

        action_name, targets, params, reasoning = _parse_completion(completion.text)

        proposed = ProposedAction(
            agent_id=agent.id,
            action=action_name,
            category=_category_for(action_name),
            targets=targets,
            params=params,
            reasoning=reasoning,
            tier_used=tier,
        )

        trace = DecisionTrace(
            agent_id=agent.id,
            tick=tick,
            observation_summary=summary,
            retrieved_memory_ids=[m.id for m in retrieved],
            prompt_hash=hashlib.sha256((bundle.identity_prompt + user_content).encode()).hexdigest(),
            tier_used=tier,
            raw_completion=completion.text,
            parsed_action=action_name,
            validator_result="pending",
            latency_ms=latency_ms,
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
            estimated_cost_usd=0.0,  # populate once About/spec.md §15.3 rate table is filled
            created_at=tick_to_datetime(tick),
        )
        return proposed, trace
