"""Shared FastAPI dependencies. See About/plan.md M6."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from otherworld.auth.tokens import verify_session_token
from otherworld.config import settings
from otherworld.db import get_session
from otherworld.models.owner import Owner, OwnerORM, owner_from_orm

SESSION_COOKIE_NAME = "otherworld_session"


async def get_current_owner(
    request: Request, session: AsyncSession = Depends(get_session)
) -> Owner:
    """401s on anything wrong with the session — missing cookie, forged
    signature, expired token, or an owner_id that no longer exists (e.g.
    post-deletion, About/plan.md T6.5) — never a 500. An unauthenticated
    request and a malformed one look identical to the caller by design.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not signed in")

    owner_id = verify_session_token(token, settings.session_secret)
    if owner_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session expired or invalid")

    row = await session.get(OwnerORM, owner_id)
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session expired or invalid")
    return owner_from_orm(row)
