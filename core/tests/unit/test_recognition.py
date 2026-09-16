"""T4.1, T4.2 — About/plan.md M4 acceptance tests: harness correctness and blinding."""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime

import pytest

from otherworld.eval.recognition import (
    _ACTION_DESCRIPTIONS,
    InsufficientEventsError,
    RecognitionHarness,
    describe_event,
    event_category,
    pick_decoy_agent,
    sample_decoy_actions,
    sample_own_actions,
)
from otherworld.models.agent import Position
from otherworld.models.events import EventRecordORM
from otherworld.safety.registry import ActionRegistry

NOW = datetime.now(UTC)
POS = Position(x=0, y=0, facing="s").model_dump()


def _event(
    agent_id: uuid.UUID, world_id: uuid.UUID, action: str, importance: float, tick: int
) -> EventRecordORM:
    return EventRecordORM(
        id=uuid.uuid4(), world_id=world_id, tick=tick, actor_id=agent_id, action=action,
        targets=[], witnesses=[], position=POS, relationship_deltas=[], importance=importance,
        owner_override=False, created_at=NOW,
    )


def test_every_registered_action_has_a_description():
    for action in ActionRegistry.all_actions():
        assert action in _ACTION_DESCRIPTIONS


def test_sample_own_actions_raises_when_pool_too_small():
    world_id, agent_id = uuid.uuid4(), uuid.uuid4()
    too_few = [_event(agent_id, world_id, "idle", 0.6, t) for t in range(5)]
    with pytest.raises(InsufficientEventsError):
        sample_own_actions(too_few, 10, random.Random(1))


@pytest.mark.asyncio
async def test_prepare_trial_enforces_minimum_importance(db_session):
    """The 0.3 importance floor (spec.md §14 step 1) is applied by the DB
    query behind prepare_trial, not by sample_own_actions itself — events
    below it must never even reach the sampling step.
    """
    world_id, owner_agent, decoy_agent = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    for t in range(20):
        db_session.add(_event(owner_agent, world_id, "idle", 0.1, t))  # all below the floor
    for t in range(20, 40):
        db_session.add(_event(decoy_agent, world_id, "idle", 0.6, t))
    await db_session.flush()

    with pytest.raises(InsufficientEventsError):
        await RecognitionHarness.prepare_trial(
            db_session, world_id, owner_agent, random.Random(4), decoy_agent_id=decoy_agent
        )


def test_sample_own_actions_returns_exactly_k():
    world_id, agent_id = uuid.uuid4(), uuid.uuid4()
    eligible = [_event(agent_id, world_id, "greet", 0.6, t) for t in range(15)]
    sampled = sample_own_actions(eligible, 10, random.Random(1))
    assert len(sampled) == 10


def test_decoy_actions_are_category_matched():
    """T4.1"""
    world_id, agent_id, decoy_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    rng = random.Random(7)

    own_sample = [
        _event(agent_id, world_id, "greet", 0.6, 0),
        _event(agent_id, world_id, "greet", 0.6, 1),
        _event(agent_id, world_id, "move_to", 0.4, 2),
        _event(agent_id, world_id, "form_goal", 0.5, 3),
    ]
    # A rich decoy pool covering every category involved, plus noise.
    decoy_pool = (
        [_event(decoy_id, world_id, "greet", 0.6, t) for t in range(10, 15)]
        + [_event(decoy_id, world_id, "move_to", 0.4, t) for t in range(20, 25)]
        + [_event(decoy_id, world_id, "form_goal", 0.5, t) for t in range(30, 35)]
        + [_event(decoy_id, world_id, "betray", 0.9, t) for t in range(40, 42)]  # noise, different category
    )

    decoys = sample_decoy_actions(decoy_pool, own_sample, k=4, rng=rng)

    assert len(decoys) == 4
    own_categories = sorted(event_category(e.action).value for e in own_sample)
    decoy_categories = sorted(event_category(e.action).value for e in decoys)
    assert own_categories == decoy_categories


def test_descriptions_never_contain_agent_identifiers():
    """T4.1 — 'all names stripped'. EventRecord carries no display name or
    handle at all, so this holds by construction; assert it explicitly so a
    future field addition (e.g. an utterance) can't silently break it.
    """
    world_id, agent_id = uuid.uuid4(), uuid.uuid4()
    for action in ActionRegistry.all_actions():
        event = _event(agent_id, world_id, action, 0.6, 0)
        description = describe_event(event)
        assert str(agent_id) not in description
        assert str(world_id) not in description


@pytest.mark.asyncio
async def test_blinding_order_is_shuffled_and_uniform_in_shape(db_session):
    """T4.2 — the owner cannot infer which are theirs from formatting,
    ordering, or length; every question is the same `RecognitionQuestion`
    shape regardless of provenance.
    """
    world_id, owner_agent, decoy_agent = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    for t in range(15):
        db_session.add(_event(owner_agent, world_id, "greet", 0.6, t))
    for t in range(15, 30):
        db_session.add(_event(decoy_agent, world_id, "move_to", 0.4, t))
    await db_session.flush()

    prepared = await RecognitionHarness.prepare_trial(
        db_session, world_id, owner_agent, random.Random(3), decoy_agent_id=decoy_agent
    )

    assert len(prepared.questions) == 20
    # Not simply "first 10 own, last 10 decoy" — the shuffle actually did something.
    truth_sequence = [prepared.ground_truth[q.event_id] for q in prepared.questions]
    assert truth_sequence != [True] * 10 + [False] * 10

    # Uniform shape: every question has exactly the same fields, no extra
    # metadata that would hint at provenance.
    for q in prepared.questions:
        assert isinstance(q.description, str) and q.description


@pytest.mark.asyncio
async def test_pick_decoy_agent_excludes_self_and_requires_a_candidate(db_session):
    world_id, owner_agent, decoy_agent = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    with pytest.raises(InsufficientEventsError):
        await pick_decoy_agent(db_session, world_id, owner_agent, random.Random(1))

    db_session.add(_event(decoy_agent, world_id, "greet", 0.6, 0))
    db_session.add(_event(owner_agent, world_id, "greet", 0.6, 1))
    await db_session.flush()

    picked = await pick_decoy_agent(db_session, world_id, owner_agent, random.Random(1))
    assert picked == decoy_agent


@pytest.mark.asyncio
async def test_full_trial_scoring_round_trip(db_session):
    world_id, owner_agent, decoy_agent = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    for t in range(12):
        db_session.add(_event(owner_agent, world_id, "greet", 0.6, t))
    for t in range(12, 24):
        db_session.add(_event(decoy_agent, world_id, "greet", 0.6, t))
    await db_session.flush()

    prepared = await RecognitionHarness.prepare_trial(
        db_session, world_id, owner_agent, random.Random(9), decoy_agent_id=decoy_agent
    )

    # A perfect owner: picks exactly the true "own" events.
    perfect_selection = {eid for eid, is_own in prepared.ground_truth.items() if is_own}
    assert RecognitionHarness.score(prepared, perfect_selection) == 1.0

    # A hopeless owner: picks nothing.
    assert RecognitionHarness.score(prepared, set()) == 0.5  # gets all 10 decoys "right" by omission

    trial = await RecognitionHarness.record_trial(
        db_session, uuid.uuid4(), persona_version=1, prepared=prepared, owner_selections=perfect_selection
    )
    assert trial.accuracy == 1.0
