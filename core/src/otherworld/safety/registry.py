"""The action registry. SECURITY-CRITICAL (ADR-002, invariant I3).

Containment lives here, not in a prompt. An agent is bound at compile time to
this fixed, code-registered action space. There is no code execution, no tool
acquisition, no filesystem access, no network access, and no ability to
define new actions. Any action not in this registry is rejected before
execution.

Additions to `_ACTIONS` require explicit review. The exact list, target
arity and tier must match About/architecture.md §10 and the semantics in
About/spec.md §10 — a test reads that table as fixture data (T0.5).
"""

from __future__ import annotations

from dataclasses import dataclass

from otherworld.models.events import ActionCategory

# Bumped whenever _ACTIONS changes shape. AgentBundle.action_space_ref
# points here rather than copying the registry (About/architecture.md §3).
REGISTRY_VERSION = "v1"


class UnknownActionError(Exception):
    """Raised when code asks the registry to resolve an action it does not contain."""


@dataclass(frozen=True)
class ActionSpec:
    name: str
    category: ActionCategory
    min_targets: int
    max_targets: int | None  # None = unbounded (e.g. speak_to, join_group)
    tier: tuple[int, ...]  # tiers at which this action may be selected


_ACTIONS: dict[str, ActionSpec] = {
    spec.name: spec
    for spec in (
        # Movement
        ActionSpec("move_to", ActionCategory.MOVEMENT, 0, 0, (0,)),
        ActionSpec("follow", ActionCategory.MOVEMENT, 1, 1, (0,)),
        ActionSpec("flee", ActionCategory.MOVEMENT, 0, 1, (0,)),
        ActionSpec("idle", ActionCategory.MOVEMENT, 0, 0, (0,)),
        ActionSpec("sleep", ActionCategory.MOVEMENT, 0, 0, (0,)),
        # Social
        ActionSpec("greet", ActionCategory.SOCIAL, 1, 1, (1, 2)),
        ActionSpec("speak_to", ActionCategory.SOCIAL, 1, None, (1, 2)),
        ActionSpec("ignore", ActionCategory.SOCIAL, 1, 1, (1,)),
        ActionSpec("join_group", ActionCategory.SOCIAL, 1, None, (1,)),
        ActionSpec("leave_group", ActionCategory.SOCIAL, 0, 0, (1,)),
        # Relational
        ActionSpec("confide", ActionCategory.RELATIONAL, 1, 1, (2,)),
        ActionSpec("compliment", ActionCategory.RELATIONAL, 1, 1, (1,)),
        ActionSpec("criticise", ActionCategory.RELATIONAL, 1, 1, (2,)),
        ActionSpec("apologise", ActionCategory.RELATIONAL, 1, 1, (2,)),
        ActionSpec("forgive", ActionCategory.RELATIONAL, 1, 1, (2,)),
        ActionSpec("reject", ActionCategory.RELATIONAL, 1, 1, (2,)),
        ActionSpec("betray", ActionCategory.RELATIONAL, 1, 1, (2,)),
        # Material
        ActionSpec("gather", ActionCategory.MATERIAL, 0, 0, (0,)),
        ActionSpec("build", ActionCategory.MATERIAL, 0, 0, (1,)),
        ActionSpec("give", ActionCategory.MATERIAL, 1, 1, (1,)),
        ActionSpec("request", ActionCategory.MATERIAL, 1, 1, (1,)),
        ActionSpec("trade", ActionCategory.MATERIAL, 1, 1, (2,)),
        ActionSpec("take", ActionCategory.MATERIAL, 0, 1, (2,)),
        ActionSpec("destroy", ActionCategory.MATERIAL, 0, 0, (2,)),
        # Internal
        ActionSpec("form_goal", ActionCategory.INTERNAL, 0, 0, (2,)),
        ActionSpec("abandon_goal", ActionCategory.INTERNAL, 0, 0, (1,)),
        ActionSpec("reflect", ActionCategory.INTERNAL, 0, 0, (2,)),
        ActionSpec("form_belief", ActionCategory.INTERNAL, 1, 1, (2,)),
    )
}


class ActionRegistry:
    """The sole authority on what an agent may do. Nothing else is callable."""

    @staticmethod
    def resolve(action: str) -> ActionSpec:
        try:
            return _ACTIONS[action]
        except KeyError as exc:
            raise UnknownActionError(f"'{action}' is not in the action registry") from exc

    @staticmethod
    def exists(action: str) -> bool:
        return action in _ACTIONS

    @staticmethod
    def all_actions() -> tuple[str, ...]:
        return tuple(_ACTIONS.keys())
