"""Owner routes. See About/plan.md M6 T6.3, T6.5."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from otherworld.api.deps import SESSION_COOKIE_NAME, get_current_owner
from otherworld.db import get_session
from otherworld.models.owner import IdentityMode, Owner, VisibilityScope
from otherworld.owner.deletion import delete_owner
from otherworld.owner.service import set_consent

router = APIRouter(prefix="/api/v1/owners", tags=["owners"])


class SetConsentBody(BaseModel):
    identity_mode: IdentityMode
    visibility_scope: VisibilityScope
    third_party_consent_intent: bool
    liability_acknowledged: bool


@router.get("/me")
async def get_me(owner: Owner = Depends(get_current_owner)) -> dict[str, object]:
    return {
        "id": str(owner.id),
        "handle": owner.handle,
        "email": owner.email,
        "consent_complete": owner.consent is not None and owner.consent.liability_acknowledged,
    }


@router.put("/me/consent")
async def put_consent(
    body: SetConsentBody,
    owner: Owner = Depends(get_current_owner),
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    updated = await set_consent(
        session, owner,
        identity_mode=body.identity_mode,
        visibility_scope=body.visibility_scope,
        third_party_consent_intent=body.third_party_consent_intent,
        liability_acknowledged=body.liability_acknowledged,
    )
    await session.commit()
    assert updated.consent is not None
    return {"consent_complete": updated.consent.liability_acknowledged}


@router.delete("/me")
async def delete_me(
    response: Response,
    owner: Owner = Depends(get_current_owner),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    receipt = await delete_owner(session, owner.id)
    await session.commit()
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"receipt": {k: (str(v) if k in ("owner_id", "deleted_at") else v) for k, v in asdict(receipt).items()}}
