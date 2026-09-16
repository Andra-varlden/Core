"""The resolver. See About/architecture.md §4, About/spec.md §5.1, §6.

Writes the memories and event record that a validated action produces.
Invariant I6: every executed action produces exactly one event record,
written here. From M3 on, a social/relational action with a target also
materialises the relationship edge, applies the trust delta, and checks
bond-state promotion — About/architecture.md §14.2's walkthrough: "episodic
memory written for A, for B, and for any witnesses; edge materialised."
"""

from __future__ import annotations

import random
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from otherworld.llm.protocol import LLMProvider
from otherworld.models.agent import Position
from otherworld.models.events import EventRecord, event_to_orm
from otherworld.models.memory import MemoryKind, MemoryRecord, MemoryRecordORM, memory_to_orm
from otherworld.models.relationship import RelationshipEdge
from otherworld.runtime.clock import tick_to_datetime
from otherworld.runtime.determinism import seeded_uuid
from otherworld.social.engine import apply_trust_delta, get_or_create_edge, save_edge
from otherworld.social.state_machine import is_social_interaction, promote_if_eligible

# Base importance per event class, About/spec.md §5.1. Actions not listed
# here default to the routine baseline; a first encounter with a previously
# unmet agent overrides this to _FIRST_ENCOUNTER_IMPORTANCE regardless of
# which action it was.
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
_FIRST_ENCOUNTER_IMPORTANCE = 0.60
_WITNESS_BONUS_THRESHOLD = 3
_WITNESS_BONUS = 0.10

# [TUNE] No memory below this importance gets written at all. 0.0 for now —
# spec.md's compression machinery (§5.4), not a write-time cutoff, is what
# keeps volume bounded; revisit once M5 gives real traffic to tune against.
MIN_IMPORTANCE_TO_REMEMBER = 0.0


def importance_for_action(action: str) -> float:
    return _BASE_IMPORTANCE.get(action, _DEFAULT_IMPORTANCE)


async def _max_shared_importance(session: AsyncSession, memory_ids: list[uuid.UUID]) -> float:
    if not memory_ids:
        return 0.0
    rows = (
        await session.execute(select(MemoryRecordORM.importance).where(MemoryRecordORM.id.in_(memory_ids)))
    ).scalars().all()
    return max(rows, default=0.0)


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
        witnesses: list[uuid.UUID] | None = None,
        first_encounter: bool = False,
    ) -> EventRecord:
        """`first_encounter`: whether any of `targets` was unmet before this
        tick. Passed in by the caller rather than inferred from edge
        creation here — by the time a multi-agent scheduler calls resolve,
        the edge has typically already been materialised in a prior,
        sequential encounter-detection pass (About/runtime/scheduler.py's
        `MultiAgentTickScheduler` docstring explains why that pass must be
        sequential), so `get_or_create_edge` below would always report
        `created=False` and silently lose the signal if we relied on it.
        """
        witnesses = witnesses or []
        created_at = tick_to_datetime(tick)
        social = is_social_interaction(action) and bool(targets)

        edges: dict[uuid.UUID, tuple[RelationshipEdge, bool]] = {}
        if social:
            for target_id in targets:
                edge, created = await get_or_create_edge(
                    session, world_id, actor_id, target_id, seeded_uuid(rng), tick
                )
                edges[target_id] = (edge, created)

        importance = _FIRST_ENCOUNTER_IMPORTANCE if first_encounter else importance_for_action(action)
        if len(witnesses) >= _WITNESS_BONUS_THRESHOLD:
            importance = min(1.0, importance + _WITNESS_BONUS)

        memory_ids_by_target: dict[uuid.UUID, list[uuid.UUID]] = {t: [] for t in targets}

        if importance >= MIN_IMPORTANCE_TO_REMEMBER:
            content = f"I did '{action}' at tick {tick}." + (f" ({reasoning})" if reasoning else "")
            embedding = await provider.embed(content)

            actor_memory_id = seeded_uuid(rng)
            session.add(
                memory_to_orm(
                    MemoryRecord(
                        id=actor_memory_id, agent_id=actor_id, kind=MemoryKind.EPISODIC, content=content,
                        embedding=embedding, importance=importance, tick=tick,
                        subjects=[actor_id, *targets], created_at=created_at,
                    )
                )
            )
            for target_id in targets:
                memory_ids_by_target[target_id].append(actor_memory_id)

            for target_id in targets:
                target_memory_id = seeded_uuid(rng)
                session.add(
                    memory_to_orm(
                        MemoryRecord(
                            id=target_memory_id, agent_id=target_id, kind=MemoryKind.EPISODIC,
                            content=f"Another agent did '{action}' to me at tick {tick}.",
                            embedding=embedding, importance=importance, tick=tick,
                            subjects=[actor_id, target_id], created_at=created_at,
                        )
                    )
                )
                memory_ids_by_target[target_id].append(target_memory_id)

            for witness_id in witnesses:
                session.add(
                    memory_to_orm(
                        MemoryRecord(
                            id=seeded_uuid(rng), agent_id=witness_id, kind=MemoryKind.EPISODIC,
                            content=f"I saw an agent do '{action}' at tick {tick}.",
                            embedding=embedding, importance=importance, tick=tick,
                            subjects=[actor_id, *targets], created_at=created_at,
                        )
                    )
                )

        relationship_deltas: list[dict[str, object]] = []
        for target_id in targets:
            if target_id not in edges:
                continue
            edge, _created = edges[target_id]
            before_state, before_trust = edge.bond_state, edge.trust

            edge = apply_trust_delta(edge, action)
            edge = edge.model_copy(
                update={
                    "shared_memory_ids": [*edge.shared_memory_ids, *memory_ids_by_target[target_id]],
                    "contact_count": edge.contact_count + 1,
                    "last_contact_tick": tick,
                }
            )
            max_shared = await _max_shared_importance(session, edge.shared_memory_ids)
            edge = promote_if_eligible(edge, max_shared)
            await save_edge(session, edge)

            relationship_deltas.append(
                {
                    "target_id": str(target_id),
                    "trust_before": before_trust,
                    "trust_after": edge.trust,
                    "bond_state_before": before_state.value,
                    "bond_state_after": edge.bond_state.value,
                }
            )

        event = EventRecord(
            id=seeded_uuid(rng),
            world_id=world_id,
            tick=tick,
            actor_id=actor_id,
            action=action,
            targets=targets,
            witnesses=witnesses,
            position=position,
            relationship_deltas=relationship_deltas,
            importance=importance,
            owner_override=False,
            created_at=created_at,
        )
        session.add(event_to_orm(event))
        await session.flush()
        return event
