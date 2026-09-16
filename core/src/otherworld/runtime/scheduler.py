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

import asyncio
import random
import uuid
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from otherworld.config import settings
from otherworld.llm.protocol import LLMProvider
from otherworld.models.agent import Agent
from otherworld.models.events import EventRecord, Rejection, ValidatedAction
from otherworld.models.memory import MemoryRecord
from otherworld.persona.compiler import AgentBundle
from otherworld.runtime.clock import tick_to_datetime
from otherworld.runtime.decision import DecisionEngine
from otherworld.runtime.determinism import seeded_uuid
from otherworld.runtime.perception import Observation, PerceptionService
from otherworld.runtime.resolver import Resolver
from otherworld.runtime.retrieval import RetrievalService
from otherworld.runtime.trace import TraceLog
from otherworld.safety.validator import Validator
from otherworld.social.engine import get_or_create_edge

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


class MultiAgentTickScheduler:
    """M3: N agents sharing one abstract room (still no tile map — ADR-008).

    Escalation trigger 1 ("first encounter with a previously unmet agent",
    About/architecture.md §12) is detected in a **sequential** pre-pass at
    the start of the tick, before any decision is computed — not inside the
    per-agent decision step. If it ran per-agent inside the concurrent
    decide step, both members of a brand-new pair would independently see
    "no edge yet" at the same instant and both would escalate to Tier 2 on
    the same tick, firing the trigger twice for one pair. Materialising the
    edge sequentially means whichever agent is processed first (lower
    agent id) claims the encounter and creates the edge; the second agent,
    processed moments later in the same pass, finds it already exists.
    That is what makes About/plan.md T3.8 ("fires exactly once per new
    pair") hold deterministically rather than by luck.

    Decisions themselves are still computed concurrently (`asyncio.gather`)
    but always applied in a fixed agent-id-sorted order regardless of which
    LLM call happened to finish first — About/architecture.md §13, tested by
    T3.3. `asyncio.gather` returns results in input order, so this is
    enforced by construction: `self.agents` is sorted once, at construction,
    and events are resolved by iterating it, never by completion order.
    """

    def __init__(
        self,
        session: AsyncSession,
        provider: LLMProvider,
        rng: random.Random,
        world_id: uuid.UUID,
        agents: list[Agent],
        bundles: dict[uuid.UUID, AgentBundle],
    ) -> None:
        self.session = session
        self.provider = provider
        self.rng = rng
        self.world_id = world_id
        self.agents = sorted(agents, key=lambda a: a.id)
        self.bundles = bundles
        self.trace_log = TraceLog()

    async def _materialise_new_encounters(
        self, tick: int
    ) -> tuple[dict[uuid.UUID, list[uuid.UUID]], dict[uuid.UUID, list[uuid.UUID]]]:
        visible_by_agent = {
            agent.id: [a.id for a in self.agents if a.id != agent.id] for agent in self.agents
        }
        newly_met: dict[uuid.UUID, list[uuid.UUID]] = {agent.id: [] for agent in self.agents}

        for agent in self.agents:
            for other_id in visible_by_agent[agent.id]:
                _edge, created = await get_or_create_edge(
                    self.session, self.world_id, agent.id, other_id, seeded_uuid(self.rng), tick
                )
                if created:
                    newly_met[agent.id].append(other_id)

        return visible_by_agent, newly_met

    async def _propose_and_validate(
        self,
        agent: Agent,
        observation: Observation,
        retrieved: list[MemoryRecord],
        tick: int,
        tier: Literal[1, 2],
        unmet: list[uuid.UUID],
        constraint_note: str | None = None,
    ) -> ValidatedAction | Rejection:
        proposed, trace = await DecisionEngine.decide(
            agent,
            self.bundles[agent.id],
            observation,
            retrieved,
            self.provider,
            tick,
            tier=tier,
            constraint_note=constraint_note,
            unmet_agent_ids=unmet or None,
        )
        result = Validator.validate(
            proposed,
            self.bundles[agent.id].boundary_ruleset,
            agent.display_name,
            set(observation.visible_agents),
            tick_to_datetime(tick),
        )
        trace.validator_result = (
            "accepted" if not isinstance(result, Rejection) else f"rejected:{result.failed_filter}"
        )
        self.trace_log.record(trace)
        return result

    async def _decide_for_agent(
        self, agent: Agent, tick: int, visible: list[uuid.UUID], unmet: list[uuid.UUID]
    ) -> tuple[str, list[uuid.UUID], str, list[uuid.UUID], bool]:
        tier: Literal[1, 2] = 2 if unmet else 1

        observation = PerceptionService.observe(agent, tick, other_agents_present=visible)
        query_embedding = await self.provider.embed(f"tick {tick} ambient decision")
        retrieved = await RetrievalService.retrieve(self.session, agent.id, query_embedding, tick, tier=tier)

        result = await self._propose_and_validate(agent, observation, retrieved, tick, tier, unmet)
        if isinstance(result, Rejection):
            constraint = f"Your previous choice was rejected ({result.reason}). Choose idle."
            result = await self._propose_and_validate(
                agent, observation, retrieved, tick, tier, unmet, constraint_note=constraint
            )

        if isinstance(result, Rejection):
            return "idle", [], "double validator rejection; safe default", visible, False

        first_encounter = any(t in unmet for t in result.targets)
        return result.action, result.targets, result.reasoning, visible, first_encounter

    async def run_tick(self, tick: int) -> list[EventRecord]:
        if in_sleep_window(tick):
            # Sleeping agents are "unperceiving for duration" (About/spec.md
            # §10's `sleep` semantics) — no encounter detection, no edges
            # materialised, purely Tier 0. Otherwise agents who have never
            # been awake at the same time would still "meet" at tick 0.
            events = []
            for agent in self.agents:
                event = await Resolver.resolve(
                    self.session, self.provider, self.rng, self.world_id, agent.id,
                    agent.position, tick, "sleep", [], "sleep window", witnesses=[],
                )
                agent.last_tick = tick
                events.append(event)
            return events

        visible_by_agent, newly_met = await self._materialise_new_encounters(tick)

        decisions = await asyncio.gather(
            *[self._decide_for_agent(agent, tick, visible_by_agent[agent.id], newly_met[agent.id])
              for agent in self.agents]
        )

        events = []
        for agent, (action_name, targets, reasoning, visible, first_encounter) in zip(
            self.agents, decisions, strict=True
        ):
            witnesses = [v for v in visible if v not in targets]
            event = await Resolver.resolve(
                self.session,
                self.provider,
                self.rng,
                self.world_id,
                agent.id,
                agent.position,
                tick,
                action_name,
                targets,
                reasoning,
                witnesses=witnesses,
                first_encounter=first_encounter,
            )
            agent.last_tick = tick
            events.append(event)
        return events

    async def run(self, num_ticks: int, start_tick: int = 0) -> list[EventRecord]:
        all_events: list[EventRecord] = []
        for t in range(start_tick, start_tick + num_ticks):
            all_events.extend(await self.run_tick(t))
        return all_events
