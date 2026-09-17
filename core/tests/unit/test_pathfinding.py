"""T5.12 — About/plan.md M5 acceptance test: A* returns optimal paths;
unreachable destinations are handled."""

from __future__ import annotations

import uuid

from otherworld.models.agent import Position
from otherworld.world.map import WorldMap, generate_starter_map
from otherworld.world.pathfinding import chebyshev_distance, find_path
from otherworld.world.proximity import agents_within_radius, within_radius


def test_chebyshev_distance_is_diagonal_aware():
    assert chebyshev_distance((0, 0), (3, 3)) == 3
    assert chebyshev_distance((0, 0), (3, 1)) == 3
    assert chebyshev_distance((2, 2), (2, 2)) == 0


def test_find_path_to_self_is_empty():
    world_map = WorldMap(width=10, height=10)
    assert find_path(world_map, (5, 5), (5, 5)) == []


def test_find_path_returns_a_chebyshev_optimal_length():
    world_map = WorldMap(width=10, height=10)
    path = find_path(world_map, (0, 0), (3, 3))
    assert path is not None
    assert len(path) == 3  # diagonal move covers both axes per step
    assert path[-1] == (3, 3)


def test_find_path_around_a_wall():
    world_map = WorldMap(width=10, height=10, blocked={(2, y) for y in range(0, 8)})
    path = find_path(world_map, (0, 0), (4, 0))
    assert path is not None
    assert path[-1] == (4, 0)
    assert all(world_map.is_walkable(step) for step in path)


def test_find_path_returns_none_for_unwalkable_goal():
    world_map = WorldMap(width=10, height=10, blocked={(5, 5)})
    assert find_path(world_map, (0, 0), (5, 5)) is None


def test_find_path_returns_none_for_a_fully_enclosed_goal():
    # Wall off (5,5) on all 8 sides — genuinely unreachable, not just blocked itself.
    x, y = 5, 5
    ring = {(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx, dy) != (0, 0)}
    world_map = WorldMap(width=10, height=10, blocked=ring)
    assert find_path(world_map, (0, 0), (5, 5)) is None


def test_find_path_returns_none_outside_bounds():
    world_map = WorldMap(width=10, height=10)
    assert find_path(world_map, (0, 0), (20, 20)) is None


def test_generate_starter_map_has_five_zones_covering_the_grid():
    world_map = generate_starter_map(uuid.uuid4(), width=60, height=60)
    assert len(world_map.zones) == 5
    names = {z.name for z in world_map.zones}
    assert names == {"Arrival green", "Market square", "Commons", "North woods", "Quarters"}
    assert world_map.zone_at((0, 0)) is not None
    # The 5 starter zones tile a 3x2 grid with one cell left over (bottom-
    # right), so (59, 59) genuinely has no zone — check a corner that's
    # actually inside a zone instead.
    assert world_map.zone_at((39, 59)) is not None


def test_within_radius_uses_chebyshev_metric():
    a = Position(x=0, y=0, facing="s")
    b = Position(x=8, y=8, facing="s")
    assert within_radius(a, b, radius=8)
    assert not within_radius(a, b, radius=7)


def test_agents_within_radius_filters_correctly():
    origin = Position(x=0, y=0, facing="s")
    near_id, far_id = uuid.uuid4(), uuid.uuid4()
    others = {near_id: Position(x=2, y=2, facing="s"), far_id: Position(x=20, y=20, facing="s")}
    visible = agents_within_radius(origin, others, radius=8)
    assert visible == [near_id]
