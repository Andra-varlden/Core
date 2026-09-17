"""Faction detection. See About/spec.md §8.3.

A pure batch computation over the whole relationship graph, recomputed
periodically (About/config.py's `FactionsConfig.scan_interval_ticks`) —
unlike bond-state transitions or conflict triggers, nothing here is tied to
a single action or a single edge, so it lives apart from `social/engine.py`
and `social/conflict.py` and takes a full edge list rather than one edge.

Exclusion signals require *persistence* over `exclusion_persistence_ticks`,
which a single snapshot can't determine on its own — `find_exclusion_
candidates` reports what's true of this scan; a caller tracking candidates
across scans (a small `{(agent_id, clique): first_seen_tick}` map) decides
whether a candidate has persisted long enough to actually raise the watch
signal. No such caller exists yet (there's no periodic scan scheduler for
this milestone's faction/gossip system, unlike reflection/compression which
run every tick inline) — that's the wiring gap here, parallel to
`social/gossip.py`'s documented one.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from otherworld.config import settings
from otherworld.models.relationship import BondState, RelationshipEdge

_FRIEND_PLUS = (BondState.FRIEND, BondState.CLOSE_BOND)


@dataclass(frozen=True)
class Clique:
    members: frozenset[uuid.UUID]


@dataclass(frozen=True)
class FactionPair:
    clique_a: Clique
    clique_b: Clique


@dataclass(frozen=True)
class ExclusionCandidate:
    agent_id: uuid.UUID
    clique: Clique


def _friend_adjacency(edges: list[RelationshipEdge]) -> dict[uuid.UUID, set[uuid.UUID]]:
    adjacency: dict[uuid.UUID, set[uuid.UUID]] = {}
    for edge in edges:
        if edge.bond_state in _FRIEND_PLUS:
            adjacency.setdefault(edge.agent_a_id, set()).add(edge.agent_b_id)
            adjacency.setdefault(edge.agent_b_id, set()).add(edge.agent_a_id)
    return adjacency


def find_cliques(edges: list[RelationshipEdge]) -> list[Clique]:
    """Connected components of the Friend+ subgraph, size >= `min_clique_size`."""
    adjacency = _friend_adjacency(edges)
    seen: set[uuid.UUID] = set()
    cliques: list[Clique] = []
    for node in adjacency:
        if node in seen:
            continue
        component: set[uuid.UUID] = set()
        stack = [node]
        while stack:
            current = stack.pop()
            if current in component:
                continue
            component.add(current)
            stack.extend(adjacency.get(current, set()) - component)
        seen |= component
        if len(component) >= settings.factions.min_clique_size:
            cliques.append(Clique(members=frozenset(component)))
    return cliques


def _clique_degree(agent_id: uuid.UUID, clique: Clique, adjacency: dict[uuid.UUID, set[uuid.UUID]]) -> int:
    return len(adjacency.get(agent_id, set()) & clique.members)


def find_faction_pairs(edges: list[RelationshipEdge], cliques: list[Clique]) -> list[FactionPair]:
    """Two cliques joined by at least one Feud edge between members with
    Friend+ degree >= `min_clique_degree_for_pair` within their own clique.
    """
    adjacency = _friend_adjacency(edges)
    feud_edges = [e for e in edges if e.bond_state == BondState.FEUD]

    pairs: list[FactionPair] = []
    for i, clique_a in enumerate(cliques):
        for clique_b in cliques[i + 1 :]:
            for feud in feud_edges:
                if feud.agent_a_id in clique_a.members and feud.agent_b_id in clique_b.members:
                    u, v = feud.agent_a_id, feud.agent_b_id
                elif feud.agent_b_id in clique_a.members and feud.agent_a_id in clique_b.members:
                    u, v = feud.agent_b_id, feud.agent_a_id
                else:
                    continue
                if (
                    _clique_degree(u, clique_a, adjacency) >= settings.factions.min_clique_degree_for_pair
                    and _clique_degree(v, clique_b, adjacency)
                    >= settings.factions.min_clique_degree_for_pair
                ):
                    pairs.append(FactionPair(clique_a=clique_a, clique_b=clique_b))
                    break
    return pairs


def find_exclusion_candidates(
    edges: list[RelationshipEdge], cliques: list[Clique]
) -> list[ExclusionCandidate]:
    """This scan's snapshot of agents who look excluded from a clique: 3+
    Acquaintance edges into it, zero Friend+ edges into it. Whether this
    has *persisted* long enough to raise the actual watch signal is the
    caller's job (see module docstring)."""
    candidates: list[ExclusionCandidate] = []
    for clique in cliques:
        for edge in edges:
            for outsider, member in ((edge.agent_a_id, edge.agent_b_id), (edge.agent_b_id, edge.agent_a_id)):
                if outsider in clique.members or member not in clique.members:
                    continue
                if edge.bond_state != BondState.ACQUAINTANCE:
                    continue
                acquaintance_count = sum(
                    1
                    for e in edges
                    if e.bond_state == BondState.ACQUAINTANCE
                    and (
                        (e.agent_a_id == outsider and e.agent_b_id in clique.members)
                        or (e.agent_b_id == outsider and e.agent_a_id in clique.members)
                    )
                )
                has_friend_edge = any(
                    e.bond_state in _FRIEND_PLUS
                    and (
                        (e.agent_a_id == outsider and e.agent_b_id in clique.members)
                        or (e.agent_b_id == outsider and e.agent_a_id in clique.members)
                    )
                    for e in edges
                )
                if (
                    acquaintance_count >= settings.factions.exclusion_acquaintance_threshold
                    and not has_friend_edge
                ):
                    candidates.append(ExclusionCandidate(agent_id=outsider, clique=clique))
                break
    # de-duplicate: the inner loop can visit the same (outsider, clique) pair
    # more than once across its several qualifying edges.
    seen: set[tuple[uuid.UUID, frozenset[uuid.UUID]]] = set()
    unique: list[ExclusionCandidate] = []
    for candidate in candidates:
        key = (candidate.agent_id, candidate.clique.members)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique
