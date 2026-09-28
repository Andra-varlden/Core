"""Invitation routes. See About/plan.md M6 T6.4."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from otherworld.api.deps import get_current_owner
from otherworld.db import get_session
from otherworld.models.owner import Owner
from otherworld.models.persona import ClaimedBond
from otherworld.persona.invitations import (
    NoPendingInvitationError,
    NoPersonaError,
    accept_seeded_relationship,
    propose_seeded_relationship,
)

router = APIRouter(prefix="/api/v1/invitations", tags=["invitations"])


class ProposeBody(BaseModel):
    counterpart_owner_id: uuid.UUID
    claimed_bond: ClaimedBond


class AcceptBody(BaseModel):
    proposer_owner_id: uuid.UUID


@router.post("", status_code=status.HTTP_201_CREATED)
async def propose(
    body: ProposeBody,
    owner: Owner = Depends(get_current_owner),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    try:
        await propose_seeded_relationship(session, owner.id, body.counterpart_owner_id, body.claimed_bond)
    except NoPersonaError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    return {"status": "proposed"}


@router.post("/accept")
async def accept(
    body: AcceptBody,
    owner: Owner = Depends(get_current_owner),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    try:
        await accept_seeded_relationship(
            session, accepter_owner_id=owner.id, proposer_owner_id=body.proposer_owner_id
        )
    except (NoPersonaError, NoPendingInvitationError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    return {"status": "accepted"}
