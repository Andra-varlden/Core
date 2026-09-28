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
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from otherworld.config import settings
from otherworld.llm.protocol import LLMProvider
from otherworld.models.agent import Agent
from otherworld.models.events import EventRecord, Rejection, ValidatedAction
from otherworld.models.memory import MemoryRecord
from otherworld.models.relationship import BondState, RelationshipEdge
from otherworld.models.trace import decision_trace_to_orm
from otherworld.persona.compiler import AgentBundle
from otherworld.runtime.clock import tick_to_datetime
from otherworld.runtime.compression import compress_if_over_cap
from otherworld.runtime.decision import DecisionEngine
from otherworld.runtime.determinism import seeded_uuid
from otherworld.runtime.goals import abandon_goal, form_goal, maybe_adopt_goal, prune_stale_goals
from otherworld.runtime.perception import Observation, PerceptionService
from otherworld.runtime.reflection import ReflectionService, is_reflection_due
from otherworld.runtime.resolver import Resolver
from otherworld.runtime.retrieval import RetrievalService
from otherworld.runtime.trace import TraceLog
from otherworld.safety.validator import Validator
from otherworld.social.conflict import compute_damping_factor, conflicts_per_agent_per_day
from otherworld.social.engine import get_all_edges, get_edge, get_or_create_edge
from otherworld.social.factions import (
    Clique,
    ExclusionCandidate,
    FactionPair,
    find_cliques,
    find_exclusion_candidates,
    find_faction_pairs,
)
from otherworld.social.gossip import get_shareable_beliefs
from otherworld.social.maintenance import run_maintenance_scan
from otherworld.world.exogenous import ExogenousEvent, ExogenousEventScheduler
from otherworld.world.map import WorldMap, generate_starter_map
from otherworld.world.pathfinding import find_path
from otherworld.world.proximity import agents_within_radius

_COUPLING_ELIGIBLE_BOND_STATES = (BondState.FRIEND, BondState.CLOSE_BOND)

_MINUTES_PER_DAY = 24 * 60
_SLEEP_WINDOW_END_HOUR = 6  # [TUNE] midnight-6am; a persona-derived window is later work


def in_sleep_window(tick: int) -> bool:
    minutes = (tick * settings.world.in_world_minutes_per_tick) % _MINUTES_PER_DAY
    hour = minutes // 60
    return hour < _SLEEP_WINDOW_END_HOUR


