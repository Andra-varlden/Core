"""Owner deletion cascade. See About/plan.md M6 T6.5, invariant I7: deleting
an owner removes all of *their own* data outright; anywhere their agent
appears only as a witness, target, or memory subject in someone ELSE's
data, that reference is anonymised (stripped), not deleted — the other
owner's own history stays intact, just with the departed agent's identity
gone from it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from otherworld.models.agent import AgentORM
from otherworld.models.auth import MagicLinkTokenORM
from otherworld.models.events import EventRecordORM
from otherworld.models.memory import MemoryRecordORM
from otherworld.models.output import RecognitionTrialORM
from otherworld.models.owner import OwnerORM
from otherworld.models.persona import PersonaObjectORM
from otherworld.models.relationship import RelationshipEdgeORM


@dataclass
class DeletionReceipt:
    owner_id: uuid.UUID
    deleted_at: datetime
    personas_deleted: int = 0
    agents_deleted: int = 0
    magic_link_tokens_deleted: int = 0
    recognition_trials_deleted: int = 0
    own_memories_deleted: int = 0
    own_events_deleted: int = 0
    relationship_edges_deleted: int = 0
    other_events_anonymised: int = 0
    other_memories_anonymised: int = 0


async def delete_owner(session: AsyncSession, owner_id: uuid.UUID) -> DeletionReceipt:
    """Idempotent-ish in spirit but not literally: a second call on an
    already-deleted owner just returns an all-zero receipt (nothing left to
    find), rather than raising — a retried delete request should never be
    an error.
    """
    receipt = DeletionReceipt(owner_id=owner_id, deleted_at=datetime.now(UTC))

    agent_ids = list(
        (await session.execute(select(AgentORM.id).where(AgentORM.owner_id == owner_id))).scalars().all()
    )
    agent_id_strs = {str(a) for a in agent_ids}

    # --- This owner's own data: hard delete. ---
    if agent_ids:
        receipt.own_memories_deleted = (
            await session.execute(delete(MemoryRecordORM).where(MemoryRecordORM.agent_id.in_(agent_ids)))
        ).rowcount
        receipt.own_events_deleted = (
            await session.execute(delete(EventRecordORM).where(EventRecordORM.actor_id.in_(agent_ids)))
        ).rowcount
        receipt.relationship_edges_deleted = (
            await session.execute(
                delete(RelationshipEdgeORM).where(
                    RelationshipEdgeORM.agent_a_id.in_(agent_ids)
                    | RelationshipEdgeORM.agent_b_id.in_(agent_ids)
                )
            )
        ).rowcount

    receipt.agents_deleted = (
        await session.execute(delete(AgentORM).where(AgentORM.owner_id == owner_id))
    ).rowcount
    receipt.personas_deleted = (
        await session.execute(delete(PersonaObjectORM).where(PersonaObjectORM.owner_id == owner_id))
    ).rowcount
    receipt.magic_link_tokens_deleted = (
        await session.execute(delete(MagicLinkTokenORM).where(MagicLinkTokenORM.owner_id == owner_id))
    ).rowcount
    receipt.recognition_trials_deleted = (
        await session.execute(delete(RecognitionTrialORM).where(RecognitionTrialORM.owner_id == owner_id))
    ).rowcount

    # --- Someone else's data that merely references this agent: anonymise. ---
    if agent_ids:
        # [TUNE] full-table scan: `targets`/`witnesses` are plain JSON, not
        # JSONB, so there's no indexed containment query available here the
        # way `memory_records.subjects` (a real Postgres ARRAY with a GIN
        # index) gets one below. Acceptable at closed-alpha volume;
        # revisit (JSONB, or a join table) if this ever shows up as slow.
        other_events = (
            await session.execute(select(EventRecordORM).where(EventRecordORM.actor_id.notin_(agent_ids)))
        ).scalars().all()
        for row in other_events:
            new_targets = [t for t in row.targets if t not in agent_id_strs]
            new_witnesses = [w for w in row.witnesses if w not in agent_id_strs]
            if new_targets != row.targets or new_witnesses != row.witnesses:
                row.targets = new_targets
                row.witnesses = new_witnesses
                receipt.other_events_anonymised += 1

        other_memories = (
            await session.execute(select(MemoryRecordORM).where(MemoryRecordORM.agent_id.notin_(agent_ids)))
        ).scalars().all()
        for mem in other_memories:
            new_subjects = [s for s in mem.subjects if s not in agent_ids]
            if len(new_subjects) != len(mem.subjects):
                mem.subjects = new_subjects
                receipt.other_memories_anonymised += 1

    await session.execute(delete(OwnerORM).where(OwnerORM.id == owner_id))
    await session.flush()
    return receipt
