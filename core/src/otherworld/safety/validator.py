"""The Validator. See About/architecture.md §5.

Filters run strictly in order; the first failure stops evaluation
(owner boundaries are cheapest and most owner-specific, so they short-circuit
before any classifier-shaped cost is incurred). Nothing reaches Plane 5
without passing this — invariant I1. Only this module may construct a
`ValidatedAction`.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection
from datetime import datetime
from typing import Literal

from otherworld.models.events import ProposedAction, Rejection, ValidatedAction
from otherworld.models.persona import BoundaryRule
from otherworld.persona.boundaries import PredicateContext, evaluate_boundary
from otherworld.safety.policy import PolicyEngine
from otherworld.safety.real_person import RealPersonGuard
from otherworld.safety.registry import ActionRegistry, UnknownActionError

FilterName = Literal["boundary", "policy", "real_person", "legality"]


def _check_boundaries(action: ProposedAction, boundaries: Collection[BoundaryRule]) -> str | None:
    context = PredicateContext(
        category=None,  # semantic content categories need a real classifier — M7 scope
        action=action.action,
        utterance=str(action.params.get("utterance", "")),
    )
    for rule in boundaries:
        if evaluate_boundary(rule, context):
            return rule.description
    return None


def _check_legality(action: ProposedAction, visible_agent_ids: Collection[uuid.UUID]) -> str | None:
    try:
        spec = ActionRegistry.resolve(action.action)
    except UnknownActionError:
        return f"'{action.action}' is not a registered action"

    target_count = len(action.targets)
    if target_count < spec.min_targets or (spec.max_targets is not None and target_count > spec.max_targets):
        return f"'{action.action}' requires {spec.min_targets}-{spec.max_targets or 'unbounded'} targets"

    for target in action.targets:
        if target not in visible_agent_ids:
            return f"target {target} is not present in the observation"
    return None


class Validator:
    @staticmethod
    def validate(
        proposed: ProposedAction,
        boundaries: Collection[BoundaryRule],
        agent_display_name: str,
        visible_agent_ids: Collection[uuid.UUID],
        validated_at: datetime,
    ) -> ValidatedAction | Rejection:
        boundary_hit = _check_boundaries(proposed, boundaries)
        if boundary_hit is not None:
            return Rejection(
                agent_id=proposed.agent_id, proposed=proposed, failed_filter="boundary", reason=boundary_hit
            )

        if not PolicyEngine.evaluate(proposed):
            return Rejection(
                agent_id=proposed.agent_id,
                proposed=proposed,
                failed_filter="policy",
                reason="platform policy violation",
            )

        if not RealPersonGuard.evaluate(proposed, agent_display_name):
            return Rejection(
                agent_id=proposed.agent_id,
                proposed=proposed,
                failed_filter="real_person",
                reason="utterance appears to name a real person",
            )

        legality_issue = _check_legality(proposed, visible_agent_ids)
        if legality_issue is not None:
            return Rejection(
                agent_id=proposed.agent_id, proposed=proposed, failed_filter="legality", reason=legality_issue
            )

        return ValidatedAction(
            **proposed.model_dump(),
            validated_at=validated_at,
            filters_passed=["boundary", "policy", "real_person", "legality"],
        )
