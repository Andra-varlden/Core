"""Chebyshev-distance proximity checks. See About/spec.md §9.1 —
`perception_radius` and `interaction_radius` are both defined in this
metric, not Euclidean."""

from __future__ import annotations

import uuid

from otherworld.models.agent import Position
from otherworld.world.pathfinding import chebyshev_distance


def within_radius(a: Position, b: Position, radius: int) -> bool:
    return chebyshev_distance((a.x, a.y), (b.x, b.y)) <= radius


def agents_within_radius(
    origin: Position, others: dict[uuid.UUID, Position], radius: int
) -> list[uuid.UUID]:
    return [agent_id for agent_id, pos in others.items() if within_radius(origin, pos, radius)]
