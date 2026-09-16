"""The tick scheduler. See About/architecture.md §4, §13.

For M2: a single agent, no concurrency. Orchestrates the six phases per
tick and enforces the hard rules from About/spec.md §4.1 — exactly one
action per tick, and a double validator rejection falls through to the
safe default (`idle`) rather than crashing.

Tier 0 (sleep window) is pure Python and never touches `LLMProvider`. Tier 1
handles everything else in M2's world. Tier 2 is reachable in code but has
no escalation trigger that can fire yet (About/architecture.md §12's list —
first encounters, relationship bands, conflicts, goals, group scenes,
reflection, whispers — all belong to later milestones), so it is never
selected here; About/plan.md T2.8 asserts exactly that.
"""

from __future__ import annotations

import random
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from otherworld.config import settings
from otherworld.llm.protocol import LLMProvider
from otherworld.models.agent import Agent
from otherworld.models.events import EventRecord, Rejection, ValidatedAction
from otherworld.persona.compiler import AgentBundle
from otherworld.runtime.clock import tick_to_datetime
from otherworld.runtime.decision import DecisionEngine
from otherworld.runtime.perception import PerceptionService
from otherworld.runtime.resolver import Resolver
from otherworld.runtime.retrieval import RetrievalService
from otherworld.runtime.trace import TraceLog
from otherworld.safety.validator import Validator

_MINUTES_PER_DAY = 24 * 60
_SLEEP_WINDOW_END_HOUR = 6  # [TUNE] midnight-6am; a persona-derived window is later work


def in_sleep_window(tick: int) -> bool:
    minutes = (tick * settings.world.in_world_minutes_per_tick) % _MINUTES_PER_DAY
    hour = minutes // 60
    return hour < _SLEEP_WINDOW_END_HOUR


class TickScheduler:
    def __init__(
        self,
        session: AsyncSession,
        provider: LLMProvider,
        rng: random.Random,
        world_id: uuid.UUID,
        agent: Agent,
        bundle: AgentBundle,
    ) -> None:
        self.session = session
        self.provider = provider
        self.rng = rng
        self.world_id = world_id
        self.agent = agent
        self.bundle = bundle
        self.trace_log = TraceLog()

    async def _propose_and_validate(
        self, tick: int, constraint_note: str | None = None
    ) -> ValidatedAction | Rejection:
        observation = PerceptionService.observe(self.agent, tick, other_agents_present=[])
        query_embedding = await self.provider.embed(f"tick {tick} ambient decision")
        retrieved = await RetrievalService.retrieve(
            self.session, self.agent.id, query_embedding, tick, tier=1
        )
        proposed, trace = await DecisionEngine.decide(
            self.agent,
            self.bundle,
            observation,
            retrieved,
            self.provider,
            tick,
            tier=1,
            constraint_note=constraint_note,
        )
        result = Validator.validate(
            proposed,
            self.bundle.boundary_ruleset,
            self.agent.display_name,
            set(observation.visible_agents),
            tick_to_datetime(tick),
        )
        trace.validator_result = (
            "accepted" if not isinstance(result, Rejection) else f"rejected:{result.failed_filter}"
        )
        self.trace_log.record(trace)
        return result

    async def run_tick(self, tick: int) -> EventRecord:
        if in_sleep_window(tick):
            return await Resolver.resolve(
                self.session,
                self.provider,
                self.rng,
                self.world_id,
                self.agent.id,
                self.agent.position,
                tick,
                "sleep",
                [],
                "sleep window",
            )

        result = await self._propose_and_validate(tick)

        if isinstance(result, Rejection):
            constraint = f"Your previous choice was rejected ({result.reason}). Choose idle."
            result = await self._propose_and_validate(tick, constraint_note=constraint)

        if isinstance(result, Rejection):
            action_name, targets, reasoning = "idle", [], "double validator rejection; safe default"
        else:
            action_name, targets, reasoning = result.action, result.targets, result.reasoning

        event = await Resolver.resolve(
            self.session,
            self.provider,
            self.rng,
            self.world_id,
            self.agent.id,
            self.agent.position,
            tick,
            action_name,
            targets,
            reasoning,
        )
        self.agent.last_tick = tick
        return event

    async def run(self, num_ticks: int, start_tick: int = 0) -> list[EventRecord]:
        return [await self.run_tick(t) for t in range(start_tick, start_tick + num_ticks)]
