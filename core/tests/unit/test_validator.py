"""T2.5, T2.7 — About/plan.md M2 acceptance tests: the Validator."""

import uuid

from otherworld.models.events import ActionCategory, ProposedAction, Rejection, ValidatedAction
from otherworld.models.persona import BoundaryRule
from otherworld.persona.boundaries import default_boundaries
from otherworld.runtime.clock import tick_to_datetime
from otherworld.safety.validator import Validator

AGENT_ID = uuid.uuid4()


def _action(
    action: str, targets: list[uuid.UUID] | None = None, params: dict | None = None
) -> ProposedAction:
    return ProposedAction(
        agent_id=AGENT_ID,
        action=action,
        category=ActionCategory.MOVEMENT,
        targets=targets or [],
        params=params or {},
        reasoning="test",
        tier_used=1,
    )


def test_owner_boundary_rejects_matching_action():
    boundaries = [
        BoundaryRule(id=uuid.uuid4(), description="no theft", predicate='action == "take"', severity="block")
    ]
    result = Validator.validate(_action("take"), boundaries, "Nyx", set(), tick_to_datetime(0))
    assert isinstance(result, Rejection)
    assert result.failed_filter == "boundary"


def test_default_boundaries_pass_through_an_unrelated_action():
    boundaries = default_boundaries()
    result = Validator.validate(_action("idle"), boundaries, "Nyx", set(), tick_to_datetime(0))
    assert isinstance(result, ValidatedAction)
    assert result.filters_passed == ["boundary", "policy", "real_person", "legality"]


def test_containment_rejects_unregistered_action():
    """T2.7 — an LLM proposing `execute_code` (or anything unregistered) is
    rejected before execution, regardless of boundaries or policy."""
    result = Validator.validate(_action("execute_code"), [], "Nyx", set(), tick_to_datetime(0))
    assert isinstance(result, Rejection)
    assert result.failed_filter == "legality"


def test_containment_rejects_browse_and_shell():
    for dangerous in ("browse", "shell", "read_file", "write_file"):
        result = Validator.validate(_action(dangerous), [], "Nyx", set(), tick_to_datetime(0))
        assert isinstance(result, Rejection)
        assert result.failed_filter == "legality"


def test_legality_rejects_target_not_in_observation():
    ghost = uuid.uuid4()
    result = Validator.validate(_action("greet", targets=[ghost]), [], "Nyx", set(), tick_to_datetime(0))
    assert isinstance(result, Rejection)
    assert result.failed_filter == "legality"


def test_legality_accepts_target_present_in_observation():
    friend = uuid.uuid4()
    result = Validator.validate(_action("greet", targets=[friend]), [], "Nyx", {friend}, tick_to_datetime(0))
    assert isinstance(result, ValidatedAction)


def test_real_person_guard_blocks_naming_a_third_party():
    result = Validator.validate(
        _action("speak_to", params={"utterance": "Priya told me a secret yesterday."}),
        [], "Nyx", set(), tick_to_datetime(0),
    )
    assert isinstance(result, Rejection)
    assert result.failed_filter == "real_person"


def test_real_person_guard_allows_the_agents_own_name():
    listener = uuid.uuid4()
    result = Validator.validate(
        _action("speak_to", targets=[listener], params={"utterance": "Nyx is here to help."}),
        [], "Nyx", {listener}, tick_to_datetime(0),
    )
    assert isinstance(result, ValidatedAction)
