"""T3.5, T3.6 — About/plan.md M3 acceptance tests: trust deltas and the
Friend promotion gate.
"""

import uuid

from otherworld.models.relationship import BondState, RelationshipEdge
from otherworld.social.engine import TRUST_DELTAS, apply_trust_delta, is_friend_eligible, ordered_pair
from otherworld.social.state_machine import promote_if_eligible

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
    trust: float = 0.0, bond_state: BondState = BondState.STRANGER, shared_memory_ids=None
) -> RelationshipEdge:
    a, b = sorted([uuid.uuid4(), uuid.uuid4()], key=str)
    return RelationshipEdge(
        id=uuid.uuid4(), world_id=uuid.uuid4(), agent_a_id=a, agent_b_id=b,
        trust=trust, bond_state=bond_state, shared_memory_ids=shared_memory_ids or [],
        last_contact_tick=0, created_tick=0,
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