def _parse_move_destination(params: dict[str, Any], world_map: WorldMap) -> tuple[int, int] | None:
    try:
        x, y = int(params.get("x")), int(params.get("y"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return (x, y) if world_map.in_bounds((x, y)) else None


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
        self.session.add(decision_trace_to_orm(trace))
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
            bundles={self.agent.id: self.bundle},
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
        world_map: WorldMap | None = None,
    ) -> None:
        self.session = session
        self.provider = provider
        self.rng = rng
        self.world_id = world_id
        self.agents = sorted(agents, key=lambda a: a.id)
        self.agents_by_id = {a.id: a for a in self.agents}
        self.bundles = bundles
        self.world_map = world_map or generate_starter_map(
            world_id, settings.world.width, settings.world.height
        )
        self.tier0_walk_count = 0
        self.trace_log = TraceLog()
        self.exogenous_scheduler = ExogenousEventScheduler(rng)
        self.exogenous_events_fired: list[ExogenousEvent] = []
        self._last_faction_scan_tick: int | None = None
        self.cliques: list[Clique] = []
        self.faction_pairs: list[FactionPair] = []
        self.exclusion_signals: list[ExclusionCandidate] = []
        self._exclusion_first_seen: dict[tuple[uuid.UUID, frozenset[uuid.UUID]], int] = {}
        self._last_maintenance_scan_tick: int | None = None
        self._last_damping_check_tick: int | None = None
        self.conflict_damping_factor: float = 1.0

    async def _maybe_update_conflict_damping(self, tick: int) -> None:
        """About/spec.md §7.6. Reuses the same periodic-whole-graph-scan
        cadence as `_maybe_run_maintenance`/`_maybe_scan_factions` rather
        than a per-tick query — the rate this throttles is a trend over a
        window, not something that needs checking every tick.
        """
        due = (
            self._last_damping_check_tick is None
            or tick - self._last_damping_check_tick >= settings.conflict.damping_check_interval_ticks
        )
        if not due:
            return
        self._last_damping_check_tick = tick

        window_ticks = settings.conflict.damping_check_interval_ticks
        window_start = max(0, tick - window_ticks)
        edges = await get_all_edges(self.session, self.world_id)
        new_conflicts = sum(
            1
            for edge in edges
            for record in edge.conflict_log
            if window_start <= record.occurred_tick < tick
        )
        rate = conflicts_per_agent_per_day(new_conflicts, len(self.agents), window_ticks)
        self.conflict_damping_factor = compute_damping_factor(rate)

    async def _maybe_run_maintenance(self, tick: int) -> None:
        """Trust decay, decay-driven demotion, Strained timeout/escalation,
        and the scan-tied conflict triggers (About/social/maintenance.py) —
        another whole-graph batch computation with nothing to hang off a
        single agent's action, so it runs on the same kind of periodic
        check as `_maybe_scan_factions` rather than every tick.
        """
        due = (
            self._last_maintenance_scan_tick is None
            or tick - self._last_maintenance_scan_tick >= settings.maintenance.scan_interval_ticks
        )
        if not due:
            return
        self._last_maintenance_scan_tick = tick
        await run_maintenance_scan(
            self.session, self.world_id, self.agents, self.bundles, self.rng, tick,
            damping_factor=self.conflict_damping_factor,
        )

    async def _maybe_scan_factions(self, tick: int) -> None:
        """About/spec.md §8.3, recomputed every `factions.scan_interval_ticks`
        — a whole-graph batch computation, not tied to any agent's action,
        so it runs once per tick check (not once per agent) alongside the
        exogenous event scheduler above.
        """
        due = (
            self._last_faction_scan_tick is None
            or tick - self._last_faction_scan_tick >= settings.factions.scan_interval_ticks
        )
        if not due:
            return
        self._last_faction_scan_tick = tick

        edges = await get_all_edges(self.session, self.world_id)
        self.cliques = find_cliques(edges)
        self.faction_pairs = find_faction_pairs(edges, self.cliques)

        candidates = find_exclusion_candidates(edges, self.cliques)
        current_keys = {(c.agent_id, c.clique.members) for c in candidates}
        for key in list(self._exclusion_first_seen):
            if key not in current_keys:
                del self._exclusion_first_seen[key]  # no longer excluded — resets persistence
        for candidate in candidates:
            self._exclusion_first_seen.setdefault((candidate.agent_id, candidate.clique.members), tick)

        self.exclusion_signals = [
            c
            for c in candidates
            if tick - self._exclusion_first_seen[(c.agent_id, c.clique.members)]
            >= settings.factions.exclusion_persistence_ticks
        ]

    async def _materialise_new_encounters(
        self, tick: int
    ) -> tuple[dict[uuid.UUID, list[uuid.UUID]], dict[uuid.UUID, list[uuid.UUID]]]:
        # Chebyshev-radius visibility (About/spec.md §9.1's perception_radius),
        # not "everyone in the world" — M2/M3 tests all colocate agents at
        # the same position, so this is a strict fidelity upgrade for them
        # (still mutually visible, distance 0) rather than a behaviour change.
        visible_by_agent = {
            agent.id: agents_within_radius(
                agent.position,
                {a.id: a.position for a in self.agents if a.id != agent.id},
                settings.world.perception_radius,
            )
            for agent in self.agents
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
        relationships: dict[uuid.UUID, RelationshipEdge],
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
            relationships=relationships,
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
        self.session.add(decision_trace_to_orm(trace))
        return result

    async def _decide_for_agent(
        self, agent: Agent, tick: int, visible: list[uuid.UUID], unmet: list[uuid.UUID]
    ) -> tuple[str, list[uuid.UUID], dict[str, Any], str, list[uuid.UUID], bool, int]:
        # Tier 0: an agent already walking a stored path just takes its next
        # step, About/architecture.md §12 ("Tier 0 never touches this
        # interface") — but only when nothing more pressing (a first
        # encounter) needs an actual decision this tick.
        if agent.current_path and not unmet:
            self.tier0_walk_count += 1
            step = agent.current_path[0]
            agent.current_path = agent.current_path[1:]
            agent.position = agent.position.model_copy(update={"x": step[0], "y": step[1]})
            return "move_to", [], {}, "walking a stored path (tier 0)", visible, False, 0

        tier: Literal[1, 2] = 2 if unmet else 1

        # `visible` is always in agent-id-sorted order (`_materialise_new_
        # encounters`'s `{a.id: ... for a in self.agents}`, and `self.agents`
        # is sorted once at construction) — the same order, every tick, for
        # every agent. Found live during the M4 real trial: the
        # alphanumerically-lowest agent ID was first (or near-first) in
        # everyone else's list every single tick, and became a social
        # "hub" bonded with all 4 others while the rest barely interacted —
        # a textbook LLM list-position/primacy bias, not a persona trait.
        # Shuffling (with the scheduler's own seeded rng, so determinism/
        # T5.2 still holds) removes the fixed position for the model to
        # anchor on.
        shuffled_visible = list(visible)
        self.rng.shuffle(shuffled_visible)
        observation = PerceptionService.observe(agent, tick, other_agents_present=shuffled_visible)
        query_embedding = await self.provider.embed(f"tick {tick} ambient decision")
        retrieved = await RetrievalService.retrieve(self.session, agent.id, query_embedding, tick, tier=tier)
        shareable = await get_shareable_beliefs(self.session, agent.id)
        retrieved_ids = {m.id for m in retrieved}
        retrieved = [*retrieved, *(b for b in shareable if b.id not in retrieved_ids)]

        relationships: dict[uuid.UUID, RelationshipEdge] = {}
        for other_id in visible:
            edge = await get_edge(self.session, self.world_id, agent.id, other_id)
            if edge is not None:
                relationships[other_id] = edge

        result = await self._propose_and_validate(
            agent, observation, retrieved, tick, tier, unmet, relationships
        )
        if isinstance(result, Rejection):
            constraint = f"Your previous choice was rejected ({result.reason}). Choose idle."
            result = await self._propose_and_validate(
                agent, observation, retrieved, tick, tier, unmet, relationships, constraint_note=constraint
            )

        if isinstance(result, Rejection):
            return "idle", [], {}, "double validator rejection; safe default", visible, False, tier

        action_name, targets = result.action, result.targets
        params, reasoning = result.params, result.reasoning
        if action_name == "move_to":
            reasoning = self._start_walking(agent, params, reasoning)

        first_encounter = any(t in unmet for t in targets)
        return action_name, targets, params, reasoning, visible, first_encounter, tier

    def _start_walking(self, agent: Agent, params: dict[str, Any], reasoning: str) -> str:
        """A freshly-chosen `move_to` (About/spec.md §10: "consumed one tile
        per tick") computes its path and takes the first step immediately,
        rather than spending this whole tick just planning — later ticks
        then walk it via the Tier-0 shortcut above until it's exhausted.
        Unreachable/invalid destinations are handled, not rejected (About/
        plan.md T5.12): the agent simply doesn't move this tick.
        """
        dest = _parse_move_destination(params, self.world_map)
        if dest is None:
            return f"{reasoning} (no valid destination given)"
        path = find_path(self.world_map, (agent.position.x, agent.position.y), dest)
        if path is None:
            return f"{reasoning} (destination unreachable)"
        if not path:
            return f"{reasoning} (already at destination)"
        agent.current_path = path[1:]
        step = path[0]
        agent.position = agent.position.model_copy(update={"x": step[0], "y": step[1]})
        return reasoning

    async def _maybe_reflect(self, agent: Agent, tick: int) -> None:
        """Reflection doesn't consume the tick's one action (About/spec.md
        §5.3) — it runs alongside whatever the agent just did, not instead
        of it (see `runtime/reflection.py`'s docstring for why this bypasses
        the decision loop entirely)."""
        if not await is_reflection_due(self.session, agent.id, agent.last_reflection_tick, tick):
            return
        await ReflectionService.reflect(
            self.session,
            self.provider,
            self.rng,
            agent.id,
            self.bundles[agent.id],
            agent.last_reflection_tick,
            tick,
            tick_to_datetime(tick),
        )
        agent.last_reflection_tick = tick

    async def _maybe_compress(self, agent: Agent, tick: int) -> None:
        await compress_if_over_cap(
            self.session, self.provider, self.rng, agent.id, tick, tick_to_datetime(tick)
        )

    def _apply_goal_effects(
        self, agent: Agent, action_name: str, params: dict[str, Any], tier: int, tick: int
    ) -> None:
        """`form_goal`/`abandon_goal` are actions the model itself chose
        (About/spec.md §10's action table); `runtime/goals.py` just applies
        them. Formation only takes effect on the Tier-2 tick spec.md §4.2
        requires — a Tier-1 proposal of `form_goal` is accepted by the
        Validator (tier isn't a containment gate, see `safety/validator.py`)
        but has no effect here, same as any other action whose precondition
        the model got wrong.
        """
        if action_name == "form_goal" and tier == 2:
            description = str(params.get("description") or "an unspecified goal").strip()
            try:
                priority = max(0.0, min(1.0, float(params.get("priority", 0.5))))
            except (TypeError, ValueError):
                priority = 0.5
            try:
                target_agent_id = uuid.UUID(str(params.get("target_agent_id")))
            except (TypeError, ValueError):
                target_agent_id = None
            exclusive = bool(params.get("exclusive", False)) and target_agent_id is not None
            form_goal(agent, description, priority, tick, self.rng, target_agent_id, exclusive)
        elif action_name == "abandon_goal":
            try:
                goal_id = uuid.UUID(str(params.get("goal_id")))
            except (TypeError, ValueError):
                return
            abandon_goal(agent, goal_id)

    async def _maybe_couple_goals(
        self, agent: Agent, targets: list[uuid.UUID], tier: int, tick: int
    ) -> None:
        """Goal coupling (About/spec.md §4.2's adoption formula) is checked
        against actual Tier-2 interaction targets rather than the whole
        population every tick — Tier-2 ticks are already the rare,
        expensive ones (About/config.py's `TieringConfig` targets ~3%), so
        this stays bounded even at T5.1's 20-agent, 10,000-tick scale.
        """
        if tier != 2:
            return
        independence = self.bundles[agent.id].decision_weights.get("independence", 0.5)
        for target_id in targets:
            friend = self.agents_by_id.get(target_id)
            if friend is None or not friend.goals:
                continue
            edge = await get_edge(self.session, self.world_id, agent.id, target_id)
            if edge is None or edge.bond_state not in _COUPLING_ELIGIBLE_BOND_STATES:
                continue
            for goal in friend.goals:
                maybe_adopt_goal(agent, goal, target_id, independence, edge.trust, tick, self.rng)

    async def run_tick(self, tick: int) -> list[EventRecord]:
        self.exogenous_events_fired.extend(self.exogenous_scheduler.maybe_fire(tick))
        await self._maybe_scan_factions(tick)
        await self._maybe_update_conflict_damping(tick)
        await self._maybe_run_maintenance(tick)

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
                prune_stale_goals(agent, tick)
                await self._maybe_reflect(agent, tick)
                await self._maybe_compress(agent, tick)
            return events

        visible_by_agent, newly_met = await self._materialise_new_encounters(tick)

        decisions = await asyncio.gather(
            *[self._decide_for_agent(agent, tick, visible_by_agent[agent.id], newly_met[agent.id])
              for agent in self.agents]
        )

        events = []
        for agent, (action_name, targets, params, reasoning, visible, first_encounter, tier) in zip(
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
                bundles=self.bundles,
                params=params,
                damping_factor=self.conflict_damping_factor,
            )
            agent.last_tick = tick
            events.append(event)
            self._apply_goal_effects(agent, action_name, params, tier, tick)
            await self._maybe_couple_goals(agent, targets, tier, tick)
            prune_stale_goals(agent, tick)
            await self._maybe_reflect(agent, tick)
            await self._maybe_compress(agent, tick)
        return events

    async def run(self, num_ticks: int, start_tick: int = 0) -> list[EventRecord]:
        all_events: list[EventRecord] = []
        for t in range(start_tick, start_tick + num_ticks):
            all_events.extend(await self.run_tick(t))
        return all_events
