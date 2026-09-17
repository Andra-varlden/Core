"""Bond-state transitions. See About/spec.md §6.4.

M5 completes the state machine started in M3 (Stranger -> Acquaintance ->
Friend): Close bond, decay-driven demotion, and Broken -> Acquaintance
reconciliation. Strained/Repaired/Broken/Feud transitions driven by the
conflict system itself live in `social/conflict.py`, not here — this module
only covers the trust/time-driven rungs.

"Costly loyalty act" (About/spec.md §6.4's Friend -> Close bond rule) is not
crisply defined in the spec beyond that phrase. Interpreted here as a `give`
action between already-Friend agents — a concrete, low-ambiguity reading;
revisit if it under- or over-fires once there's real usage data.
"""

from __future__ import annotations

from otherworld.config import settings
from otherworld.models.events import ActionCategory
from otherworld.models.relationship import BondState, RelationshipEdge
from otherworld.safety.registry import ActionRegistry, UnknownActionError

_SOCIAL_CATEGORIES = {ActionCategory.SOCIAL, ActionCategory.RELATIONAL}
_COSTLY_LOYALTY_ACTIONS = {"give"}


def is_social_interaction(action: str) -> bool:
    try:
        return ActionRegistry.resolve(action).category in _SOCIAL_CATEGORIES
    except UnknownActionError:
        return False


def is_costly_loyalty_act(action: str) -> bool:
    return action in _COSTLY_LOYALTY_ACTIONS


def promote_if_eligible(
    edge: RelationshipEdge,
    max_shared_memory_importance: float,
    has_repaired_conflict: bool = False,
    costly_loyalty_act_this_tick: bool = False,
) -> RelationshipEdge:
    """Advance `edge` upward if it has earned it. Never demotes — demotion
    is decay/conflict-driven, handled by `apply_decay` below and by
    `social/conflict.py` respectively.
    """
    if edge.bond_state == BondState.STRANGER:
        edge = edge.model_copy(update={"bond_state": BondState.ACQUAINTANCE})

    if edge.bond_state == BondState.ACQUAINTANCE and (
        edge.trust >= settings.relationships.friend_trust_threshold
        and max_shared_memory_importance >= settings.relationships.friend_shared_memory_importance
    ):
        edge = edge.model_copy(update={"bond_state": BondState.FRIEND})

    close_bond_ready = edge.trust >= settings.relationships.close_bond_trust_threshold and (
        has_repaired_conflict or costly_loyalty_act_this_tick
    )
    if edge.bond_state == BondState.FRIEND and close_bond_ready:
        edge = edge.model_copy(update={"bond_state": BondState.CLOSE_BOND})

    return edge


def has_repaired_conflict(edge: RelationshipEdge) -> bool:
    return any(r.resolution == "repaired" for r in edge.conflict_log)


def apply_decay(edge: RelationshipEdge, current_tick: int) -> RelationshipEdge:
    """About/spec.md §6.4's decay-driven demotions. Trust decay itself
    (the numeric decrease) is applied elsewhere (About/spec.md §6.3);
    this only reacts to trust that has already dropped.
    """
    if edge.bond_state == BondState.FRIEND and edge.trust < settings.relationships.demote_friend_below:
        return edge.model_copy(update={"bond_state": BondState.ACQUAINTANCE})

    if (
        edge.bond_state == BondState.ACQUAINTANCE
        and edge.trust < settings.relationships.demote_acquaintance_below
        and current_tick - edge.last_contact_tick > 1000  # [TUNE] spec.md §6.4
    ):
        return edge.model_copy(update={"bond_state": BondState.STRANGER})

    return edge


def attempt_reconciliation(edge: RelationshipEdge, action: str) -> RelationshipEdge:
    """Broken -> Acquaintance, About/spec.md §6.4: "rare." A successful
    `forgive` reaching out to a Broken edge is the reconciliation sequence.

    Feud has no recovery path in spec.md's own transition table at all —
    About/plan.md's T5.1 acceptance run found that, left that way, Feud is
    a true absorbing state: every one of a 20-agent population's edges had
    converged to Feud, permanently, by the end of a single 10,000-tick run.
    Rather than let Feud jump straight back to a bonded state on one
    `forgive` — cheaper than what Broken requires, despite being the worse
    state — a Feud reconciliation only steps down to Broken. Escaping Feud
    for real still takes the existing, harder Broken -> Acquaintance step
    afterward: two deliberate acts of forgiveness, not one.
    """
    if action != "forgive":
        return edge
    if edge.bond_state == BondState.BROKEN:
        return edge.model_copy(update={"bond_state": BondState.ACQUAINTANCE})
    if edge.bond_state == BondState.FEUD:
        return edge.model_copy(update={"bond_state": BondState.BROKEN})
    return edge
