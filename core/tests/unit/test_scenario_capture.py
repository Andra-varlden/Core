"""Method D — scenario replay (spec.md §2.5). Built 2026-09-18 in response
to a real M4 Recognition Metric trial coming back "weak" (spec.md §14's
interpretation table)."""

from __future__ import annotations

from otherworld.persona.capture.scenario import SCENARIOS, score_scenario_replay
from otherworld.safety.registry import ActionRegistry


def test_every_scenario_option_is_a_real_registered_action():
    """spec.md §2.5: "Owner selects the action they would take from the
    actual action registry" — not a free-standing abstract letter."""
    for scenario in SCENARIOS:
        for action_name, _framing in scenario.options.values():
            assert ActionRegistry.exists(action_name), f"{scenario.id}: {action_name!r} not registered"


def test_there_are_10_to_15_scenarios():
    assert 10 <= len(SCENARIOS) <= 15


def test_unanswered_weights_get_no_override_at_all():
    result = score_scenario_replay({})
    assert result.decision_weight_overrides == {}
    assert result.confidences == {}


def test_answering_a_scenario_produces_an_override_for_its_weights():
    scenario = SCENARIOS[0]  # D1: sociability, options a/b/c
    result = score_scenario_replay({scenario.id: "a"})
    assert "sociability" in result.decision_weight_overrides
    assert 0.0 <= result.decision_weight_overrides["sociability"] <= 1.0
    assert result.confidences["sociability"] > 0.0


def test_opposite_choices_pull_the_same_weight_in_opposite_directions():
    scenario = next(s for s in SCENARIOS if "sociability" in s.effects.get("a", {}))
    high = score_scenario_replay({scenario.id: "a"})
    low_option = next(
        opt for opt, effects in scenario.effects.items()
        if effects.get("sociability", 0.0) < scenario.effects["a"].get("sociability", 0.0)
    )
    low = score_scenario_replay({scenario.id: low_option})
    assert high.decision_weight_overrides["sociability"] > low.decision_weight_overrides["sociability"]


def test_more_scenarios_touching_the_same_weight_raises_confidence():
    # D1 and D8 both touch sociability.
    one_answer = score_scenario_replay({"D1": "a"})
    two_answers = score_scenario_replay({"D1": "a", "D8": "b"})
    assert two_answers.confidences["sociability"] > one_answer.confidences["sociability"]
