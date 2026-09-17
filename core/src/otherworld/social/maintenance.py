"""Periodic relationship maintenance. See About/spec.md §6.3, §6.4, §7.1, §7.5.

Runs once per `maintenance.scan_interval_ticks` across a world's whole edge
graph, checking everything that's time-driven or needs a global view rather
than being tied to a single action:

- Trust decay (spec.md §6.3) and its consequent demotions (§6.4's
  Friend -> Acquaintance, Acquaintance -> Stranger rows).
- Strained -> Broken after `strained_to_broken_ticks` with no repair, and
  Strained -> Feud via trust collapse (`social/conflict.py`'s
  `check_strained_timeout` / `check_feud_escalation` — both built during
  M5's initial pass but never actually invoked anywhere until this module,
  which is exactly why About/plan.md's T5.1 run never observed a Broken
  transition: nothing was checking for it).
- NEGLECT and CONTAGION (spec.md §7.1), the two scan-tied conflict
  triggers that have no single action to hang off of.

VALUE_CLASH (goals mutually exclusive) is NOT implemented here: goals are
free-text descriptions (About/runtime/goals.py) with no structured
representation of what they conflict *with*, so "mutually exclusive" has no
principled detector to build yet. A documented gap, not a silent one.
"""

from __future__ import annotations

import random
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from otherworld.models.relationship import BondState, ConflictTrigger, RelationshipEdge
from otherworld.persona.compiler import AgentBundle
from otherworld.runtime.determinism import seeded_uuid
from otherworld.social.conflict import (
    TRIGGER_BASE_SEVERITY,
    check_feud_escalation,
    check_strained_timeout,
    contagion_susceptibility,
    detect_neglect,
    open_conflict,
)
from otherworld.social.engine import apply_trust_decay, get_all_edges, ordered_pair, save_edge
from otherworld.social.state_machine import apply_decay

_BONDED_FOR_CONTAGION = (BondState.FRIEND, BondState.CLOSE_BOND)


async def run_maintenance_scan(
    session: AsyncSession,
    world_id: uuid.UUID,
    bundles: dict[uuid.UUID, AgentBundle],
    rng: random.Random,
    tick: int,
) -> None:
    edges = await get_all_edges(session, world_id)

    for edge in edges:
        updated = apply_trust_decay(edge, tick)
        updated = apply_decay(updated, tick)
        updated = check_strained_timeout(updated, tick)
        updated = check_feud_escalation(updated)
        if detect_neglect(updated, tick):
            updated = open_conflict(
                updated, ConflictTrigger.NEGLECT, theme="neglect", tick=tick, rng_id=seeded_uuid(rng)
            )
        if updated != edge:
            await save_edge(session, updated)
            edge = updated

    await _apply_contagion(session, edges, bundles, rng, tick)


async def _apply_contagion(
    session: AsyncSession,
    edges: list[RelationshipEdge],
    bundles: dict[uuid.UUID, AgentBundle],
    rng: random.Random,
    tick: int,
) -> None:
    """About/spec.md §7.1: "A Friend+ edge exists to an agent in a Feud with
    the target." For every agent A with a Friend+ edge to B, where B is
    feuding with some C, A inherits a scaled-down hostility trigger toward
    C — but only onto an edge that already exists between A and C; this
    doesn't materialise new edges for pairs who've never actually met, to
    stay consistent with edges being materialised lazily, on real encounters
    only (About/architecture.md §6.8).
    """
    friend_partners: dict[uuid.UUID, set[uuid.UUID]] = {}
    feud_partners: dict[uuid.UUID, set[uuid.UUID]] = {}
    edge_by_pair: dict[tuple[uuid.UUID, uuid.UUID], RelationshipEdge] = {}

    for edge in edges:
        pair = ordered_pair(edge.agent_a_id, edge.agent_b_id)
        edge_by_pair[pair] = edge
        if edge.bond_state in _BONDED_FOR_CONTAGION:
            friend_partners.setdefault(edge.agent_a_id, set()).add(edge.agent_b_id)
            friend_partners.setdefault(edge.agent_b_id, set()).add(edge.agent_a_id)
        elif edge.bond_state == BondState.FEUD:
            feud_partners.setdefault(edge.agent_a_id, set()).add(edge.agent_b_id)
            feud_partners.setdefault(edge.agent_b_id, set()).add(edge.agent_a_id)

    for agent_id, friends in friend_partners.items():
        bundle = bundles.get(agent_id)
        if bundle is None:
            continue
        loyalty = bundle.decision_weights.get("loyalty", 0.5)
        independence = bundle.decision_weights.get("independence", 0.5)
        susceptibility = contagion_susceptibility(loyalty, independence)
        if susceptibility <= 0.0:
            continue

        for friend_id in friends:
            for third_party_id in feud_partners.get(friend_id, set()):
                if third_party_id == agent_id:
                    continue
                pair = ordered_pair(agent_id, third_party_id)
                target_edge = edge_by_pair.get(pair)
                if target_edge is None:
                    continue
                base_severity = TRIGGER_BASE_SEVERITY[ConflictTrigger.CONTAGION] * susceptibility
                updated = open_conflict(
                    target_edge,
                    ConflictTrigger.CONTAGION,
                    theme="contagion",
                    tick=tick,
                    rng_id=seeded_uuid(rng),
                    base_severity_override=base_severity,
                )
                if updated != target_edge:
                    await save_edge(session, updated)
                    edge_by_pair[pair] = updated
