"""Mutual social invitation flow. See About/plan.md M6 T6.4 and ADR-007
(About/context.md §"ADR-007"): a claimed real-world relationship only takes
effect once BOTH owners have explicitly accepted it — no unilateral
seeding, no naming a non-user, no importing a contact list.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from otherworld.models.persona import ClaimedBond, PersonaObject, SeededRelationship
from otherworld.persona.service import edit_persona, get_latest_persona


class NoPersonaError(Exception):
    """Either party hasn't captured a persona yet — nothing exists to
    attach a seeded relationship claim to."""


class NoPendingInvitationError(Exception):
    """Accepting confirms a claim someone else already made; it is never a
    way to create one — that would be exactly the unilateral seeding
    ADR-007 exists to prevent.
    """


async def propose_seeded_relationship(
    session: AsyncSession,
    proposer_owner_id: uuid.UUID,
    counterpart_owner_id: uuid.UUID,
    claimed_bond: ClaimedBond,
) -> PersonaObject:
    """Only ever writes to the proposer's own persona — About/spec.md's
    "no unilateral seeding" holds by construction: nothing about the
    counterpart's data changes until they separately call `accept_seeded_relationship`.
    """
    persona = await get_latest_persona(session, proposer_owner_id)
    if persona is None:
        raise NoPersonaError(f"owner {proposer_owner_id} has no captured persona yet")

    # Replaces any existing (still-pending) claim to the same counterpart
    # rather than accumulating duplicates — re-inviting (e.g. after
    # changing the claimed bond type) updates the one claim, it doesn't
    # pile up a second.
    remaining = [s for s in persona.social if s.counterpart_owner_id != counterpart_owner_id]
    proposal = SeededRelationship(
        counterpart_owner_id=counterpart_owner_id, claimed_bond=claimed_bond,
        mutual_accepted=False, accepted_at=None,
    )
    return await edit_persona(session, persona, social=[*remaining, proposal])


async def accept_seeded_relationship(
    session: AsyncSession, accepter_owner_id: uuid.UUID, proposer_owner_id: uuid.UUID
) -> tuple[PersonaObject, PersonaObject]:
    """Both personas end up with a symmetric, mutually-accepted record —
    the proposer's pending claim gets confirmed, and the accepter gets
    their own mirrored entry — so whichever owner's persona a later reader
    looks at, they see the same accepted relationship.
    """
    proposer_persona = await get_latest_persona(session, proposer_owner_id)
    accepter_persona = await get_latest_persona(session, accepter_owner_id)
    if proposer_persona is None or accepter_persona is None:
        raise NoPersonaError("both owners must have a captured persona")

    pending = next(
        (
            s for s in proposer_persona.social
            if s.counterpart_owner_id == accepter_owner_id and not s.mutual_accepted
        ),
        None,
    )
    if pending is None:
        raise NoPendingInvitationError(
            f"no pending invitation from {proposer_owner_id} to {accepter_owner_id}"
        )

    now = datetime.now(UTC)
    confirmed = pending.model_copy(update={"mutual_accepted": True, "accepted_at": now})
    proposer_updated = await edit_persona(
        session, proposer_persona,
        social=[confirmed if s is pending else s for s in proposer_persona.social],
    )

    mirror = SeededRelationship(
        counterpart_owner_id=proposer_owner_id, claimed_bond=pending.claimed_bond,
        mutual_accepted=True, accepted_at=now,
    )
    remaining = [s for s in accepter_persona.social if s.counterpart_owner_id != proposer_owner_id]
    accepter_updated = await edit_persona(session, accepter_persona, social=[*remaining, mirror])

    return proposer_updated, accepter_updated
