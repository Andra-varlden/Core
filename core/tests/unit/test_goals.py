"""About/plan.md M5: goal stack formation, abandonment, staleness pruning,
and the goal-coupling adoption formula (About/spec.md §4.2)."""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime

from otherworld.models.agent import Agent, AgentStatus, Goal, Position
from otherworld.runtime.goals import (
    abandon_goal,
    adoption_probability,
    form_goal,
    has_capacity,
    maybe_adopt_goal,
    prune_stale_goals,
)
from otherworld.social.engine import trust_normalised

NOW = datetime.now(UTC)


def _agent(goals: list[Goal] | None = None) -> Agent:
    return Agent(
        id=uuid.uuid4(), owner_id=uuid.uuid4(), persona_version=1, world_id=uuid.uuid4(),
        display_name="Nyx", status=AgentStatus.ACTIVE, position=Position(x=0, y=0, facing="s"),
        goals=goals or [], created_at=NOW,
    )


def _goal(**overrides) -> Goal:
    defaults = dict(
        id=uuid.uuid4(), description="test goal", priority=0.5, origin="self", created_tick=0
    )
    defaults.update(overrides)
    return Goal(**defaults)


def test_form_goal_adds_to_stack():
    agent = _agent()
    form_goal(agent, "learn to paint", 0.6, tick=10, rng=random.Random(1))
    assert len(agent.goals) == 1
    assert agent.goals[0].description == "learn to paint"
    assert agent.goals[0].origin == "self"


def test_form_goal_respects_max_concurrent():
    agent = _agent(goals=[_goal(), _goal(), _goal()])
    assert not has_capacity(agent)
    form_goal(agent, "one too many", 0.5, tick=10, rng=random.Random(1))
    assert len(agent.goals) == 3


def test_abandon_goal_removes_by_id():
    g1, g2 = _goal(), _goal()
    agent = _agent(goals=[g1, g2])
    abandon_goal(agent, g1.id)
    assert agent.goals == [g2]


def test_abandon_goal_is_a_noop_for_unknown_id():
    g1 = _goal()
    agent = _agent(goals=[g1])
    abandon_goal(agent, uuid.uuid4())
    assert agent.goals == [g1]


def test_prune_stale_goals_removes_goals_past_the_grace_period():
    fresh = _goal(created_tick=900)
    stale = _goal(created_tick=0)
    agent = _agent(goals=[fresh, stale])
    prune_stale_goals(agent, tick=1000)
    assert agent.goals == [fresh]


def test_prune_stale_goals_never_removes_a_completed_goal():
    completed = _goal(created_tick=0, completed_tick=5)
    agent = _agent(goals=[completed])
    prune_stale_goals(agent, tick=100_000)
    assert agent.goals == [completed]


def test_trust_normalised_maps_range_to_unit_interval():
    assert trust_normalised(-1.0) == 0.0
    assert trust_normalised(0.0) == 0.5
    assert trust_normalised(1.0) == 1.0


def test_adoption_probability_matches_spec_formula():
    assert abs(adoption_probability(independence=0.3, trust=0.5) - (0.7 * 0.75)) < 1e-9


def test_maybe_adopt_goal_succeeds_with_a_favourable_roll():
    agent = _agent()
    friend_goal = _goal()
    friend_id = uuid.uuid4()
    adopted = maybe_adopt_goal(
        agent, friend_goal, friend_id, independence=0.0, trust=1.0, tick=10, rng=random.Random(1)
    )
    assert adopted
    assert len(agent.goals) == 1
    assert agent.goals[0].origin == "adopted"
    assert agent.goals[0].adopted_from_agent_id == friend_id
    assert agent.goals[0].id == friend_goal.id


def test_maybe_adopt_goal_fails_with_an_unfavourable_roll():
    agent = _agent()
    friend_goal = _goal()
    adopted = maybe_adopt_goal(
        agent, friend_goal, uuid.uuid4(), independence=1.0, trust=-1.0, tick=10, rng=random.Random(1)
    )
    assert not adopted
    assert agent.goals == []


def test_maybe_adopt_goal_does_not_duplicate_an_already_adopted_goal():
    friend_goal = _goal()
    already_adopted = friend_goal.model_copy(update={"origin": "adopted"})
    agent = _agent(goals=[already_adopted])
    adopted = maybe_adopt_goal(
        agent, friend_goal, uuid.uuid4(), independence=0.0, trust=1.0, tick=10, rng=random.Random(1)
    )
    assert not adopted
    assert agent.goals == [already_adopted]


def test_maybe_adopt_goal_respects_capacity():
    agent = _agent(goals=[_goal(), _goal(), _goal()])
    adopted = maybe_adopt_goal(
        agent, _goal(), uuid.uuid4(), independence=0.0, trust=1.0, tick=10, rng=random.Random(1)
    )
    assert not adopted
    assert len(agent.goals) == 3
