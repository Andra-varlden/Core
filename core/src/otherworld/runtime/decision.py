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
        'For "form_goal", set params to {"description": "<short goal>", "priority": <0-1>}. '
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
    ) -> tuple[ProposedAction, DecisionTrace]:
        summary = _observation_summary(observation, tick)
        user_content = summary + " " + _goal_stack_summary(agent) + _shareable_beliefs_summary(
            retrieved, agent.id
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
