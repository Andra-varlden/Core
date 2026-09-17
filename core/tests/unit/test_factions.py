"""About/plan.md M5: faction detection (About/spec.md §8.3) — cliques,
faction pairs, and exclusion candidates, over an in-memory edge list."""

from __future__ import annotations

import uuid

from otherworld.models.relationship import BondState, RelationshipEdge
from otherworld.social.factions import find_cliques, find_exclusion_candidates, find_faction_pairs

A, B, C, D, E, F = (uuid.UUID(int=i) for i in range(1, 7))


def _edge(a: uuid.UUID, b: uuid.UUID, bond_state: BondState) -> RelationshipEdge:
    lo, hi = sorted([a, b], key=str)
    return RelationshipEdge(
        id=uuid.uuid4(), world_id=uuid.uuid4(), agent_a_id=lo, agent_b_id=hi,
        trust=0.5, bond_state=bond_state, last_contact_tick=0, created_tick=0,
    )


def test_find_cliques_requires_a_connected_triangle_or_larger():
    edges = [
        _edge(A, B, BondState.FRIEND),
        _edge(B, C, BondState.FRIEND),
        _edge(A, C, BondState.FRIEND),
    ]
    cliques = find_cliques(edges)
    assert len(cliques) == 1
    assert cliques[0].members == frozenset({A, B, C})


def test_find_cliques_excludes_components_smaller_than_minimum():
    edges = [_edge(A, B, BondState.FRIEND)]
    assert find_cliques(edges) == []


def test_find_cliques_ignores_non_friend_edges():
    edges = [
        _edge(A, B, BondState.ACQUAINTANCE),
        _edge(B, C, BondState.STRANGER),
        _edge(A, C, BondState.STRAINED),
    ]
    assert find_cliques(edges) == []


def test_find_cliques_close_bond_counts_as_friend_plus():
    edges = [
        _edge(A, B, BondState.CLOSE_BOND),
        _edge(B, C, BondState.FRIEND),
        _edge(A, C, BondState.FRIEND),
    ]
    assert len(find_cliques(edges)) == 1


def test_find_faction_pairs_requires_a_qualifying_feud_edge():
    # Two triangles, A-B-C and D-E-F, linked by a Feud edge between
    # sufficiently-connected members of each.
    edges = [
        _edge(A, B, BondState.FRIEND), _edge(B, C, BondState.FRIEND), _edge(A, C, BondState.FRIEND),
        _edge(D, E, BondState.FRIEND), _edge(E, F, BondState.FRIEND), _edge(D, F, BondState.FRIEND),
        _edge(A, D, BondState.FEUD),
    ]
    cliques = find_cliques(edges)
    pairs = find_faction_pairs(edges, cliques)
    assert len(pairs) == 1


def test_find_faction_pairs_rejects_a_feud_from_a_low_degree_member():
    # G joins the {A,B,C} clique via a single Friend edge to A, giving G
    # Friend+ degree 1 within that clique — below the >= 2 threshold, so a
    # feud from G shouldn't produce a faction pair even though G is now a
    # member of the (now 4-agent) clique.
    G = uuid.UUID(int=7)
    edges = [
        _edge(A, B, BondState.FRIEND), _edge(B, C, BondState.FRIEND), _edge(A, C, BondState.FRIEND),
        _edge(A, G, BondState.FRIEND),  # G's only Friend+ edge into the clique
        _edge(D, E, BondState.FRIEND), _edge(E, F, BondState.FRIEND), _edge(D, F, BondState.FRIEND),
        _edge(G, D, BondState.FEUD),
    ]
    cliques = find_cliques(edges)
    clique_with_g = next(c for c in cliques if G in c.members)
    assert clique_with_g.members == frozenset({A, B, C, G})
    assert find_faction_pairs(edges, cliques) == []


def test_find_exclusion_candidates_flags_acquaintance_only_outsider():
    outsider = uuid.UUID(int=99)
    edges = [
        _edge(A, B, BondState.FRIEND), _edge(B, C, BondState.FRIEND), _edge(A, C, BondState.FRIEND),
        _edge(outsider, A, BondState.ACQUAINTANCE),
        _edge(outsider, B, BondState.ACQUAINTANCE),
        _edge(outsider, C, BondState.ACQUAINTANCE),
    ]
    cliques = find_cliques(edges)
    candidates = find_exclusion_candidates(edges, cliques)
    assert len(candidates) == 1
    assert candidates[0].agent_id == outsider


def test_find_exclusion_candidates_excludes_agents_with_a_friend_edge_in():
    outsider = uuid.UUID(int=99)
    edges = [
        _edge(A, B, BondState.FRIEND), _edge(B, C, BondState.FRIEND), _edge(A, C, BondState.FRIEND),
        _edge(outsider, A, BondState.ACQUAINTANCE),
        _edge(outsider, B, BondState.ACQUAINTANCE),
        _edge(outsider, C, BondState.FRIEND),  # has a Friend+ edge in — not excluded
    ]
    cliques = find_cliques(edges)
    assert find_exclusion_candidates(edges, cliques) == []


def test_find_exclusion_candidates_requires_the_full_threshold():
    outsider = uuid.UUID(int=99)
    edges = [
        _edge(A, B, BondState.FRIEND), _edge(B, C, BondState.FRIEND), _edge(A, C, BondState.FRIEND),
        _edge(outsider, A, BondState.ACQUAINTANCE),
        _edge(outsider, B, BondState.ACQUAINTANCE),
        # only 2 acquaintance edges in, threshold is 3
    ]
    cliques = find_cliques(edges)
    assert find_exclusion_candidates(edges, cliques) == []
