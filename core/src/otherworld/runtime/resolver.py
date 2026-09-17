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
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from otherworld.llm.protocol import LLMProvider
from otherworld.models.agent import Position
from otherworld.models.events import EventRecord, event_to_orm
from otherworld.models.memory import MemoryKind, MemoryRecord, MemoryRecordORM, memory_from_orm, memory_to_orm
from otherworld.models.relationship import BondState, RelationshipEdge
from otherworld.persona.compiler import AgentBundle
from otherworld.runtime.clock import tick_to_datetime
from otherworld.runtime.determinism import seeded_uuid
from otherworld.social.conflict import apply_conflict_consequences
from otherworld.social.engine import TRUST_DELTAS, apply_trust_delta, get_or_create_edge, save_edge
from otherworld.social.gossip import GossipService, check_pileon_for_subject, save_propagated_belief
from otherworld.social.state_machine import (
    attempt_reconciliation,
    has_repaired_conflict,
    is_costly_loyalty_act,
    is_social_interaction,
    promote_if_eligible,
)

_GOSSIP_ACTION = "confide"

# Base importance per event class, About/spec.md §5.1. Actions not listed
# here default to the routine baseline. First encounters and relationship
# state changes override this to their own (higher) class importance
# regardless of which action triggered them — and a single action can be
# both at once (a first-ever greet that immediately promotes Stranger ->
# Acquaintance), in which case the higher of the two applies.
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
_RELATIONSHIP_STATE_CHANGE_IMPORTANCE = 0.75
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


async def _maybe_gossip(
    session: AsyncSession,
    provider: LLMProvider,
    rng: random.Random,
    actor_id: uuid.UUID,
    listener_id: uuid.UUID,
    params: dict[str, Any],
    trust_ab: float,
    tick: int,
    created_at: datetime,
) -> None:
    """`confide` sharing a belief — About/spec.md §8.1's gossip pipeline. A
    no-op if `params` doesn't carry a valid `belief_id`/`about_agent_id`
    (a legitimate, un-modelled use of `confide` — the model chose it without
    gossip content) or if the referenced belief doesn't check out (not the
    actor's, not actually about who they claimed).
    """
    try:
        belief_id = uuid.UUID(str(params.get("belief_id")))
        about_agent_id = uuid.UUID(str(params.get("about_agent_id")))
    except (TypeError, ValueError):
        return

    row = await session.get(MemoryRecordORM, belief_id)
    if row is None or row.agent_id != actor_id or row.kind != MemoryKind.BELIEF.value:
        return
    if about_agent_id not in row.subjects:
        return

    pileon = await check_pileon_for_subject(session, about_agent_id, excluding_agent_id=listener_id)
    if pileon.suppressed:
        return

    propagated = await GossipService.propagate(
        provider, rng, memory_from_orm(row), listener_id, about_agent_id, trust_ab, tick, created_at
    )
    if propagated is not None:
        await save_propagated_belief(session, propagated)


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
        bundles: dict[uuid.UUID, AgentBundle] | None = None,
        params: dict[str, Any] | None = None,
        damping_factor: float = 1.0,
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
        # `take` (About/spec.md §7.1's RESOURCE_COMPETITION trigger, and
        # TRUST_DELTAS) is categorised MATERIAL, not SOCIAL/RELATIONAL — it
        # still carries a modelled relationship consequence, so it must
        # reach the edge-update loop below even though it isn't a "social
        # interaction" in the narrower, category sense `is_social_interaction`
        # tests for elsewhere (Friend-eligibility, close-bond gating).
        social = (is_social_interaction(action) or action in TRUST_DELTAS) and bool(targets)

        # Resolve trust and bond-state consequences first, using only
        # shared memories that already existed before this tick — this
        # tick's own (not-yet-written) memories are appended to the edge
        # afterward, once we know their final importance. That ordering is
        # what lets us tell, below, whether THIS action just caused a
        # promotion, so its own importance can reflect that.
        edges: dict[uuid.UUID, RelationshipEdge] = {}
        relationship_deltas: list[dict[str, object]] = []
        state_changed = False
        for target_id in targets if social else []:
            edge, _created = await get_or_create_edge(
                session, world_id, actor_id, target_id, seeded_uuid(rng), tick
            )
            before_state, before_trust = edge.bond_state, edge.trust

            edge = apply_trust_delta(edge, action)
            edge = edge.model_copy(
                update={"contact_count": edge.contact_count + 1, "last_contact_tick": tick}
            )

            if edge.bond_state in (BondState.BROKEN, BondState.FEUD):
                edge = attempt_reconciliation(edge, action)
            else:
                target_traits = (bundles or {}).get(target_id)
                weights = target_traits.decision_weights if target_traits else {}
                edge = apply_conflict_consequences(
                    edge,
                    action,
                    witnessed=bool(witnesses),
                    tick=tick,
                    rng=rng,
                    target_forgiveness=weights.get("forgiveness", 0.5),
                    target_grudge_retention=weights.get("grudge_retention", 0.5),
                    damping_factor=damping_factor,
                )

            max_shared = await _max_shared_importance(session, edge.shared_memory_ids)
            edge = promote_if_eligible(
                edge,
                max_shared,
                has_repaired_conflict=has_repaired_conflict(edge),
                costly_loyalty_act_this_tick=is_costly_loyalty_act(action),
            )

            edges[target_id] = edge
            state_changed = state_changed or edge.bond_state != before_state
            relationship_deltas.append(
                {
                    "target_id": str(target_id),
                    "trust_before": before_trust,
                    "trust_after": edge.trust,
                    "bond_state_before": before_state.value,
                    "bond_state_after": edge.bond_state.value,
                }
            )

        importance = importance_for_action(action)
        if first_encounter:
            importance = max(importance, _FIRST_ENCOUNTER_IMPORTANCE)
        if state_changed:
            importance = max(importance, _RELATIONSHIP_STATE_CHANGE_IMPORTANCE)
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

        # Now that this tick's memories exist and carry their final
        # importance, fold their ids into the edge's shared history so a
        # *future* tick's Friend-eligibility check (About/spec.md §6.4) can
        # see them.
        for target_id, edge in edges.items():
            edge = edge.model_copy(
                update={"shared_memory_ids": [*edge.shared_memory_ids, *memory_ids_by_target[target_id]]}
            )
            await save_edge(session, edge)

        if action == _GOSSIP_ACTION and len(targets) == 1 and targets[0] in edges:
            await _maybe_gossip(
                session, provider, rng, actor_id, targets[0], params or {},
                edges[targets[0]].trust, tick, created_at,
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
