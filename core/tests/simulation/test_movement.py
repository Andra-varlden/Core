"""T5.12, T5.13 — About/plan.md M5: `move_to` is real movement, not a no-op.
`Agent.current_path` is computed once via A* and then consumed one tile per
tick as Tier 0 (About/architecture.md §12: never touching `LLMProvider`),
matching spec.md §10's "consumed one tile per tick"."""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime

import pytest

from otherworld.llm.protocol import Completion, Prompt
from otherworld.llm.providers.mock import MockLLMProvider
from otherworld.models.agent import Agent, AgentStatus, Position
from otherworld.models.persona import PersonaObject, TraitVector, VoiceProfile
from otherworld.persona.compiler import Compiler
from otherworld.runtime.clock import tick_to_datetime
from otherworld.runtime.scheduler import MultiAgentTickScheduler
from otherworld.world.map import WorldMap

NOW = datetime.now(UTC)
A_ID = uuid.UUID(int=1)
# Tick 0 falls in the sleep window (midnight-6am, `scheduler.in_sleep_window`)
# and never reaches the decision loop at all — tick 36 (hour 6, at 10
# in-world minutes/tick) is the first non-sleeping tick of the day.
_START_TICK = 36


def _persona() -> PersonaObject:
    return PersonaObject(
        id=uuid.uuid4(), owner_id=uuid.uuid4(), version=1,
        voice=VoiceProfile(verbosity=0.4, formality=0.5, humour_style="dry", profanity_baseline=0.1),
        values=TraitVector(), source_methods=["A"], created_at=NOW,
    )


def _agent(start=(0, 0)) -> Agent:
    return Agent(
        id=A_ID, owner_id=uuid.uuid4(), persona_version=1, world_id=uuid.uuid4(),
        display_name="A", status=AgentStatus.ACTIVE, position=Position(x=start[0], y=start[1], facing="s"),
        goals=[], current_path=[], last_tick=0, created_at=tick_to_datetime(0),
    )


class _MoveOnceProvider:
    """Proposes `move_to` toward (5, 5) on its first call, `idle` after."""

    def __init__(self) -> None:
        self._base = MockLLMProvider()
        self.calls = 0

    async def tier1(self, prompt: Prompt) -> Completion:
        self.calls += 1
        if self.calls == 1:
            return Completion(
                text='{"action": "move_to", "targets": [], "params": {"x": 5, "y": 5}, "reasoning": "go"}',
                input_tokens=1, output_tokens=1, model="test",
            )
        return Completion(
            text='{"action": "idle", "targets": [], "params": {}, "reasoning": "done"}',
            input_tokens=1, output_tokens=1, model="test",
        )

    async def tier2(self, prompt: Prompt) -> Completion:
        return await self.tier1(prompt)

    async def embed(self, text: str) -> list[float]:
        return await self._base.embed(text)


@pytest.mark.asyncio
async def test_move_to_computes_a_path_and_takes_the_first_step_immediately(db_session):
    world_id = uuid.uuid4()
    agent = _agent(start=(0, 0))
    bundles = {agent.id: Compiler.compile(_persona())}
    scheduler = MultiAgentTickScheduler(
        db_session, _MoveOnceProvider(), random.Random(1), world_id, [agent], bundles
    )

    await scheduler.run_tick(_START_TICK)

    assert (agent.position.x, agent.position.y) != (0, 0)
    assert agent.current_path  # more steps queued toward (5, 5)


@pytest.mark.asyncio
async def test_walking_a_stored_path_never_calls_the_llm_again(db_session):
    world_id = uuid.uuid4()
    agent = _agent(start=(0, 0))
    bundles = {agent.id: Compiler.compile(_persona())}
    provider = _MoveOnceProvider()
    scheduler = MultiAgentTickScheduler(db_session, provider, random.Random(1), world_id, [agent], bundles)

    await scheduler.run_tick(_START_TICK)
    calls_after_first_tick = provider.calls
    assert calls_after_first_tick == 1

    # Chebyshev distance from (0,0) to (5,5) is 5, so several more ticks are
    # needed — each should consume the stored path, not call the LLM.
    for tick in range(_START_TICK + 1, _START_TICK + 5):
        await scheduler.run_tick(tick)
    assert provider.calls == calls_after_first_tick  # still 1: no further LLM calls
    assert scheduler.tier0_walk_count >= 4


@pytest.mark.asyncio
async def test_move_to_reaches_its_destination_and_then_asks_again(db_session):
    world_id = uuid.uuid4()
    agent = _agent(start=(0, 0))
    bundles = {agent.id: Compiler.compile(_persona())}
    provider = _MoveOnceProvider()
    scheduler = MultiAgentTickScheduler(db_session, provider, random.Random(1), world_id, [agent], bundles)

    for tick in range(_START_TICK, _START_TICK + 6):  # Chebyshev distance 5 => arrives well within 6 ticks
        await scheduler.run_tick(tick)

    assert (agent.position.x, agent.position.y) == (5, 5)
    assert agent.current_path == []
    assert provider.calls == 2  # one move_to, then one fresh decision once the path ran out


@pytest.mark.asyncio
async def test_move_to_an_unreachable_destination_is_handled_not_rejected(db_session):
    """(5, 5) is a valid, walkable tile — it's just walled off from (0, 0),
    so A* legitimately finds no path (spec.md's "unreachable destinations
    handled", not merely an out-of-bounds coordinate rejected up front)."""
    world_id = uuid.uuid4()
    agent = _agent(start=(0, 0))
    bundles = {agent.id: Compiler.compile(_persona())}

    class _UnreachableProvider(_MoveOnceProvider):
        async def tier1(self, prompt: Prompt) -> Completion:
            self.calls += 1
            return Completion(
                text='{"action": "move_to", "targets": [], "params": {"x": 5, "y": 5}, "reasoning": "go"}',
                input_tokens=1, output_tokens=1, model="test",
            )

    blocked = {(x, y) for x in range(10) for y in range(10)} - {(0, 0), (5, 5)}
    world_map = WorldMap(width=10, height=10, blocked=blocked)
    scheduler = MultiAgentTickScheduler(
        db_session, _UnreachableProvider(), random.Random(1), world_id, [agent], bundles, world_map=world_map
    )

    events = await scheduler.run_tick(_START_TICK)

    assert (agent.position.x, agent.position.y) == (0, 0)  # didn't move
    assert agent.current_path == []
    assert events[0].action == "move_to"  # still resolved as an event, not a crash/rejection
