"""Spawn real captured personas as living agents and simulate them.

    python -m otherworld.cli.run_world --world-name alpha --ticks 5000 --owners Jiths friend2

This is the bridge M4 needs: the Recognition Metric (otherworld.eval.recognition)
reads real EventRecords, and those only exist once a captured PersonaObject
(About/plan.md M1) has actually been compiled, bound, and run through the
tick loop (M2/M3). Reuses an existing World/Agent for each owner if one
already exists in the named world, so re-running just keeps simulating
forward rather than starting over — including after a mid-run crash (a
real provider's rate limit, About/plan.md's M4 pilot run): progress
resumes from the last actually-recorded EventRecord, and agent state is
persisted every `--commit-every` ticks rather than only at the very end.

Uses `otherworld.llm.factory.get_default_provider()` — a real provider
(currently Groq, About/spec.md §15.3) if `GROQ_API_KEY` is set, else the
deterministic mock. Be aware of what that means for M4 specifically if no
key is configured: the mock's decisions do not vary by persona trait at
all (see the M4 changelog entry in About/README.md), so a "trial" run
against mock-driven agents cannot be a real test of assumption A1 — only a
real Tier 1/2 model, reading the compiled identity prompt, can produce
behaviour that plausibly varies by persona.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select

from otherworld.db import async_session_factory
from otherworld.llm.factory import get_default_provider
from otherworld.models.agent import AgentORM, agent_from_orm, agent_to_orm
from otherworld.models.events import EventRecordORM
from otherworld.models.world import World, WorldORM, world_from_orm, world_to_orm
from otherworld.owner.service import get_or_create_owner
from otherworld.persona.binder import Binder
from otherworld.persona.compiler import Compiler
from otherworld.persona.service import get_latest_persona
from otherworld.runtime.clock import tick_to_datetime
from otherworld.runtime.scheduler import MultiAgentTickScheduler


async def _get_or_create_world(session, name: str, population_cap: int) -> World:
    row = (await session.execute(select(WorldORM).where(WorldORM.name == name))).scalar_one_or_none()
    if row is not None:
        return world_from_orm(row)
    world = World(
        id=uuid.uuid4(), name=name, width=1, height=1, current_tick=0, population=0,
        population_cap=population_cap, status="open", created_at=datetime.now(UTC),
    )
    session.add(world_to_orm(world))
    await session.flush()
    return world


async def _get_or_spawn_agent(session, world_id: uuid.UUID, handle: str, email: str):
    owner = await get_or_create_owner(session, handle, email)
    persona = await get_latest_persona(session, owner.id)
    if persona is None:
        raise ValueError(f"owner '{handle}' has no captured persona yet — run otherworld.cli.capture first")

    existing = (
        await session.execute(
            select(AgentORM).where(AgentORM.owner_id == owner.id, AgentORM.world_id == world_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return agent_from_orm(existing), Compiler.compile(persona)

    bundle = Compiler.compile(persona)
    agent = Binder.bind(
        bundle, owner_id=owner.id, persona_version=persona.version, world_id=world_id,
        display_name=handle, spawned_at=tick_to_datetime(0),
    )
    session.add(agent_to_orm(agent))
    await session.flush()
    return agent, bundle


async def _main(
    world_name: str,
    ticks: int,
    owner_specs: list[tuple[str, str]],
    commit_every: int,
    progress_every: int,
) -> None:
    async with async_session_factory() as session:
        world = await _get_or_create_world(session, world_name, population_cap=len(owner_specs))

        agents = []
        bundles = {}
        for handle, email in owner_specs:
            agent, bundle = await _get_or_spawn_agent(session, world.id, handle, email)
            agents.append(agent)
            bundles[agent.id] = bundle
        await session.commit()

        # Resume from the last actually-recorded tick, not `agent.last_tick`
        # — the latter was only ever persisted at the very end of a full
        # run (see the periodic commit below), so a crash mid-run (a real
        # provider's rate limit, About/plan.md's M4 pilot run) would
        # otherwise restart from tick 0 and re-simulate — re-spending real
        # LLM tokens on — a range that already has real EventRecords.
        last_event_tick = (
            await session.execute(
                select(func.max(EventRecordORM.tick)).where(EventRecordORM.world_id == world.id)
            )
        ).scalar_one_or_none()
        start_tick = (last_event_tick + 1) if last_event_tick is not None else 0

        seed = random.SystemRandom().randrange(2**32)
        provider = get_default_provider()
        scheduler = MultiAgentTickScheduler(
            session, provider, random.Random(seed), world.id, agents, bundles
        )

        total_events = 0
        for done, tick in enumerate(range(start_tick, start_tick + ticks), start=1):
            total_events += len(await scheduler.run_tick(tick))
            if done % commit_every == 0:
                # Persists agent position/goals/last_tick incrementally, not
                # just at the end — a mid-run crash now loses at most
                # `commit_every` ticks of in-memory agent state, not the
                # whole run's worth.
                for agent in agents:
                    await session.merge(agent_to_orm(agent))
                await session.commit()
            if progress_every and done % progress_every == 0:
                print(f"tick {tick} ({done}/{ticks} this run) | events so far: {total_events}", flush=True)

        for agent in agents:
            await session.merge(agent_to_orm(agent))
        await session.commit()

    end_tick = start_tick + ticks - 1
    print(f"Provider: {type(provider).__name__}")
    print(f"World '{world_name}' ({world.id}): ran ticks {start_tick}..{end_tick} (seed={seed})")
    print(f"{total_events} events written across {len(agents)} agents.")
    for handle, _email in owner_specs:
        print(f"  - {handle}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a shared world for one or more captured personas.")
    parser.add_argument("--world-name", required=True)
    parser.add_argument("--ticks", type=int, required=True)
    parser.add_argument(
        "--owners", nargs="+", metavar="HANDLE:EMAIL", required=True,
        help="One or more 'handle:email' pairs, each already captured via otherworld.cli.capture",
    )
    parser.add_argument(
        "--commit-every", type=int, default=1,
        help="Persist agent state every N ticks, so a crash (e.g. a real provider's rate limit) "
        "loses at most this many ticks of in-memory agent state, not the whole run. Defaults to "
        "every tick: an uncommitted tick's *flushed* EventRecords are still rolled back on a crash "
        "(confirmed live, About/plan.md's M4 pilot — a batch of 10 silently lost 6 free sleep-tick "
        "events to a rollback), and a real LLM tick costs real tokens, so there's no reason to "
        "batch commits against a cost this asymmetric.",
    )
    parser.add_argument(
        "--progress-every", type=int, default=10,
        help="Print a progress line every N ticks; 0 disables progress output",
    )
    args = parser.parse_args()
    owner_specs = []
    for spec in args.owners:
        handle, _, email = spec.partition(":")
        if not email:
            raise SystemExit(f"--owners entries must be 'handle:email', got: {spec!r}")
        owner_specs.append((handle, email))

    asyncio.run(_main(args.world_name, args.ticks, owner_specs, args.commit_every, args.progress_every))


if __name__ == "__main__":
    main()
