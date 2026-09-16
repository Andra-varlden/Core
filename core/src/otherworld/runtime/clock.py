"""Tick-based time. See About/architecture.md §13: "No wall-clock time in
decision logic; use tick numbers." Every timestamp the runtime writes is a
pure function of the tick number, never of the system clock — required for
the determinism guarantee (About/plan.md T2.2, T2.10).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from otherworld.config import settings

# An arbitrary fixed origin. What matters is that it never moves and never
# comes from the wall clock.
WORLD_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


def tick_to_datetime(tick: int) -> datetime:
    return WORLD_EPOCH + timedelta(seconds=tick * settings.world.tick_seconds)
