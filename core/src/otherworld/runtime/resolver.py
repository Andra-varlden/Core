"""The resolver. See About/architecture.md §4, About/spec.md §5.1.

Writes the memory and event record that a validated action produces.
Invariant I6: every executed action produces exactly one event record,
written here.
"""

from __future__ import annotations

import random
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from otherworld.llm.protocol import LLMProvider
from otherworld.models.agent import Position
from otherworld.models.events import EventRecord, event_to_orm
from otherworld.models.memory import MemoryKind, MemoryRecord, memory_to_orm
from otherworld.runtime.clock import tick_to_datetime
from otherworld.runtime.determinism import seeded_uuid

# Base importance per event class, About/spec.md §5.1. Actions not listed
# here default to the routine baseline — M2's world only ever produces
# idle/sleep organically; the rest are filled in as later milestones add
# the behaviour that produces them (first encounters, conflicts, ...).
_BASE_IMPORTANCE: dict[str, float] = {
    "idle": 0.05,
    "sleep": 0.05,
    "move_to": 0.05,
    "follow": 0.05,
    "flee": 0.05,
    "greet": 0.15,
    "speak_to": 0.15,
    "betray": 0.95,
}
_DEFAULT_IMPORTANCE = 0.05

# [TUNE] No memory below this importance gets written at all. 0.0 for now —
# spec.md's compression machinery (§5.4), not a write-time cutoff, is what
# keeps volume bounded; revisit once M5 gives real traffic to tune against.
MIN_IMPORTANCE_TO_REMEMBER = 0.0


def importance_for_action(action: str) -> float:
    return _BASE_IMPORTANCE.get(action, _DEFAULT_IMPORTANCE)


class Resolver:
    @staticmethod
    async def resolve(
        session: AsyncSession,
        provider: LLMProvider,
        rng: random.Random,
        world_id: uuid.UUID,
        actor_id: uuid.UUID,
        position: Position,
        tick: int,
        action: str,
        targets: list[uuid.UUID],
        reasoning: str,
    ) -> EventRecord:
        importance = importance_for_action(action)
        created_at = tick_to_datetime(tick)

        if importance >= MIN_IMPORTANCE_TO_REMEMBER:
            content = f"I did '{action}' at tick {tick}." + (f" ({reasoning})" if reasoning else "")
            embedding = await provider.embed(content)
            memory = MemoryRecord(
                id=seeded_uuid(rng),
                agent_id=actor_id,
                kind=MemoryKind.EPISODIC,
                content=content,
                embedding=embedding,
                importance=importance,
                tick=tick,
                subjects=[actor_id, *targets],
                source_event_id=None,
                derived_from=[],
                created_at=created_at,
            )
            session.add(memory_to_orm(memory))

        event = EventRecord(
            id=seeded_uuid(rng),
            world_id=world_id,
            tick=tick,
            actor_id=actor_id,
            action=action,
            targets=targets,
            witnesses=[],
            position=position,
            relationship_deltas=[],
            importance=importance,
            owner_override=False,
            created_at=created_at,
        )
        session.add(event_to_orm(event))
        await session.flush()
        return event
