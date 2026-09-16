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
from typing import Literal

from otherworld.llm.protocol import LLMProvider, Prompt
from otherworld.models.agent import Agent
from otherworld.models.events import ActionCategory, ProposedAction
from otherworld.models.memory import MemoryRecord
from otherworld.persona.compiler import AgentBundle
from otherworld.runtime.clock import tick_to_datetime
from otherworld.runtime.perception import Observation
from otherworld.runtime.trace import DecisionTrace
from otherworld.safety.registry import ActionRegistry, UnknownActionError

_RESPONSE_INSTRUCTION = (
    'Respond with JSON only: {"action": "<registered action name>", '
    '"targets": [], "reasoning": "<why>"}.'
)


def _category_for(action_name: str) -> ActionCategory:
    try:
        return ActionRegistry.resolve(action_name).category
    except UnknownActionError:
        return ActionCategory.INTERNAL


def _parse_completion(text: str) -> tuple[str, list[uuid.UUID], str]:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return "idle", [], "unparseable completion"

    action = data.get("action")
    if not isinstance(action, str):
        return "idle", [], "completion had no action field"

    targets: list[uuid.UUID] = []
    for raw in data.get("targets", []) or []:
        try:
            targets.append(uuid.UUID(str(raw)))
        except ValueError:
            continue

    reasoning = data.get("reasoning", "")
    return action, targets, str(reasoning) if reasoning is not None else ""


def _observation_summary(observation: Observation, tick: int) -> str:
    return f"Tick {tick}. Zone: {observation.zone}. Visible agents: {len(observation.visible_agents)}."


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
    ) -> tuple[ProposedAction, DecisionTrace]:
        summary = _observation_summary(observation, tick)
        user_content = summary
        if constraint_note:
            user_content += f" Constraint: {constraint_note}"
        user_content += " " + _RESPONSE_INSTRUCTION

        prompt = Prompt(system=bundle.identity_prompt, messages=[{"role": "user", "content": user_content}])

        start = time.perf_counter()
        completion = await (provider.tier2(prompt) if tier == 2 else provider.tier1(prompt))
        latency_ms = (time.perf_counter() - start) * 1000

        action_name, targets, reasoning = _parse_completion(completion.text)

        proposed = ProposedAction(
            agent_id=agent.id,
            action=action_name,
            category=_category_for(action_name),
            targets=targets,
            params={},
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
