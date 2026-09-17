"""The conflict system. See About/spec.md §7.

Two kinds of trigger:
- Action-tied (BETRAYAL, RESOURCE_COMPETITION): detected the instant the
  triggering action resolves — About/runtime/resolver.py calls
  `detect_action_trigger` inline.
- Scan-tied (NEGLECT, CONTAGION, VALUE_CLASH): only meaningful across many
  edges/agents at once, so they're detected periodically by
  `social/maintenance.py`, not per-action — matching how
  About/architecture.md already treats faction detection and gossip as
  periodic recomputations rather than per-tick work.
"""

from __future__ import annotations

import random
import uuid

from otherworld.config import settings
from otherworld.models.relationship import BondState, ConflictRecord, ConflictTrigger, RelationshipEdge
from otherworld.runtime.determinism import seeded_uuid

# Base severity per trigger, About/spec.md §7.1. CONTAGION's is further
# scaled by contagion_susceptibility = loyalty * (1 - independence)
# (About/spec.md §3's derived values) at the call site, since severity
# there depends on the *receiving* agent's persona, not the edge alone.
TRIGGER_BASE_SEVERITY: dict[ConflictTrigger, float] = {
    ConflictTrigger.BETRAYAL: 0.9,
    ConflictTrigger.VALUE_CLASH: 0.5,
    ConflictTrigger.RESOURCE_COMPETITION: 0.4,
    ConflictTrigger.NEGLECT: 0.3,
    ConflictTrigger.CONTAGION: 0.35,
}

_BONDED_STATES = {BondState.ACQUAINTANCE, BondState.FRIEND, BondState.CLOSE_BOND}


def detect_action_trigger(action: str, witnessed: bool) -> ConflictTrigger | None:
    """BETRAYAL and RESOURCE_COMPETITION are tied directly to an action.
    `take` fires RESOURCE_COMPETITION normally, or BETRAYAL if witnessed
    (About/spec.md §10's action semantics table, `take` row).
    """
    if action == "betray":
        return ConflictTrigger.BETRAYAL
    if action == "take":
        return ConflictTrigger.BETRAYAL if witnessed else ConflictTrigger.RESOURCE_COMPETITION
    return None


def matching_scar_count(edge: RelationshipEdge, theme: str) -> int:
    return sum(1 for record in edge.conflict_log if record.theme == theme)


def effective_severity(base_severity: float, scar_count: int) -> float:
    """About/spec.md §7.2. Capped at 2.0x."""
    return min(
        settings.conflict.scar_multiplier_cap,
        base_severity * (1 + settings.conflict.scar_severity_multiplier * scar_count),
    )


def is_in_cooling_period(edge: RelationshipEdge, current_tick: int) -> bool:
    """About/spec.md §7.5: no new trigger may fire on this edge for
    `cooling_period_ticks` after any terminal transition.
    """
    for record in reversed(edge.conflict_log):
        if record.resolved_tick is not None:
            return current_tick - record.resolved_tick < settings.conflict.cooling_period_ticks
    return False


_ALREADY_AT_OR_BELOW_STRAINED = {BondState.STRAINED, BondState.BROKEN, BondState.FEUD}


def open_conflict(
    edge: RelationshipEdge,
    trigger: ConflictTrigger,
    theme: str,
    tick: int,
    rng_id: uuid.UUID,
    base_severity_override: float | None = None,
) -> RelationshipEdge:
    """Fires a trigger: opens a ConflictRecord (a permanent scar once
    resolved) and moves any bonded edge to Strained. Does nothing if the
    edge is already Strained, Broken or Feuding (one open conflict at a
    time; an edge already at or below Strained gains nothing from stacking
    more scars — About/spec.md's transition table has no "still worse than
    Feud" state, and getting better from there requires reconciliation, not
    more triggers — About/plan.md T5.1's pilot run found `conflict_log`
    growing unboundedly on busy Feud edges before this guard existed, each
    with its own O(len(conflict_log)) Python scan on every subsequent
    interaction) or in its cooling period.

    `base_severity_override`: CONTAGION's base severity isn't the flat
    per-trigger constant (About/spec.md §7.1: "0.35 x contagion_
    susceptibility", which depends on the *receiving* agent's persona, not
    the edge) — `social/maintenance.py` computes that scaled value and
    passes it through here instead of `TRIGGER_BASE_SEVERITY[trigger]`.
    """
    if edge.bond_state in _ALREADY_AT_OR_BELOW_STRAINED or is_in_cooling_period(edge, tick):
        return edge

    scars = matching_scar_count(edge, theme)
    base_severity = (
        base_severity_override if base_severity_override is not None else TRIGGER_BASE_SEVERITY[trigger]
    )
    severity = effective_severity(base_severity, scars)
    record = ConflictRecord(id=rng_id, trigger=trigger, theme=theme, severity=severity, occurred_tick=tick)

    new_state = BondState.STRAINED if edge.bond_state in _BONDED_STATES else edge.bond_state
    return edge.model_copy(update={"conflict_log": [*edge.conflict_log, record], "bond_state": new_state})


def _open_record(edge: RelationshipEdge) -> ConflictRecord | None:
    for record in reversed(edge.conflict_log):
        if record.resolved_tick is None:
            return record
    return None


