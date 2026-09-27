"""T3.5, T3.6 — About/plan.md M3 acceptance tests: trust deltas and the
Friend promotion gate.
"""

import uuid

from otherworld.models.relationship import BondState, RelationshipEdge
from otherworld.social.engine import (
    TRUST_DELTAS,
    apply_trust_decay,
    apply_trust_delta,
    is_friend_eligible,
    ordered_pair,
)
from otherworld.social.state_machine import apply_decay, attempt_reconciliation, promote_if_eligible

# Hand-computed fixture: exact values from About/spec.md §6.2.
_SPEC_6_2_FIXTURE = {
    "greet": 0.03,
    "criticise": -0.10,
    "reject": -0.15,
    "take": -0.30,
    "betray": -0.50,
    "apologise": 0.20,
    "forgive": 0.25,
}


def _edge(
    trust: float = 0.0,
    bond_state: BondState = BondState.STRANGER,
    shared_memory_ids=None,
    last_contact_tick: int = 0,
) -> RelationshipEdge:
    a, b = sorted([uuid.uuid4(), uuid.uuid4()], key=str)
    return RelationshipEdge(
        id=uuid.uuid4(), world_id=uuid.uuid4(), agent_a_id=a, agent_b_id=b,
        trust=trust, bond_state=bond_state, shared_memory_ids=shared_memory_ids or [],
        last_contact_tick=last_contact_tick, created_tick=0,
    )


def test_trust_deltas_match_spec_exactly():
    assert TRUST_DELTAS == _SPEC_6_2_FIXTURE


def test_apply_trust_delta_matches_fixture_values():
    for action, expected_delta in _SPEC_6_2_FIXTURE.items():
        edge = _edge(trust=0.0)
        updated = apply_trust_delta(edge, action)
        assert abs(updated.trust - expected_delta) < 1e-9, action


def test_apply_trust_delta_clamps_to_bounds():
    edge = _edge(trust=0.95)
    updated = apply_trust_delta(edge, "apologise")  # +0.20 would overshoot 1.0
    assert updated.trust == 1.0

    edge = _edge(trust=-0.95)
    updated = apply_trust_delta(edge, "betray")  # -0.50 would undershoot -1.0
    assert updated.trust == -1.0


def test_unrecognised_action_leaves_trust_unchanged():
    edge = _edge(trust=0.4)
    assert apply_trust_delta(edge, "gather").trust == 0.4


def test_ordered_pair_is_stable_regardless_of_argument_order():
    a, b = uuid.uuid4(), uuid.uuid4()
    assert ordered_pair(a, b) == ordered_pair(b, a)


def test_stranger_promotes_to_acquaintance_on_any_interaction():
    edge = _edge(bond_state=BondState.STRANGER)
    updated = promote_if_eligible(edge, max_shared_memory_importance=0.15)
    assert updated.bond_state == BondState.ACQUAINTANCE


def test_friend_promotion_requires_both_trust_and_high_importance_memory():
    """T3.6 — trust alone, at or above threshold, must NOT promote to Friend
    without a high-importance shared memory."""
    edge = _edge(trust=0.40, bond_state=BondState.ACQUAINTANCE)  # trust clears 0.35 threshold

    still_acquaintance = promote_if_eligible(edge, max_shared_memory_importance=0.3)  # below 0.6
    assert still_acquaintance.bond_state == BondState.ACQUAINTANCE
    assert not is_friend_eligible(edge, max_shared_memory_importance=0.3)

    now_friend = promote_if_eligible(edge, max_shared_memory_importance=0.6)
    assert now_friend.bond_state == BondState.FRIEND


def test_high_importance_memory_alone_does_not_promote_without_trust():
    edge = _edge(trust=0.10, bond_state=BondState.ACQUAINTANCE)  # below 0.35 threshold
    updated = promote_if_eligible(edge, max_shared_memory_importance=0.9)
    assert updated.bond_state == BondState.ACQUAINTANCE


def test_friend_promotes_to_close_bond_with_repaired_conflict():
    edge = _edge(trust=0.75, bond_state=BondState.FRIEND)
    updated = promote_if_eligible(edge, max_shared_memory_importance=0.9, has_repaired_conflict=True)
    assert updated.bond_state == BondState.CLOSE_BOND


def test_friend_promotes_to_close_bond_with_costly_loyalty_act():
    edge = _edge(trust=0.75, bond_state=BondState.FRIEND)
    updated = promote_if_eligible(edge, max_shared_memory_importance=0.9, costly_loyalty_act_this_tick=True)
    assert updated.bond_state == BondState.CLOSE_BOND


def test_friend_does_not_promote_to_close_bond_without_a_qualifying_event():
    edge = _edge(trust=0.95, bond_state=BondState.FRIEND)
    updated = promote_if_eligible(edge, max_shared_memory_importance=0.9)
    assert updated.bond_state == BondState.FRIEND


def test_apply_decay_demotes_friend_below_threshold():
    edge = _edge(trust=0.20, bond_state=BondState.FRIEND)
    assert apply_decay(edge, current_tick=0).bond_state == BondState.ACQUAINTANCE


def test_apply_decay_demotes_stale_acquaintance_to_stranger():
    edge = _edge(trust=0.01, bond_state=BondState.ACQUAINTANCE, last_contact_tick=0)
    unchanged = apply_decay(edge, current_tick=500)  # not stale enough yet
    assert unchanged.bond_state == BondState.ACQUAINTANCE
    demoted = apply_decay(edge, current_tick=1500)
    assert demoted.bond_state == BondState.STRANGER


