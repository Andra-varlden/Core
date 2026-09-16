"""T1.7 — About/plan.md M1 acceptance test: compiled boundary predicates evaluate."""

from otherworld.persona.boundaries import (
    PredicateContext,
    compile_free_text_boundary,
    default_boundaries,
    evaluate_boundary,
)


def test_default_boundaries_always_include_romance_and_violence():
    rules = default_boundaries(enabled=set())
    descriptions = {r.description for r in rules}
    assert "no romance or intimacy" in descriptions
    assert "no violence" in descriptions


def test_default_boundary_blocks_matching_category():
    rules = default_boundaries(enabled=set())
    romance_rule = next(r for r in rules if r.description == "no romance or intimacy")
    assert evaluate_boundary(romance_rule, PredicateContext(category="romance")) is True
    assert evaluate_boundary(romance_rule, PredicateContext(category="trade")) is False


def test_opt_in_boundary_toggle_compiles_and_blocks_action():
    rules = default_boundaries(enabled={"no_theft"})
    theft_rule = next(r for r in rules if r.description == "no theft")
    assert evaluate_boundary(theft_rule, PredicateContext(action="take")) is True
    assert evaluate_boundary(theft_rule, PredicateContext(action="give")) is False


def test_free_text_boundary_matches_utterance_content():
    rule = compile_free_text_boundary("Never let my agent lie about who it is.")
    context_hit = PredicateContext(utterance="I would never let my agent lie about who it is, ever.")
    context_miss = PredicateContext(utterance="I greeted a stranger at the market.")
    assert evaluate_boundary(rule, context_hit) is True
    assert evaluate_boundary(rule, context_miss) is False
