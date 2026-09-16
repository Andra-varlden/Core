"""Seeded randomness. See About/architecture.md §13: "All randomness goes
through a seeded RNG owned by the world."

This includes id generation during a simulation run: `uuid.uuid4()` draws
from `os.urandom` and would make two same-seed runs diverge on their very
first event, breaking the byte-identical replay guarantee (T2.2). Anything
written while ticking must use `seeded_uuid` instead.
"""

from __future__ import annotations

import random
import uuid


def seeded_uuid(rng: random.Random) -> uuid.UUID:
    return uuid.UUID(int=rng.getrandbits(128), version=4)
