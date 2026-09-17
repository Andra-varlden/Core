"""A* pathfinding over `world/map.py`'s `WorldMap`. Chebyshev distance
metric, 8-directional movement (About/spec.md §9.1)."""

from __future__ import annotations

import heapq

from otherworld.world.map import Coord, WorldMap

_NEIGHBOUR_OFFSETS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


def chebyshev_distance(a: Coord, b: Coord) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _reconstruct(came_from: dict[Coord, Coord], start: Coord, goal: Coord) -> list[Coord]:
    path = [goal]
    while path[-1] != start:
        path.append(came_from[path[-1]])
    path.reverse()
    return path[1:]  # the steps to take — excludes the current tile


def find_path(world_map: WorldMap, start: Coord, goal: Coord) -> list[Coord] | None:
    """Returns the steps from `start` to `goal`, excluding `start` itself
    and including `goal` — what `move_to` stores as `Agent.current_path`
    (About/spec.md §10: "consumed one tile per tick"). `[]` if already at
    the goal. `None` if the goal is unwalkable or unreachable.
    """
    if start == goal:
        return []
    if not world_map.is_walkable(goal):
        return None

    open_heap: list[tuple[int, int, Coord]] = [(chebyshev_distance(start, goal), 0, start)]
    came_from: dict[Coord, Coord] = {}
    best_g: dict[Coord, int] = {start: 0}
    closed: set[Coord] = set()

    while open_heap:
        _, g, current = heapq.heappop(open_heap)
        if current in closed:
            continue
        if current == goal:
            return _reconstruct(came_from, start, goal)
        closed.add(current)

        for dx, dy in _NEIGHBOUR_OFFSETS:
            neighbour = (current[0] + dx, current[1] + dy)
            if neighbour in closed or not world_map.is_walkable(neighbour):
                continue
            tentative_g = g + 1
            if tentative_g < best_g.get(neighbour, tentative_g + 1):
                best_g[neighbour] = tentative_g
                came_from[neighbour] = current
                f_score = tentative_g + chebyshev_distance(neighbour, goal)
                heapq.heappush(open_heap, (f_score, tentative_g, neighbour))

    return None
