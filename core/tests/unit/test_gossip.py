"""T5.10, T5.11 — About/plan.md M5 acceptance tests: gossip hop limit and
pile-on damping (About/spec.md §8.1, §8.2)."""

from __future__ import annotations

import uuid

from otherworld.social.gossip import (
    check_pileon,
    eligible_to_propagate,
    inherited_belief_strength,
    weighted_belief_strength,
    within_hop_limit,
)


def test_belief_below_importance_floor_is_not_eligible():
    assert not eligible_to_propagate(0.49)
    assert eligible_to_propagate(0.5)


def test_hop_limit_matches_spec_max_hops():
    assert within_hop_limit(0)
    assert within_hop_limit(2)
    assert not within_hop_limit(3)


def test_inherited_belief_strength_matches_spec_formula():
    strength = inherited_belief_strength(source_strength=0.8, trust_ab=0.5)
    expected = 0.8 * 0.75 * 0.7  # trust_normalised(0.5) = 0.75, propagation_decay = 0.7
    assert abs(strength - expected) < 1e-9


def test_inherited_belief_strength_is_dampened_by_distrust():
    trusting = inherited_belief_strength(0.8, trust_ab=0.9)
    distrusting = inherited_belief_strength(0.8, trust_ab=-0.9)
    assert distrusting < trusting


def test_direct_experience_outweighs_inherited_belief():
    weighted = weighted_belief_strength(direct_experience_strength=0.3, inherited_strength=0.9)
    assert weighted == 0.3 * 3.0  # direct_experience_weight = 3.0


def test_no_direct_experience_falls_back_to_inherited():
    assert weighted_belief_strength(direct_experience_strength=None, inherited_strength=0.6) == 0.6


def test_pileon_not_triggered_at_or_below_threshold():
    status = check_pileon([uuid.uuid4() for _ in range(4)])
    assert status.holder_count == 4
    assert not status.suppressed
    assert not status.watch_signal


def test_pileon_triggered_above_threshold():
    status = check_pileon([uuid.uuid4() for _ in range(5)])
    assert status.holder_count == 5
    assert status.suppressed
    assert status.watch_signal


def test_pileon_counts_distinct_holders_only():
    shared = uuid.uuid4()
    status = check_pileon([shared, shared, shared])
    assert status.holder_count == 1
