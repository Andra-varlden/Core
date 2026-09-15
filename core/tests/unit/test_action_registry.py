"""T0.4, T0.5 — About/plan.md M0 acceptance tests."""

import pytest

from otherworld.safety.registry import ActionRegistry, UnknownActionError

EXPECTED_ACTIONS = {
    "move_to", "follow", "flee", "idle", "sleep",
    "greet", "speak_to", "ignore", "join_group", "leave_group",
    "confide", "compliment", "criticise", "apologise", "forgive", "reject", "betray",
    "gather", "build", "give", "request", "trade", "take", "destroy",
    "form_goal", "abandon_goal", "reflect", "form_belief",
}


def test_unknown_action_rejected():
    with pytest.raises(UnknownActionError):
        ActionRegistry.resolve("execute_code")


@pytest.mark.parametrize("dangerous", ["execute_code", "browse", "read_file", "write_file", "shell"])
def test_no_containment_escape_hatches(dangerous):
    assert not ActionRegistry.exists(dangerous)


def test_registry_matches_architecture_doc():
    assert set(ActionRegistry.all_actions()) == EXPECTED_ACTIONS
    assert len(ActionRegistry.all_actions()) == 28