def repair_probability(
    forgiveness: float,
    grudge_retention: float,
    severity: float,
    seeded: bool,
    shared_memory_count: int,
) -> float:
    """About/spec.md §7.4, clamped to [0.02, 0.95]."""
    p = (
        forgiveness
        * (1 - grudge_retention * 0.5)
        * (1 - severity * 0.4)
        * (1 + (0.25 if seeded else 0.0))
        * (1 + shared_memory_count * 0.02)
    )
    return max(0.02, min(0.95, p))


def resolve_conflict(edge: RelationshipEdge, resolution: str, tick: int) -> RelationshipEdge:
    """Applies a terminal transition to the currently-open conflict (About/
    spec.md §6.4's Strained -> {Repaired, Broken, Feud}). A no-op if there
    is no open conflict.
    """
    record = _open_record(edge)
    if record is None:
        return edge

    updated_log = [
        r.model_copy(update={"resolved_tick": tick, "resolution": resolution}) if r.id == record.id else r
        for r in edge.conflict_log
    ]
    new_state = {
        "repaired": BondState.FRIEND if edge.trust >= settings.relationships.friend_trust_threshold
        else BondState.ACQUAINTANCE,
        "broken": BondState.BROKEN,
        "feud": BondState.FEUD,
    }[resolution]
    return edge.model_copy(update={"conflict_log": updated_log, "bond_state": new_state})


def check_strained_timeout(edge: RelationshipEdge, current_tick: int) -> RelationshipEdge:
    """About/spec.md §6.4: Strained -> Broken after `strained_to_broken_ticks`
    with no repair attempt.
    """
    if edge.bond_state != BondState.STRAINED:
        return edge
    record = _open_record(edge)
    if record is None:
        return edge
    if current_tick - record.occurred_tick > settings.conflict.strained_to_broken_ticks:
        return resolve_conflict(edge, "broken", current_tick)
    return edge


_ESCALATING_ACTIONS = {"take", "betray", "reject"}


def apply_conflict_consequences(
    edge: RelationshipEdge,
    action: str,
    witnessed: bool,
    tick: int,
    rng: random.Random,
    target_forgiveness: float = 0.5,
    target_grudge_retention: float = 0.5,
) -> RelationshipEdge:
    """Everything an action can do to an edge's conflict state in a single
    tick, About/spec.md §7.3's in-conflict action outcomes table:
    escalating an open conflict straight to Feud, attempting repair
    (`apologise` rolled against the receiver's traits, `forgive` completing
    it outright), or opening a fresh trigger on an edge that wasn't already
    Strained. Called once per (actor, target) pair by
    `runtime/resolver.py`, after the trust delta and before bond-state
    promotion. Broken -> Acquaintance reconciliation is a separate rung
    (`social/state_machine.py`'s `attempt_reconciliation`), not this
    function's concern.
    """
    if edge.bond_state == BondState.STRAINED:
        if action in _ESCALATING_ACTIONS:
            return resolve_conflict(edge, "feud", tick)
        if action == "forgive":
            return resolve_conflict(edge, "repaired", tick)
        if action == "apologise":
            record = _open_record(edge)
            if record is not None:
                probability = repair_probability(
                    forgiveness=target_forgiveness,
                    grudge_retention=target_grudge_retention,
                    severity=record.severity,
                    seeded=edge.seeded,
                    shared_memory_count=len(edge.shared_memory_ids),
                )
                if rng.random() < probability:
                    return resolve_conflict(edge, "repaired", tick)
        return edge

    trigger = detect_action_trigger(action, witnessed)
    if trigger is not None:
        return open_conflict(edge, trigger, theme=trigger.value, tick=tick, rng_id=seeded_uuid(rng))
    return edge


def detect_neglect(edge: RelationshipEdge, current_tick: int) -> bool:
    """About/spec.md §7.1: "High-trust edge with no contact for
    `neglect_ticks` where one side attempted contact." The "one side
    attempted contact" qualifier needs data this codebase doesn't track
    (a record of rebuffed attempts, not just successful contact) — this
    checks the always-available half: a high-trust edge that's gone quiet.
    [TUNE], a documented simplification, not a silent one.
    """
    is_high_trust = edge.trust >= settings.relationships.friend_trust_threshold
    return is_high_trust and (current_tick - edge.last_contact_tick) >= settings.conflict.neglect_ticks


def contagion_susceptibility(loyalty: float, independence: float) -> float:
    """About/spec.md §3's derived value, used to scale CONTAGION's base
    severity (§7.1) for the *receiving* agent."""
    return loyalty * (1 - independence)


def check_feud_escalation(edge: RelationshipEdge) -> RelationshipEdge:
    """About/spec.md §6.4: Strained -> Feud when trust drops below the feud
    threshold (the "escalation action while already strained" half of this
    rule is handled by the caller resolving with resolution="feud" directly
    when an escalating action — take/betray/reject — occurs during Strained).
    """
    if edge.bond_state == BondState.STRAINED and edge.trust < settings.conflict.feud_trust_threshold:
        record = _open_record(edge)
        tick = record.occurred_tick if record else edge.last_contact_tick
        return resolve_conflict(edge, "feud", tick)
    return edge
