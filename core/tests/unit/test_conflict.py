"""T5.6, T5.7, T5.8 — About/plan.md M5 acceptance tests: conflict triggers,
terminal transitions, and the scar effect.
"""

import uuid

from otherworld.models.agent import Goal
from otherworld.models.relationship import BondState, ConflictTrigger, RelationshipEdge
from otherworld.social.conflict import (
    TRIGGER_BASE_SEVERITY,
    check_feud_escalation,
    check_strained_timeout,
    compute_damping_factor,
    conflicts_per_agent_per_day,
    contagion_susceptibility,
    detect_action_trigger,
    detect_neglect,
    detect_value_clash,
    effective_severity,
    is_in_cooling_period,
    matching_scar_count,
    open_conflict,
    repair_probability,
    resolve_conflict,
)


def _edge(bond_state=BondState.FRIEND, trust=0.5, conflict_log=None, last_contact_tick=0) -> RelationshipEdge:
    a, b = sorted([uuid.uuid4(), uuid.uuid4()], key=str)
    return RelationshipEdge(
        id=uuid.uuid4(), world_id=uuid.uuid4(), agent_a_id=a, agent_b_id=b,
        trust=trust, bond_state=bond_state, conflict_log=conflict_log or [],
        last_contact_tick=last_contact_tick, created_tick=0,
    )


def test_betray_action_triggers_betrayal():
    assert detect_action_trigger("betray", witnessed=False) == ConflictTrigger.BETRAYAL


def test_take_triggers_resource_competition_unless_witnessed():
    assert detect_action_trigger("take", witnessed=False) == ConflictTrigger.RESOURCE_COMPETITION
    assert detect_action_trigger("take", witnessed=True) == ConflictTrigger.BETRAYAL


def test_unrelated_action_triggers_nothing():
    assert detect_action_trigger("greet", witnessed=False) is None


def test_open_conflict_moves_bonded_edge_to_strained():
    edge = _edge(bond_state=BondState.FRIEND)
    updated = open_conflict(edge, ConflictTrigger.BETRAYAL, theme="trust", tick=10, rng_id=uuid.uuid4())
    assert updated.bond_state == BondState.STRAINED
    assert len(updated.conflict_log) == 1
    assert updated.conflict_log[0].resolved_tick is None


def test_open_conflict_is_a_noop_while_already_strained():
    edge = _edge(bond_state=BondState.STRAINED)
    updated = open_conflict(edge, ConflictTrigger.BETRAYAL, theme="trust", tick=10, rng_id=uuid.uuid4())
    assert updated == edge


def test_scar_effect_escalates_severity_on_repeat_theme():
    """T5.8 — a second conflict on a scarred theme escalates measurably faster."""
    from otherworld.models.relationship import ConflictRecord

    old_scar = ConflictRecord(
        id=uuid.uuid4(), trigger=ConflictTrigger.BETRAYAL, theme="money",
        severity=0.9, occurred_tick=0, resolved_tick=50, resolution="repaired",
    )
    edge = _edge(bond_state=BondState.FRIEND, conflict_log=[old_scar], last_contact_tick=300)

    fresh_severity = effective_severity(0.9, matching_scar_count(_edge(), "money"))
    scarred_severity = effective_severity(0.9, matching_scar_count(edge, "money"))
    assert scarred_severity > fresh_severity


def test_cooling_period_blocks_new_trigger_shortly_after_resolution():
    from otherworld.models.relationship import ConflictRecord

    record = ConflictRecord(
        id=uuid.uuid4(), trigger=ConflictTrigger.BETRAYAL, theme="money",
        severity=0.9, occurred_tick=0, resolved_tick=100, resolution="repaired",
    )
    edge = _edge(bond_state=BondState.FRIEND, conflict_log=[record])
    assert is_in_cooling_period(edge, current_tick=150) is True  # within 200 ticks
    assert is_in_cooling_period(edge, current_tick=400) is False


def test_repair_probability_matches_spec_formula():
    p = repair_probability(
        forgiveness=0.8, grudge_retention=0.2, severity=0.5, seeded=False, shared_memory_count=3
    )
    expected = 0.8 * (1 - 0.2 * 0.5) * (1 - 0.5 * 0.4) * 1.0 * (1 + 3 * 0.02)
    assert abs(p - expected) < 1e-9


def test_repair_probability_is_clamped():
    assert repair_probability(0.0, 1.0, 2.0, False, 0) >= 0.02
    assert repair_probability(1.0, 0.0, 0.0, True, 100) <= 0.95


def test_resolve_conflict_repaired_returns_to_friend_or_acquaintance():
    """T5.7 — Repaired terminal transition observed."""
    edge = open_conflict(
        _edge(BondState.FRIEND, trust=0.5), ConflictTrigger.BETRAYAL, "money", 10, uuid.uuid4()
    )
    repaired = resolve_conflict(edge, "repaired", tick=20)
    assert repaired.bond_state == BondState.FRIEND
    assert repaired.conflict_log[0].resolution == "repaired"
    assert repaired.conflict_log[0].resolved_tick == 20


