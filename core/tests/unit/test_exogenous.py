"""About/plan.md M5: exogenous event scheduling (About/spec.md §9.5)."""

from __future__ import annotations

import random

from otherworld.world.exogenous import (
    ExogenousEventScheduler,
    ExogenousEventType,
    next_resource_scarcity_tick,
    next_seasonal_shift_tick,
    next_shared_challenge_tick,
    ticks_per_day,
)


def test_ticks_per_day_matches_time_mapping():
    assert ticks_per_day() == 144  # 1440 minutes / 10 minutes-per-tick


def test_seasonal_shift_is_every_seven_days():
    assert next_seasonal_shift_tick(0) == 7 * ticks_per_day()


def test_shared_challenge_is_every_ten_days():
    assert next_shared_challenge_tick(0) == 10 * ticks_per_day()


def test_resource_scarcity_falls_within_three_to_five_days():
    rng = random.Random(1)
    for _ in range(20):
        interval = next_resource_scarcity_tick(0, rng)
        assert 3 * ticks_per_day() <= interval <= 5 * ticks_per_day()


def test_scheduler_does_not_fire_before_any_interval_elapses():
    scheduler = ExogenousEventScheduler(random.Random(1), start_tick=0)
    assert scheduler.maybe_fire(tick=1) == []


def test_scheduler_fires_seasonal_shift_on_schedule_and_reschedules():
    scheduler = ExogenousEventScheduler(random.Random(1), start_tick=0)
    due_tick = 7 * ticks_per_day()

    fired = scheduler.maybe_fire(due_tick)
    kinds = {e.kind for e in fired}
    assert ExogenousEventType.SEASONAL_SHIFT in kinds

    # It shouldn't fire again immediately on the very next tick.
    assert ExogenousEventType.SEASONAL_SHIFT not in {e.kind for e in scheduler.maybe_fire(due_tick + 1)}


def test_scheduler_can_fire_multiple_due_events_on_the_same_tick():
    scheduler = ExogenousEventScheduler(random.Random(1), start_tick=0)
    far_future = 100 * ticks_per_day()
    fired = scheduler.maybe_fire(far_future)
    kinds = {e.kind for e in fired}
    assert ExogenousEventType.SEASONAL_SHIFT in kinds
    assert ExogenousEventType.RESOURCE_SCARCITY in kinds
    assert ExogenousEventType.SHARED_CHALLENGE in kinds
