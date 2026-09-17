"""The goal stack and goal coupling. See About/spec.md §4.2, §2.

Formation (`form_goal`) and abandonment (`abandon_goal`) are actions the
model itself proposes through the normal decision loop — About/spec.md's
action semantics table ties both to the goal stack directly ("Under max
concurrent goals" / "Goal exists"). Staleness pruning, by contrast, is
system-driven, for the same reason `runtime/reflection.py` and
`runtime/compression.py` are: "abandon this after N ticks of no progress" is
a mechanical check, not something that needs an LLM's judgement, and an
agent has no way to know it's been exactly `stale_ticks` since a goal was
formed without being told anyway.

These functions mutate the `Agent` they're given in place, matching
`runtime/scheduler.py`'s existing convention for agent-lifetime state
(`agent.last_tick`, `agent.last_reflection_tick`) — unlike
`RelationshipEdge`, which is re-read and re-saved every tick and so stays
immutable/copy-on-write, an `Agent` is held in memory for the scheduler's
whole run.
"""

from __future__ import annotations

import random
import uuid

from otherworld.config import settings
from otherworld.models.agent import Agent, Goal
from otherworld.runtime.determinism import seeded_uuid
from otherworld.social.engine import trust_normalised


def has_capacity(agent: Agent) -> bool:
    return len(agent.goals) < settings.goals.max_concurrent


def form_goal(
    agent: Agent,
    description: str,
    priority: float,
    tick: int,
    rng: random.Random,
    target_agent_id: uuid.UUID | None = None,
    exclusive: bool = False,
) -> None:
    if not has_capacity(agent):
        return
    goal = Goal(
        id=seeded_uuid(rng), description=description, priority=priority, origin="self", created_tick=tick,
        target_agent_id=target_agent_id, exclusive=exclusive,
    )
    agent.goals = [*agent.goals, goal]


def abandon_goal(agent: Agent, goal_id: uuid.UUID) -> None:
    agent.goals = [g for g in agent.goals if g.id != goal_id]


def prune_stale_goals(agent: Agent, tick: int) -> None:
    agent.goals = [
        g for g in agent.goals
        if g.completed_tick is not None or tick - g.created_tick <= settings.goals.stale_ticks
    ]


def adoption_probability(independence: float, trust: float) -> float:
    return (1 - independence) * trust_normalised(trust)


def maybe_adopt_goal(
    agent: Agent,
    friend_goal: Goal,
    friend_id: uuid.UUID,
    independence: float,
    trust: float,
    tick: int,
    rng: random.Random,
) -> bool:
    """One roll against `adoption_probability`. Returns whether it adopted.
    No-op if the agent is at capacity or already carries this exact goal
    (by id — the id is copied from the friend's goal, so re-encountering the
    same still-active goal doesn't roll again).
    """
    if not has_capacity(agent) or any(g.id == friend_goal.id for g in agent.goals):
        return False
    if rng.random() >= adoption_probability(independence, trust):
        return False
    adopted = Goal(
        id=friend_goal.id,
        description=friend_goal.description,
        priority=friend_goal.priority,
        origin="adopted",
        adopted_from_agent_id=friend_id,
        created_tick=tick,
    )
    agent.goals = [*agent.goals, adopted]
    return True