def test_trust_decay_matches_spec_formula_and_halves_for_seeded_edges():
    """spec.md §6.3: decay accrues from the moment the grace period lapses
    (tick 300), not from tick 0 — `ticks_since_last_contact > 300` is the
    *gate*, not the multiplier's own start point."""
    edge = _edge(trust=0.5, last_contact_tick=0)
    decayed = apply_trust_decay(edge, current_tick=1000)
    expected = max(-1.0, 0.5 - 0.0008 * (1000 - 300))
    assert abs(decayed.trust - expected) < 1e-9

    seeded = edge.model_copy(update={"seeded": True})
    seeded_decayed = apply_trust_decay(seeded, current_tick=1000)
    assert seeded_decayed.trust > decayed.trust  # decays at half rate


def test_trust_decay_is_a_noop_before_the_grace_period():
    edge = _edge(trust=0.5, last_contact_tick=0)
    assert apply_trust_decay(edge, current_tick=100).trust == 0.5


def test_trust_decay_sets_last_decay_tick_so_the_next_check_can_be_incremental():
    edge = _edge(trust=0.5, last_contact_tick=0)
    decayed = apply_trust_decay(edge, current_tick=1000)
    assert decayed.last_decay_tick == 1000


def test_repeated_periodic_scans_do_not_compound_beyond_the_true_elapsed_decay():
    """Regression test for the real M4 trial bug: `social/maintenance.py`
    calls `apply_trust_decay` on every scan (every `scan_interval_ticks`)
    for every stale edge. Before this fix, each call recomputed decay from
    the FULL, ever-growing `ticks_since_last_contact` and re-subtracted it
    from the already-decayed trust — so a pair scanned repeatedly while
    neglected fell to trust=-1.0 within one or two scans regardless of the
    real elapsed time, and stayed pinned there. Simulating 20 scans, 50
    ticks apart (the real `scan_interval_ticks` default), must land at the
    same trust as a single check at the final tick — not far below it."""
    edge = _edge(trust=0.5, last_contact_tick=0)

    repeatedly_scanned = edge
    for scan_tick in range(50, 1050, 50):
        repeatedly_scanned = apply_trust_decay(repeatedly_scanned, current_tick=scan_tick)

    single_check = apply_trust_decay(edge, current_tick=1000)
    assert abs(repeatedly_scanned.trust - single_check.trust) < 1e-9


def test_a_moderate_unscanned_gap_decays_gradually_not_straight_to_the_floor():
    """The actual reported symptom: a pair whose first-ever decay check
    lands well past the grace period must decay by exactly the real
    elapsed-since-grace-period amount, not fall straight to trust=-1.0
    regardless of how small that amount actually is."""
    edge = _edge(trust=0.5, last_contact_tick=0)
    decayed = apply_trust_decay(edge, current_tick=900)  # 600 ticks past the grace period
    expected = 0.5 - 0.0008 * 600  # == 0.02, nowhere near the floor
    assert abs(decayed.trust - expected) < 1e-9
    assert decayed.trust > -1.0


def test_decay_resumes_incrementally_after_an_earlier_partial_check():
    edge = _edge(trust=0.5, last_contact_tick=0)
    first_check = apply_trust_decay(edge, current_tick=400)  # 100 ticks past the grace period
    assert abs(first_check.trust - (0.5 - 0.0008 * 100)) < 1e-9
    assert first_check.last_decay_tick == 400

    second_check = apply_trust_decay(first_check, current_tick=500)  # 100 more ticks
    expected = first_check.trust - 0.0008 * 100
    assert abs(second_check.trust - expected) < 1e-9


def test_fresh_contact_resets_the_decay_clock():
    """`runtime/resolver.py` resets `last_decay_tick` to None on every
    contact — a revived relationship's decay should restart from the new
    contact, not keep accruing from a stale anchor."""
    edge = _edge(trust=0.5, last_contact_tick=0)
    decayed = apply_trust_decay(edge, current_tick=1000)
    assert decayed.last_decay_tick == 1000

    revived = decayed.model_copy(update={"last_contact_tick": 1000, "last_decay_tick": None})
    assert apply_trust_decay(revived, current_tick=1100).trust == decayed.trust  # still within grace period


def test_reconciliation_from_broken_via_forgive():
    edge = _edge(bond_state=BondState.BROKEN)
    reconciled = attempt_reconciliation(edge, "forgive")
    assert reconciled.bond_state == BondState.ACQUAINTANCE


def test_reconciliation_from_feud_steps_down_to_broken_not_acquaintance():
    """Feud has no reconciliation path in spec.md's own transition table —
    About/plan.md T5.1's run found it's a true absorbing state without one.
    Escaping it should take two deliberate `forgive`s, not one: Feud is
    strictly worse than Broken, so it shouldn't be cheaper to recover from.
    """
    edge = _edge(bond_state=BondState.FEUD)
    after_first_forgive = attempt_reconciliation(edge, "forgive")
    assert after_first_forgive.bond_state == BondState.BROKEN

    after_second_forgive = attempt_reconciliation(after_first_forgive, "forgive")
    assert after_second_forgive.bond_state == BondState.ACQUAINTANCE


def test_reconciliation_does_not_fire_on_other_actions():
    edge = _edge(bond_state=BondState.BROKEN)
    unchanged = attempt_reconciliation(edge, "greet")
    assert unchanged.bond_state == BondState.BROKEN
