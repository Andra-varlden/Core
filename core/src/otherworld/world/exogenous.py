"""Exogenous events. See About/spec.md §9.5.

Periodic, system-injected world-level events, not tied to any single
agent's decision. What's implemented here is the scheduling mechanism
(when each event type is due) and the event itself firing — fully tested
against spec's frequencies. Downstream *effects* ("changes resource
availability", "a goal requiring 3+ agents") need a resource/feature system
this codebase doesn't have yet (About/models/world.py's `Feature` exists as
a shape but nothing populates or consumes it), so firing an event today
means it's recorded and observable, not yet that anything mechanically
reacts to it. That's the wiring gap here, parallel to the ones documented
in `social/gossip.py` and `social/factions.py`.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import StrEnum

from otherworld.config import settings

_MINUTES_PER_DAY = 24 * 60


def ticks_per_day() -> int:
    return _MINUTES_PER_DAY // settings.world.in_world_minutes_per_tick


class ExogenousEventType(StrEnum):
    SEASONAL_SHIFT = "seasonal_shift"
    RESOURCE_SCARCITY = "resource_scarcity"
    SHARED_CHALLENGE = "shared_challenge"


@dataclass(frozen=True)
class ExogenousEvent:
    kind: ExogenousEventType
    tick: int


def next_seasonal_shift_tick(last_tick: int) -> int:
    return last_tick + 7 * ticks_per_day()


def next_resource_scarcity_tick(last_tick: int, rng: random.Random) -> int:
    """About/spec.md §9.5: every 3-5 in-world days — a range, not a fixed
    period, so each occurrence rolls its own interval."""
    days = rng.uniform(3.0, 5.0)
    return last_tick + round(days * ticks_per_day())


def next_shared_challenge_tick(last_tick: int) -> int:
    return last_tick + 10 * ticks_per_day()


class ExogenousEventScheduler:
    """Tracks each event type's next-due tick and fires whichever are due
    on a given tick. `New zone opening` (About/spec.md §9.5's fourth event)
    is milestone-based, not periodic, and has no map-expansion mechanism to
    trigger yet — deliberately not modelled here.
    """

    def __init__(self, rng: random.Random, start_tick: int = 0) -> None:
        self._rng = rng
        self._next_seasonal_shift = next_seasonal_shift_tick(start_tick)
        self._next_resource_scarcity = next_resource_scarcity_tick(start_tick, rng)
        self._next_shared_challenge = next_shared_challenge_tick(start_tick)

    def maybe_fire(self, tick: int) -> list[ExogenousEvent]:
        fired: list[ExogenousEvent] = []

        if tick >= self._next_seasonal_shift:
            fired.append(ExogenousEvent(ExogenousEventType.SEASONAL_SHIFT, tick))
            self._next_seasonal_shift = next_seasonal_shift_tick(tick)

        if tick >= self._next_resource_scarcity:
            fired.append(ExogenousEvent(ExogenousEventType.RESOURCE_SCARCITY, tick))
            self._next_resource_scarcity = next_resource_scarcity_tick(tick, self._rng)

        if tick >= self._next_shared_challenge:
            fired.append(ExogenousEvent(ExogenousEventType.SHARED_CHALLENGE, tick))
            self._next_shared_challenge = next_shared_challenge_tick(tick)

        return fired
