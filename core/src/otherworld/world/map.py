"""The minimal tile world. See About/spec.md §9.1, §9.2.

ADR-008: the tile world is built last, and deliberately minimal — "movement
is real; visuals are not." This module exists to make `move_to`'s
precondition ("destination walkable and reachable") and proximity-gated
perception real, not to support a renderer. There is no renderer.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from otherworld.models.world import Zone

Coord = tuple[int, int]

# About/spec.md §9.2's Phase 1 starter set, laid out as a simple 3x2 grid of
# roughly equal rectangles (one cell unused) — enough structure for
# zone-aware perception and pathfinding without needing actual level design,
# since there's no renderer to design *for*.
_STARTER_ZONE_NAMES = ("Arrival green", "Market square", "Commons", "North woods", "Quarters")
_STARTER_ZONE_CELLS = ((0, 0), (1, 0), (2, 0), (0, 1), (1, 1))


@dataclass
class WorldMap:
    width: int
    height: int
    blocked: set[Coord] = field(default_factory=set)
    zones: list[Zone] = field(default_factory=list)

    def in_bounds(self, coord: Coord) -> bool:
        x, y = coord
        return 0 <= x < self.width and 0 <= y < self.height

    def is_walkable(self, coord: Coord) -> bool:
        return self.in_bounds(coord) and coord not in self.blocked

    def zone_at(self, coord: Coord) -> Zone | None:
        for zone in self.zones:
            x0, y0, x1, y1 = zone.bounds
            if x0 <= coord[0] <= x1 and y0 <= coord[1] <= y1:
                return zone
        return None


def generate_starter_map(world_id: uuid.UUID, width: int = 60, height: int = 60) -> WorldMap:
    cell_w, cell_h = width // 3, height // 2
    zones = []
    for name, (cx, cy) in zip(_STARTER_ZONE_NAMES, _STARTER_ZONE_CELLS, strict=True):
        x0, y0 = cx * cell_w, cy * cell_h
        x1 = (x0 + cell_w - 1) if cx < 2 else (width - 1)
        y1 = (y0 + cell_h - 1) if cy < 1 else (height - 1)
        zones.append(Zone(id=uuid.uuid4(), world_id=world_id, name=name, bounds=(x0, y0, x1, y1)))
    return WorldMap(width=width, height=height, zones=zones)
