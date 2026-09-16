"""Bond-state transitions. See About/spec.md §6.4.

M3 implements the first two rungs only: Stranger -> Acquaintance -> Friend.
Strained/Repaired/Broken/Feud all require the conflict system (About/plan.md
M5 scope) and Close bond requires a repaired conflict or costly loyalty act
— neither exists yet, so this module deliberately stops at Friend.
"""

from __future__ import annotations

from otherworld.config import settings
from otherworld.models.events import ActionCategory
from otherworld.models.relationship import BondState, RelationshipEdge
from otherworld.safety.registry import ActionRegistry, UnknownActionError

_SOCIAL_CATEGORIES = {ActionCategory.SOCIAL, ActionCategory.RELATIONAL}


def is_social_interaction(action: str) -> bool:
    try:
        return ActionRegistry.resolve(action).category in _SOCIAL_CATEGORIES
    except UnknownActionError:
        return False


def promote_if_eligible(edge: RelationshipEdge, max_shared_memory_importance: float) -> RelationshipEdge:
    """Advance `edge` toward Friend if it has earned it. Never demotes —
    demotion is decay/conflict-driven (About/spec.md §6.4), out of M3 scope.
    """
    if edge.bond_state == BondState.STRANGER:
        edge = edge.model_copy(update={"bond_state": BondState.ACQUAINTANCE})

    if edge.bond_state == BondState.ACQUAINTANCE and (
        edge.trust >= settings.relationships.friend_trust_threshold
        and max_shared_memory_importance >= settings.relationships.friend_shared_memory_importance
    ):
        edge = edge.model_copy(update={"bond_state": BondState.FRIEND})

    return edge
