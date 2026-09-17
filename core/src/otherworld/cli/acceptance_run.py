"""About/plan.md T5.1: a synthetic 20-agent, N-tick run to exercise M5's
full social system at scale, and report the acceptance-test metrics
(T5.3-T5.9, T5.12-T5.13) against real Postgres data.

    python -m otherworld.cli.acceptance_run --agents 20 --ticks 10000

Uses `ScenarioMockProvider` (About/llm/providers/scenario_mock.py), not a
real LLM or the plain `MockLLMProvider` — see that module's docstring for
why: `MockLLMProvider` alone never lets relationships progress past first
contact, which would make T5.3-T5.8 vacuous, and a real provider at
20 agents x 10,000 ticks (200,000 agent-ticks) is infeasible on cost, rate
limits and wall-clock time, and unnecessary — determinism (T5.2) is a
mechanism-level guarantee that doesn't depend on which deterministic
provider is used.

Movement (`move_to` actually consuming an A* path tick-by-tick) was
deliberately not wired this milestone (About/plan.md's M5 status) — agents
stay at their spawn position for the whole run. Spawning them as several
small, well-separated clusters (not one shared blob, and not spread
uniformly across the full 60x60 grid) is what makes that a reasonable
stand-in: it keeps typical witness counts small and realistic (a handful of
nearby agents, About/spec.md §9.1's `perception_radius`, not all 20 mutually
visible at once — the latter was tried first and produced O(agents^2)
witnessed-memory writes per tick, which is neither realistic nor what the
spec's zone-based dispersion intends) while still giving each cluster
enough internal density to form real bonds, conflicts and — with multiple
separated clusters — actual distinct factions rather than one giant clique.
Known, stated limitation of this specific run either way: it doesn't
exercise spatial dispersion *dynamics* (agents never move between
clusters), which is separately covered by `tests/unit/test_pathfinding.py`.
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import random
import time
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from otherworld.db import async_session_factory
from otherworld.llm.providers.scenario_mock import ScenarioMockProvider
from otherworld.models.agent import Agent, AgentORM, AgentStatus, Position, agent_from_orm, agent_to_orm
from otherworld.models.events import EventRecordORM
from otherworld.models.memory import MemoryKind, MemoryRecordORM
from otherworld.models.persona import PersonaObject, TraitVector, VoiceProfile
from otherworld.models.relationship import BondState, RelationshipEdgeORM
from otherworld.models.world import World, WorldORM, world_from_orm, world_to_orm
from otherworld.persona.compiler import AgentBundle, Compiler
from otherworld.persona.service import get_latest_persona, save_persona
from otherworld.runtime.scheduler import MultiAgentTickScheduler, in_sleep_window

_TRAIT_NAMES = list(TraitVector.model_fields.keys())
_CLUSTER_RADIUS = 4  # agents spawn within +/- this many tiles of their cluster's centre
# Centres are Chebyshev-distance 12 apart pairwise. With radius 4, that puts
# typical cross-cluster distance around 12 (outside perception_radius=8, so
# clusters mostly don't see each other) but occasionally as close as 4 for
# agents who land near a shared edge — enough for the rare cross-cluster
# contact that can turn into a faction pair, without collapsing into one
# mutually-visible blob (About/spec.md §9.2's "Market square... high-traffic
# social hub" is the real-world analogue of that occasional overlap).
_CLUSTER_CENTRES = ((10, 10), (22, 10), (10, 22), (22, 22))


def _make_persona(rng, owner_id: uuid.UUID, now: datetime) -> PersonaObject:
    traits = {name: round(rng.uniform(0.1, 0.9), 2) for name in _TRAIT_NAMES}
    return PersonaObject(
        id=uuid.uuid4(), owner_id=owner_id, version=1,
        voice=VoiceProfile(
            verbosity=rng.uniform(0.2, 0.8), formality=rng.uniform(0.2, 0.8),
            humour_style=rng.choice(["dry", "warm", "absurd", "sarcastic", "none"]),
            profanity_baseline=rng.uniform(0.0, 0.5),
        ),
        values=TraitVector(**traits), source_methods=["A"], created_at=now,
    )


def _make_agent(
    agent_id: uuid.UUID,
    owner_id: uuid.UUID,
    world_id: uuid.UUID,
    name: str,
    center: tuple[int, int],
    rng,
    now: datetime,
) -> Agent:
    cx, cy = center
    x = max(0, min(59, cx + rng.randint(-_CLUSTER_RADIUS, _CLUSTER_RADIUS)))
    y = max(0, min(59, cy + rng.randint(-_CLUSTER_RADIUS, _CLUSTER_RADIUS)))
    return Agent(
        id=agent_id, owner_id=owner_id, persona_version=1, world_id=world_id,
        display_name=name, status=AgentStatus.ACTIVE, position=Position(x=x, y=y, facing="s"),
        goals=[], current_path=[], last_tick=0, created_at=now,
    )


async def _report(session: AsyncSession, world_id: uuid.UUID) -> str:
    edges = (
        await session.execute(select(RelationshipEdgeORM).where(RelationshipEdgeORM.world_id == world_id))
    ).scalars().all()

    bond_counts = Counter(e.bond_state for e in edges)
    total_edges = len(edges)
    friend_plus = bond_counts[BondState.FRIEND.value] + bond_counts[BondState.CLOSE_BOND.value]
    close_bond_share = bond_counts[BondState.CLOSE_BOND.value] / total_edges if total_edges else 0.0
    friend_plus_share = friend_plus / total_edges if total_edges else 0.0

    triggers_seen: Counter[str] = Counter()
    resolutions_seen: Counter[str] = Counter()
    scarred_pairs = 0
    for e in edges:
        themes: Counter[str] = Counter()
        for record in e.conflict_log:
            triggers_seen[record["trigger"]] += 1
            if record["resolution"]:
                resolutions_seen[record["resolution"]] += 1
            themes[record["theme"]] += 1
        if any(count >= 2 for count in themes.values()):
            scarred_pairs += 1

    episodic_counts = (
        await session.execute(
            select(MemoryRecordORM.agent_id, func.count())
            .where(MemoryRecordORM.kind == MemoryKind.EPISODIC.value)
            .group_by(MemoryRecordORM.agent_id)
        )
    ).all()
    max_episodic = max((c for _, c in episodic_counts), default=0)

    belief_stats = (
        await session.execute(
            select(func.count(), func.max(MemoryRecordORM.hop_count)).where(
                MemoryRecordORM.kind == MemoryKind.BELIEF.value
            )
        )
    ).one()
    belief_count, max_hop = belief_stats

    lines = [
        f"Total edges materialised: {total_edges}",
        f"Bond state distribution: {dict(bond_counts)}",
        f"Friend+ share: {friend_plus_share:.1%} (T5.3 target < 40%)",
        f"Close bond share: {close_bond_share:.1%} (T5.4 target <= 5%)",
        f"Conflict triggers observed: {dict(triggers_seen)} (T5.6: all 5 expected)",
        f"Terminal transitions observed: {dict(resolutions_seen)} (T5.7: repaired/broken/feud each >= 1)",
        f"Edges with a scarred (repeated-theme) conflict: {scarred_pairs} (T5.8 signal)",
        f"Max episodic memories on any one agent: {max_episodic} (T5.9 cap is 2000)",
        f"Total beliefs formed/propagated: {belief_count}, max hop_count: {max_hop} (T5.10: must be <= 3)",
    ]
    return "\n".join(lines)


async def _load_existing_world(
    session: AsyncSession, world_id: uuid.UUID
) -> tuple[World, list[Agent], dict[uuid.UUID, AgentBundle], int]:
    """Resumes an interrupted run by continuing from the world's persisted
    state (agents, edges, memories) — but NOT its RNG state, which isn't
    persisted anywhere. The resumed portion is a valid, independent
    continuation for About/plan.md T5.1's purposes (completing at scale,
    observing the resulting distributions), not a byte-identical
    continuation of what an uninterrupted run would have produced —
    determinism (T5.2) is verified separately, on short, uninterrupted runs.

    `start_tick` comes from `event_records.tick`, not `agent.last_tick`:
    the latter was only ever written back once, at the very end of a
    successful run (see the fix alongside this one) — worthless for
    resuming after exactly the kind of interruption (killed for memory,
    stopped for a stuck DB) this option exists to recover from.
    """
    row = (await session.execute(select(WorldORM).where(WorldORM.id == world_id))).scalar_one_or_none()
    if row is None:
        raise SystemExit(f"--world-id {world_id}: no such world")
    world = world_from_orm(row)

    agent_rows = (
        await session.execute(select(AgentORM).where(AgentORM.world_id == world_id))
    ).scalars().all()
    agents = [agent_from_orm(r) for r in agent_rows]

    bundles: dict[uuid.UUID, AgentBundle] = {}
    for agent in agents:
        persona = await get_latest_persona(session, agent.owner_id)
        if persona is None:
            raise SystemExit(f"agent {agent.id}: no persisted persona to resume from")
        bundles[agent.id] = Compiler.compile(persona)

    last_event_tick = (
        await session.execute(
            select(func.max(EventRecordORM.tick)).where(EventRecordORM.world_id == world_id)
        )
    ).scalar_one_or_none()
    start_tick = (last_event_tick + 1) if last_event_tick is not None else 0
    return world, agents, bundles, start_tick


async def _create_new_world(
    session: AsyncSession, num_agents: int, seed: int
) -> tuple[World, list[Agent], dict[uuid.UUID, AgentBundle]]:
    setup_rng = random.Random(seed)
    now = datetime.now(UTC)
    world_id = uuid.uuid4()
    world = World(
        id=world_id, name=f"acceptance-run-{world_id.hex[:8]}", width=60, height=60, current_tick=0,
        population=num_agents, population_cap=num_agents, status="open", created_at=now,
    )
    session.add(world_to_orm(world))

    agents: list[Agent] = []
    bundles: dict[uuid.UUID, AgentBundle] = {}
    for i in range(num_agents):
        agent_id = uuid.uuid4()
        owner_id = uuid.uuid4()
        persona = _make_persona(setup_rng, owner_id, now)
        await save_persona(session, persona)  # so a later --world-id resume can recompile the same bundle
        bundle = Compiler.compile(persona)
        center = _CLUSTER_CENTRES[i % len(_CLUSTER_CENTRES)]
        agent = _make_agent(agent_id, owner_id, world_id, f"agent-{i:02d}", center, setup_rng, now)
        session.add(agent_to_orm(agent))
        agents.append(agent)
        bundles[agent.id] = bundle
    await session.commit()
    return world, agents, bundles


async def _main(
    num_agents: int,
    ticks: int,
    seed: int,
    progress_every: int,
    commit_every: int,
    trace_file: Path,
    resume_world_id: uuid.UUID | None,
) -> None:
    async with async_session_factory() as session:
        if resume_world_id is not None:
            world, agents, bundles, start_tick = await _load_existing_world(session, resume_world_id)
        else:
            world, agents, bundles = await _create_new_world(session, num_agents, seed)
            start_tick = 0
        world_id, world_name = world.id, world.name

        scheduler = MultiAgentTickScheduler(
            session, ScenarioMockProvider(), random.Random(seed), world_id, agents, bundles
        )

        start = time.perf_counter()
        total_events = 0
        tier_counts: Counter[int] = Counter()
        trace_file.parent.mkdir(parents=True, exist_ok=True)
        for done, tick in enumerate(range(start_tick, start_tick + ticks), start=1):
            events = await scheduler.run_tick(tick)
            total_events += len(events)
            if done % commit_every == 0:
                for agent in agents:
                    await session.merge(agent_to_orm(agent))
                await session.commit()
                # `db.py`'s session factory sets `expire_on_commit=False`,
                # which means commit alone does *not* release anything —
                # every ORM object this session has ever touched (tens of
                # thousands of memory records, each carrying a 1536-float
                # embedding) stays pinned in its identity map for the
                # session's whole lifetime. Over a single long-lived session
                # spanning 10,000 ticks that is real, unbounded *process*
                # memory growth — About/plan.md T5.1's own criterion — and
                # is what actually got this run killed by the OS for low
                # memory the first time through, not anything about the
                # database itself. `expunge_all()` detaches everything so
                # it can be garbage collected; safe here because nothing
                # in the tick loop holds onto ORM instances across ticks
                # (Agent/RelationshipEdge/MemoryRecord are all plain
                # Pydantic objects, not the ORM rows themselves).
                session.expunge_all()
                gc.collect()  # the system this ran on had ~1GB headroom at idle; don't wait on it
                # `TraceLog.entries` grows one entry per Tier-1/2 decision
                # with no cap of its own (About/runtime/trace.py) — flushing
                # and clearing it periodically is what keeps *this run's*
                # own process memory bounded, distinct from what T5.1 is
                # actually checking (the database's growth).
                tier_counts.update(t.tier_used for t in scheduler.trace_log.entries)
                scheduler.trace_log.write_jsonl(trace_file)
                scheduler.trace_log.entries.clear()
            if done % progress_every == 0:
                elapsed = time.perf_counter() - start
                rate = done / elapsed
                eta = (ticks - done) / rate if rate > 0 else float("inf")
                print(
                    f"tick {tick} (world tick; {done}/{ticks} this run) | {elapsed:.1f}s elapsed | "
                    f"{rate:.2f} ticks/s | ETA {eta:.0f}s | events so far: {total_events}",
                    flush=True,
                )
        tier_counts.update(t.tier_used for t in scheduler.trace_log.entries)
        scheduler.trace_log.write_jsonl(trace_file)
        scheduler.trace_log.entries.clear()
        await session.commit()

        for agent in agents:
            await session.merge(agent_to_orm(agent))
        await session.commit()

        elapsed = time.perf_counter() - start
        # `TraceLog` only records Tier 1/2 decisions (About/runtime/trace.py
        # — Tier 0 never touches `DecisionEngine`); the sleep window and
        # walking a stored path (`scheduler.tier0_walk_count`, About/plan.md
        # M5's real-movement wiring) are this run's Tier-0 behaviours, so
        # Tier 0's count is computed directly rather than from a trace that
        # was never written for them.
        tier0_ticks = sum(1 for t in range(start_tick, start_tick + ticks) if in_sleep_window(t))
        tier_counts[0] = tier0_ticks * len(agents) + scheduler.tier0_walk_count
        total_decisions = sum(tier_counts.values())
        tier_shares = {
            tier: (count / total_decisions if total_decisions else 0.0) for tier, count in tier_counts.items()
        }

        print("\n=== Run complete ===")
        print(f"World: {world_name} ({world_id})")
        print(f"{len(agents)} agents, world ticks {start_tick}..{start_tick + ticks - 1}, seed={seed}")
        print(f"Wall clock: {elapsed:.1f}s ({ticks / elapsed:.2f} ticks/s)")
        print(f"Total events: {total_events}")
        print(f"Tier shares (of {total_decisions} decisions): {tier_shares} (T5.13 target: 0>=0.80, 2<=0.05)")
        print(f"Tier-0 walking steps: {scheduler.tier0_walk_count}")
        print(f"Exogenous events fired: {len(scheduler.exogenous_events_fired)}")
        print(
            f"Cliques at last scan: {len(scheduler.cliques)}, "
            f"faction pairs: {len(scheduler.faction_pairs)}, "
            f"exclusion signals: {len(scheduler.exclusion_signals)}"
        )
        print(
            f"Conflict damping factor at end of run: {scheduler.conflict_damping_factor:.3f} "
            "(T5.5; 1.0 = no damping)"
        )
        print()
        print(await _report(session, world_id))


def main() -> None:
    parser = argparse.ArgumentParser(description="M5 acceptance-scale run (T5.1).")
    parser.add_argument("--agents", type=int, default=20, help="ignored when --world-id resumes a run")
    parser.add_argument("--ticks", type=int, default=10_000, help="how many more ticks to run this call")
    parser.add_argument("--seed", type=int, default=42, help="ignored when --world-id resumes a run")
    parser.add_argument("--progress-every", type=int, default=200)
    parser.add_argument("--commit-every", type=int, default=200)
    parser.add_argument("--trace-file", type=Path, default=Path("acceptance_run_trace.jsonl"))
    parser.add_argument(
        "--world-id", type=uuid.UUID, default=None,
        help="resume an existing world from its agents' last_tick instead of creating a new one",
    )
    args = parser.parse_args()
    asyncio.run(
        _main(
            args.agents, args.ticks, args.seed, args.progress_every, args.commit_every, args.trace_file,
            args.world_id,
        )
    )


if __name__ == "__main__":
    main()