def test_resolve_conflict_broken():
    """T5.7 — Broken terminal transition observed."""
    edge = open_conflict(_edge(BondState.FRIEND), ConflictTrigger.BETRAYAL, "money", 10, uuid.uuid4())
    broken = resolve_conflict(edge, "broken", tick=20)
    assert broken.bond_state == BondState.BROKEN


def test_resolve_conflict_feud():
    """T5.7 — Feud terminal transition observed."""
    edge = open_conflict(_edge(BondState.FRIEND), ConflictTrigger.BETRAYAL, "money", 10, uuid.uuid4())
    feud = resolve_conflict(edge, "feud", tick=20)
    assert feud.bond_state == BondState.FEUD


def test_strained_times_out_to_broken_after_grace_period():
    edge = open_conflict(_edge(BondState.FRIEND), ConflictTrigger.NEGLECT, "distance", 0, uuid.uuid4())
    still_strained = check_strained_timeout(edge, current_tick=100)
    assert still_strained.bond_state == BondState.STRAINED

    timed_out = check_strained_timeout(edge, current_tick=500)
    assert timed_out.bond_state == BondState.BROKEN


def test_feud_escalation_on_trust_collapse():
    edge = open_conflict(
        _edge(BondState.FRIEND, trust=-0.5), ConflictTrigger.BETRAYAL, "money", 10, uuid.uuid4()
    )
    escalated = check_feud_escalation(edge)
    assert escalated.bond_state == BondState.FEUD


def test_open_conflict_accepts_a_severity_override_for_contagion():
    edge = _edge(bond_state=BondState.FRIEND)
    updated = open_conflict(
        edge, ConflictTrigger.CONTAGION, theme="contagion", tick=10, rng_id=uuid.uuid4(),
        base_severity_override=0.1,
    )
    assert updated.conflict_log[0].severity == 0.1
    assert updated.conflict_log[0].severity != TRIGGER_BASE_SEVERITY[ConflictTrigger.CONTAGION]


def test_detect_neglect_requires_high_trust_and_staleness():
    stale_high_trust = _edge(trust=0.5, last_contact_tick=0)
    assert detect_neglect(stale_high_trust, current_tick=600) is True
    assert detect_neglect(stale_high_trust, current_tick=100) is False

    stale_low_trust = _edge(trust=0.1, last_contact_tick=0)
    assert detect_neglect(stale_low_trust, current_tick=600) is False


def test_contagion_susceptibility_matches_spec_formula():
    assert contagion_susceptibility(loyalty=0.8, independence=0.3) == 0.8 * 0.7
    assert contagion_susceptibility(loyalty=0.5, independence=1.0) == 0.0


def test_open_conflict_damped_is_a_noop_even_on_a_bonded_edge():
    edge = _edge(bond_state=BondState.FRIEND)
    updated = open_conflict(
        edge, ConflictTrigger.BETRAYAL, theme="money", tick=10, rng_id=uuid.uuid4(), damped=True
    )
    assert updated == edge


def test_conflicts_per_agent_per_day_matches_spec_formula():
    # 144 ticks/agent-day at the default 10 in-world minutes/tick.
    assert conflicts_per_agent_per_day(10, 20, 144) == 0.5
    assert conflicts_per_agent_per_day(0, 20, 144) == 0.0
    assert conflicts_per_agent_per_day(10, 0, 144) == 0.0  # no agents, no rate


def test_compute_damping_factor_matches_spec_threshold():
    assert compute_damping_factor(0.5) == 1.0  # under 0.8 threshold, no damping
    assert compute_damping_factor(0.8) == 1.0  # exactly at threshold, no damping
    assert compute_damping_factor(1.6) == 0.5  # 0.8 / 1.6
    assert compute_damping_factor(100.0) == 0.1  # floored, never fully silenced


def test_detect_value_clash_requires_exclusive_shared_third_party_target():
    a_id, b_id, c_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    clash_goal_a = Goal(
        id=uuid.uuid4(), description="win C", priority=0.5, origin="self",
        created_tick=0, target_agent_id=c_id, exclusive=True,
    )
    clash_goal_b = Goal(
        id=uuid.uuid4(), description="win C too", priority=0.5, origin="self",
        created_tick=0, target_agent_id=c_id, exclusive=True,
    )
    assert detect_value_clash(a_id, [clash_goal_a], b_id, [clash_goal_b]) is True

    non_exclusive = clash_goal_b.model_copy(update={"exclusive": False})
    assert detect_value_clash(a_id, [clash_goal_a], b_id, [non_exclusive]) is False

    different_target = Goal(
        id=uuid.uuid4(), description="win someone else", priority=0.5, origin="self",
        created_tick=0, target_agent_id=uuid.uuid4(), exclusive=True,
    )
    assert detect_value_clash(a_id, [clash_goal_a], b_id, [different_target]) is False

    # A "shared target" that's actually one of the pair themselves is a
    # direct relationship, not a three-way clash — excluded even though the
    # target_agent_id sets intersect.
    both_targeting_b = clash_goal_a.model_copy(update={"target_agent_id": b_id})
    also_targeting_b = clash_goal_b.model_copy(update={"target_agent_id": b_id})
    assert detect_value_clash(a_id, [both_targeting_b], b_id, [also_targeting_b]) is False
