"""Administer a Recognition Metric trial to a real owner. See About/spec.md §14.

    python -m otherworld.cli.recognition --world-name alpha --handle Jiths --email jithindranaath2@gmail.com

Requires that `otherworld.cli.run_world` has already been run for this
world with at least two owners' agents, long enough that each has 10+
events at importance >= 0.3 (About/eval/recognition.py's
MIN_SAMPLE_IMPORTANCE / SAMPLE_SIZE).
"""

from __future__ import annotations

import argparse
import asyncio
import random

from sqlalchemy import select

from otherworld.db import async_session_factory
from otherworld.eval.recognition import InsufficientEventsError, RecognitionHarness, interpret
from otherworld.models.agent import AgentORM, agent_from_orm
from otherworld.models.world import WorldORM, world_from_orm
from otherworld.owner.service import get_or_create_owner
from otherworld.persona.service import get_latest_persona


async def _main(world_name: str, handle: str, email: str) -> None:
    async with async_session_factory() as session:
        world_row = (
            await session.execute(select(WorldORM).where(WorldORM.name == world_name))
        ).scalar_one_or_none()
        if world_row is None:
            raise SystemExit(f"no world named '{world_name}' — run otherworld.cli.run_world first")
        world = world_from_orm(world_row)

        owner = await get_or_create_owner(session, handle, email)
        persona = await get_latest_persona(session, owner.id)
        if persona is None:
            raise SystemExit(f"'{handle}' has no captured persona — run otherworld.cli.capture first")

        agent_row = (
            await session.execute(
                select(AgentORM).where(AgentORM.owner_id == owner.id, AgentORM.world_id == world.id)
            )
        ).scalar_one_or_none()
        if agent_row is None:
            raise SystemExit(
                f"'{handle}' has no agent in world '{world_name}' — run otherworld.cli.run_world first"
            )
        agent = agent_from_orm(agent_row)

        try:
            prepared = await RecognitionHarness.prepare_trial(session, world.id, agent.id, random.Random())
        except InsufficientEventsError as exc:
            raise SystemExit(
                f"Not enough data for a trial yet: {exc}\n"
                "Run more ticks with otherworld.cli.run_world for this world first."
            ) from exc

        print(f"\n{len(prepared.questions)} actions follow, in random order.")
        print("For each one: was this YOUR agent, or the other one? [y/n]\n")

        selections = set()
        for i, question in enumerate(prepared.questions, start=1):
            print(f"{i:2d}. {question.description}")
            while True:
                answer = input("    yours? [y/n] > ").strip().lower()
                if answer in ("y", "n"):
                    break
                print("    please answer y or n")
            if answer == "y":
                selections.add(question.event_id)

        trial = await RecognitionHarness.record_trial(
            session, owner.id, persona.version, prepared, selections
        )
        await session.commit()

    print(f"\nAccuracy: {trial.accuracy:.0%}")
    print(interpret(trial.accuracy))


def main() -> None:
    parser = argparse.ArgumentParser(description="Administer a Recognition Metric trial (About/spec.md §14).")
    parser.add_argument("--world-name", required=True)
    parser.add_argument("--handle", required=True)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    asyncio.run(_main(args.world_name, args.handle, args.email))


if __name__ == "__main__":
    main()
