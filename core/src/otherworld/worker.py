"""The unattended simulation worker. See About/plan.md M6, T6.1/T6.2.

Runs every non-archived world forever, one real tick per real-time interval
(paced 1:1 — a tick's `in_world_minutes_per_tick` of fiction takes that many
real minutes to actually happen), rather than a fixed-count batch like
`cli.run_world`. That CLI stays as the manual/test-batch tool; this is what
Railway's worker service actually runs in production.

Deliberately does NOT reuse `settings.world.tick_seconds` for pacing, even
though the name suggests it — that field is only ever read by
`runtime/clock.py`'s `tick_to_datetime` to stamp each event's *fictional*
timestamp, and already disagrees numerically with `in_world_minutes_per_tick`
(both default to 10, but one names seconds and the other minutes — a
pre-existing inconsistency between the two "how much fiction is one tick"
concepts that predates this worker and isn't fixed here). Real-time pacing
uses `in_world_minutes_per_tick` specifically because that's the value the
sleep-window/day-night logic (`runtime/scheduler.py`'s `in_sleep_window`)
already treats as authoritative.
"""

from __future__ import annotations

import asyncio
import logging
import random
import signal
from datetime import UTC, datetime

from sqlalchemy import func, select

from otherworld.config import settings
from otherworld.db import async_session_factory
from otherworld.llm.factory import get_default_provider
from otherworld.models.agent import AgentORM, agent_from_orm, agent_to_orm
from otherworld.models.events import EventRecordORM
from otherworld.models.world import WorldORM, world_from_orm
from otherworld.persona.compiler import Compiler
from otherworld.persona.service import get_persona_version
from otherworld.runtime.scheduler import MultiAgentTickScheduler

logger = logging.getLogger("otherworld.worker")

REAL_SECONDS_PER_TICK = settings.world.in_world_minutes_per_tick * 60  # 1:1 real-time pacing

_shutdown_requested = False


def _request_shutdown(signum: int, _frame: object) -> None:
    global _shutdown_requested
    logger.info("received signal %s — finishing the current cycle, then stopping", signum)
    _shutdown_requested = True


async def _load_world_agents(session, world_id) -> tuple[list, dict] | None:
    """Returns (agents, bundles) for every agent already spawned in this
    world, or None if it has none yet — a world with an owner but no agent
    spawned (e.g. mid-onboarding) is skipped this cycle, not an error.
    """
    rows = (await session.execute(select(AgentORM).where(AgentORM.world_id == world_id))).scalars().all()
    if not rows:
        return None
    candidates = [agent_from_orm(row) for row in rows]
    agents = []
    bundles: dict = {}
    for agent in candidates:
        persona = await get_persona_version(session, agent.owner_id, agent.persona_version)
        if persona is None:
            # Excluded from `agents` too, not just `bundles` — the scheduler
            # requires every agent it's given to have a bundle; leaving it
            # in `agents` without one would crash the whole world's tick
            # instead of just sitting this one broken agent out.
            logger.warning("agent %s references a missing persona version — skipping it", agent.id)
            continue
        agents.append(agent)
        bundles[agent.id] = Compiler.compile(persona)
    return agents, bundles


async def _run_one_world_tick(session, provider, world_row) -> int:
    """Advances exactly one tick for this world. Returns the tick number run,
    or -1 if the world was skipped (no agents yet)."""
    world = world_from_orm(world_row)
    loaded = await _load_world_agents(session, world.id)
    if loaded is None:
        return -1
    agents, bundles = loaded

    last_event_tick = (
        await session.execute(select(func.max(EventRecordORM.tick)).where(EventRecordORM.world_id == world.id))
    ).scalar_one_or_none()
    tick = (last_event_tick + 1) if last_event_tick is not None else 0

    seed = random.SystemRandom().randrange(2**32)
    scheduler = MultiAgentTickScheduler(session, provider, random.Random(seed), world.id, agents, bundles)
    events = await scheduler.run_tick(tick)

    for agent in agents:
        await session.merge(agent_to_orm(agent))
    await session.commit()

    logger.info("world %r: tick %d ran (%d events)", world.name, tick, len(events))
    return tick


async def run_forever() -> None:
    provider = get_default_provider()
    logger.info(
        "worker starting — real-time pacing: %d real seconds per tick (%s provider)",
        REAL_SECONDS_PER_TICK, type(provider).__name__,
    )

    while not _shutdown_requested:
        cycle_start = datetime.now(UTC)
        async with async_session_factory() as session:
            worlds = (
                await session.execute(select(WorldORM).where(WorldORM.status != "archived"))
            ).scalars().all()
            for world_row in worlds:
                try:
                    await _run_one_world_tick(session, provider, world_row)
                except Exception:
                    # One world's failure (a bad persona, a transient Groq
                    # error the provider's own retry didn't absorb) must
                    # never take down every other world's simulation.
                    logger.exception("tick failed for world %r — will retry next cycle", world_row.name)
                    await session.rollback()

        elapsed = (datetime.now(UTC) - cycle_start).total_seconds()
        remaining = max(0.0, REAL_SECONDS_PER_TICK - elapsed)
        if remaining == 0.0:
            logger.warning(
                "cycle took %.1fs, longer than the %ds tick interval — falling behind real time",
                elapsed, REAL_SECONDS_PER_TICK,
            )
        for _ in range(int(remaining // 1)):
            if _shutdown_requested:
                break
            await asyncio.sleep(1)

    logger.info("worker stopped cleanly")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    signal.signal(signal.SIGTERM, _request_shutdown)
    signal.signal(signal.SIGINT, _request_shutdown)
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
