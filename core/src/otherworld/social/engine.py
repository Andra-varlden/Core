"""The relationship engine. See About/architecture.md §6.5, About/spec.md §6.

Edges are materialised lazily — a world with N agents does not pre-create
N²/2 rows (About/architecture.md §6.8). Always stored with
`agent_a_id < agent_b_id` so a pair has exactly one row (invariant enforced
again at the DB level, About/models/relationship.py).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from otherworld.config import settings
from otherworld.models.relationship import (
    BondState,
    RelationshipEdge,
    RelationshipEdgeORM,
    edge_from_orm,
    edge_to_orm,
)

# Delta applied to the edge's single shared `trust` scalar on a successful,
# unconditional interaction. About/spec.md §6.2's table gives most rows a
# single "both sides" number, which maps exactly onto our one-scalar model;
# rows with genuinely asymmetric numbers for both parties (compliment, give)
# don't have a faithful single-scalar mapping and are deferred, alongside
# interactions whose delta depends on a response the target hasn't modelled
# yet (confide, request, trade — "was it reciprocated?").
TRUST_DELTAS: dict[str, float] = {
    "greet": 0.03,
    "criticise": -0.10,
    "reject": -0.15,
    "take": -0.30,
    "betray": -0.50,
    "apologise": 0.20,
    "forgive": 0.25,
}


def ordered_pair(a: uuid.UUID, b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    return (a, b) if str(a) < str(b) else (b, a)


async def get_edge(
    session: AsyncSession, world_id: uuid.UUID, agent_a: uuid.UUID, agent_b: uuid.UUID
) -> RelationshipEdge | None:
    a, b = ordered_pair(agent_a, agent_b)
    row = (
        await session.execute(
            select(RelationshipEdgeORM).where(
                RelationshipEdgeORM.world_id == world_id,
                RelationshipEdgeORM.agent_a_id == a,
                RelationshipEdgeORM.agent_b_id == b,
            )
        )
    ).scalar_one_or_none()
    return edge_from_orm(row) if row else None


async def get_or_create_edge(
    session: AsyncSession,
    world_id: uuid.UUID,
    agent_a: uuid.UUID,
    agent_b: uuid.UUID,
    edge_id: uuid.UUID,
    tick: int,
) -> tuple[RelationshipEdge, bool]:
    """Returns (edge, created). `edge_id` comes from the caller's seeded RNG
    (About/runtime/determinism.py) so a fresh edge's id stays deterministic.
    """
    existing = await get_edge(session, world_id, agent_a, agent_b)
    if existing is not None:
        return existing, False

    a, b = ordered_pair(agent_a, agent_b)
    edge = RelationshipEdge(
        id=edge_id,
        world_id=world_id,
        agent_a_id=a,
        agent_b_id=b,
        trust=0.0,
        bond_state=BondState.STRANGER,
        seeded=False,
        conflict_log=[],
        shared_memory_ids=[],
        contact_count=0,
        last_contact_tick=tick,
        created_tick=tick,
    )
    await session.merge(edge_to_orm(edge))
    await session.flush()
    return edge, True


async def save_edge(session: AsyncSession, edge: RelationshipEdge) -> None:
    await session.merge(edge_to_orm(edge))
    await session.flush()


def apply_trust_delta(edge: RelationshipEdge, action: str) -> RelationshipEdge:
    """Returns a new edge with the trust delta for `action` applied
    (About/spec.md §6.2, matched exactly — see TRUST_DELTAS). Unrecognised
    actions leave trust unchanged — not every action in the registry has a
    modelled social consequence yet.
    """
    if action not in TRUST_DELTAS:
        return edge
    new_trust = max(-1.0, min(1.0, edge.trust + TRUST_DELTAS[action]))
    return edge.model_copy(update={"trust": new_trust})


def is_friend_eligible(edge: RelationshipEdge, max_shared_memory_importance: float) -> bool:
    return (
        edge.trust >= settings.relationships.friend_trust_threshold
        and max_shared_memory_importance >= settings.relationships.friend_shared_memory_importance
    )
