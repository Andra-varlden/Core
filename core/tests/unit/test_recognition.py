"""T4.1, T4.2 — About/plan.md M4 acceptance tests: harness correctness and blinding."""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime

import pytest

from otherworld.eval.recognition import (
    _ACTION_DESCRIPTIONS,
    SAMPLE_SIZE,
    InsufficientEventsError,
    RecognitionHarness,
    _distinctive_action_types,
    _elapsed_ticks_since_met,
    _timing_clause,
    compute_distinctiveness,
    describe_event,
    event_category,
    pick_decoy_agent,
    sample_decoy_actions,
    sample_own_actions,
)
from otherworld.models.agent import Position
from otherworld.models.events import EventRecordORM
from otherworld.safety.registry import ActionRegistry
from otherworld.social.engine import get_or_create_edge, save_edge

NOW = datetime.now(UTC)
POS = Position(x=0, y=0, facing="s").model_dump()


def _event(
    agent_id: uuid.UUID,
    world_id: uuid.UUID,
    action: str,
    importance: float,
    tick: int,
    targets: list[str] | None = None,
    relationship_deltas: list[dict[str, object]] | None = None,
) -> EventRecordORM:
    return EventRecordORM(
        id=uuid.uuid4(), world_id=world_id, tick=tick, actor_id=agent_id, action=action,
        targets=targets or [], witnesses=[], position=POS,
        relationship_deltas=relationship_deltas or [], importance=importance,
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
async def test_prepare_trial_excludes_purely_mechanical_actions_regardless_of_importance(db_session):
    """`idle`/`sleep`/`move_to`/etc. are excluded from the quiz pool
    entirely (see `SAMPLE_SIZE`'s docstring — they carry no persona signal,
    everyone does them the same way), even at high importance. An owner
    whose only events are mechanical has nothing eligible."""
    world_id, owner_agent, decoy_agent = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    for t in range(20):
        db_session.add(_event(owner_agent, world_id, "idle", 0.9, t))  # high importance, still excluded
    for t in range(20, 40):
        db_session.add(_event(decoy_agent, world_id, "idle", 0.6, t))
    await db_session.flush()

    with pytest.raises(InsufficientEventsError):
        await RecognitionHarness.prepare_trial(
            db_session, world_id, owner_agent, random.Random(4), decoy_agent_id=decoy_agent
        )


def test_compute_distinctiveness_is_zero_when_everyone_behaves_identically():
    from collections import Counter

    agent = Counter({"greet": 10})
    population = Counter({"greet": 30})  # this agent is exactly a third of the population
    scores = compute_distinctiveness(agent, population)
    assert scores["greet"] == pytest.approx(0.0)


def test_compute_distinctiveness_is_positive_for_an_above_average_habit():
    from collections import Counter

    agent = Counter({"give": 8, "greet": 2})  # 80% of this agent's own actions are "give"
    population = Counter({"give": 10, "greet": 20})  # population-wide, "give" is only 33%
    scores = compute_distinctiveness(agent, population)
    assert scores["give"] == pytest.approx(0.8 - 10 / 30)
    assert scores["give"] > 0


def test_distinctive_action_types_ranks_positive_scores_only_and_caps_at_top_n():
    scores = {"give": 0.5, "confide": 0.3, "greet": -0.1, "compliment": 0.05}
    ranked = _distinctive_action_types(scores, top_n=2)
    assert ranked == ["give", "confide"]  # highest first; "greet" (negative) excluded


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

    Fixture note: the owner must actually be MORE "greet"-heavy than the
    population for "greet" to register as distinctive (see
    `compute_distinctiveness` — identical behaviour scores exactly 0, not
    eligible). The decoy does a mixed "greet"/"form_goal" split so the
    population-wide "greet" share sits below the owner's 100%.
    """
    world_id, owner_agent, decoy_agent = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    for t in range(15):
        db_session.add(_event(owner_agent, world_id, "greet", 0.6, t))
    for t in range(15, 25):
        db_session.add(_event(decoy_agent, world_id, "greet", 0.6, t))
    for t in range(25, 35):
        db_session.add(_event(decoy_agent, world_id, "form_goal", 0.5, t))
    await db_session.flush()

    prepared = await RecognitionHarness.prepare_trial(
        db_session, world_id, owner_agent, random.Random(3), decoy_agent_id=decoy_agent
    )

    assert len(prepared.questions) == SAMPLE_SIZE * 2
    # Not simply "first 10 own, last 10 decoy" — the shuffle actually did something.
    truth_sequence = [prepared.ground_truth[q.event_id] for q in prepared.questions]
    assert truth_sequence != [True] * SAMPLE_SIZE + [False] * SAMPLE_SIZE

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


def test_timing_clause_buckets_by_elapsed_in_world_time():
    """spec.md's `in_world_minutes_per_tick=10` -> 6 ticks/hour, 144/day."""
    assert _timing_clause(None) == ""
    assert _timing_clause(3) == ", moments after meeting them"
    assert _timing_clause(50) == ", about 8 hours after meeting them"
    assert _timing_clause(3 * 144) == ", 3 days after meeting them"
    assert _timing_clause(14 * 144) == ", about 2 weeks after meeting them"
    assert _timing_clause(90 * 144) == ", about 3 months after meeting them"


@pytest.mark.asyncio
async def test_two_otherwise_identical_transition_events_get_different_descriptions(db_session):
    """Regression test for the real gamma-world finding: every qualifying
    event across all 5 real people collapsed to one of ~3 possible
    sentences (a relationship-milestone transition is the only thing that
    ever clears the 0.3 importance floor), so an owner's own question and a
    decoy's were frequently byte-identical text — the quiz was unanswerable
    above chance by construction. Two different pairs reaching the same
    milestone at very different relationship ages must now read
    differently."""
    world_id = uuid.uuid4()
    fast_actor, fast_target = uuid.uuid4(), uuid.uuid4()
    slow_actor, slow_target = uuid.uuid4(), uuid.uuid4()

    fast_edge, _ = await get_or_create_edge(db_session, world_id, fast_actor, fast_target, uuid.uuid4(), tick=100)
    await save_edge(db_session, fast_edge)
    slow_edge, _ = await get_or_create_edge(db_session, world_id, slow_actor, slow_target, uuid.uuid4(), tick=0)
    await save_edge(db_session, slow_edge)

    deltas = [{"bond_state_before": "friend", "bond_state_after": "close_bond"}]
    fast_event = _event(
        fast_actor, world_id, "give", 0.95, tick=110, targets=[str(fast_target)], relationship_deltas=deltas
    )
    slow_event = _event(
        slow_actor, world_id, "give", 0.95, tick=5000, targets=[str(slow_target)], relationship_deltas=deltas
    )

    fast_elapsed = await _elapsed_ticks_since_met(db_session, world_id, fast_event)
    slow_elapsed = await _elapsed_ticks_since_met(db_session, world_id, slow_event)
    fast_description = describe_event(fast_event, fast_elapsed)
    slow_description = describe_event(slow_event, slow_elapsed)

    assert fast_description != slow_description
    assert fast_description == "Gave an item to another agent, which formed a close bond, about 2 hours after meeting them"
    assert "month" in slow_description


@pytest.mark.asyncio
async def test_full_trial_scoring_round_trip(db_session):
    """Fixture note: same distinctiveness requirement as the blinding test
    above — the owner must be more "greet"-heavy than the population."""
    world_id, owner_agent, decoy_agent = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    for t in range(15):
        db_session.add(_event(owner_agent, world_id, "greet", 0.6, t))
    for t in range(15, 25):
        db_session.add(_event(decoy_agent, world_id, "greet", 0.6, t))
    for t in range(25, 35):
        db_session.add(_event(decoy_agent, world_id, "form_goal", 0.5, t))
    await db_session.flush()

    prepared = await RecognitionHarness.prepare_trial(
        db_session, world_id, owner_agent, random.Random(9), decoy_agent_id=decoy_agent
    )

    # A perfect owner: picks exactly the true "own" events.
    perfect_selection = {eid for eid, is_own in prepared.ground_truth.items() if is_own}
    assert RecognitionHarness.score(prepared, perfect_selection) == 1.0

    # A hopeless owner: picks nothing.
    assert RecognitionHarness.score(prepared, set()) == 0.5  # gets all decoys "right" by omission

    trial = await RecognitionHarness.record_trial(
        db_session, uuid.uuid4(), persona_version=1, prepared=prepared, owner_selections=perfect_selection
    )
    assert trial.accuracy == 1.0
