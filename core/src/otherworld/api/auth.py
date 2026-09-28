"""Auth routes. See About/plan.md M6, spec.md §16 (routes under `/api/v1`)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from otherworld.api.deps import SESSION_COOKIE_NAME
from otherworld.auth.service import request_magic_link, verify_magic_link
from otherworld.auth.tokens import SESSION_TTL, create_session_token
from otherworld.config import settings
from otherworld.db import get_session

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class RequestLinkBody(BaseModel):
    email: EmailStr


@router.post("/request-link", status_code=status.HTTP_202_ACCEPTED)
async def request_link(body: RequestLinkBody, session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    """Always 202s, whether or not the email is already registered — the
    response can't reveal which, or it becomes a way to enumerate real
    people's email addresses.
    """
    await request_magic_link(session, body.email, link_base_url=f"{settings.app_base_url}/verify.html")
    await session.commit()
    return {"status": "sent"}


@router.get("/verify")
async def verify(
    token: str, response: Response, session: AsyncSession = Depends(get_session)
) -> dict[str, str]:
    owner = await verify_magic_link(session, token)
    if owner is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "this link is invalid or has expired")
    await session.commit()

    session_token = create_session_token(owner.id, settings.session_secret)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_token,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,
        secure=not settings.debug,
        samesite="lax",
    )
    return {"status": "signed_in"}
