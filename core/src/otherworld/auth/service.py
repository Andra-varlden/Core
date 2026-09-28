"""Magic-link request/verify flow. See About/plan.md M6."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from otherworld.auth.email import send_magic_link
from otherworld.auth.tokens import MAGIC_LINK_TTL, generate_magic_link_token, hash_token
from otherworld.models.auth import MagicLinkTokenORM
from otherworld.models.owner import Owner, OwnerORM, owner_from_orm, owner_to_orm


async def _get_or_create_owner_by_email(session: AsyncSession, email: str) -> Owner:
    row = (await session.execute(select(OwnerORM).where(OwnerORM.email == email))).scalar_one_or_none()
    if row is not None:
        return owner_from_orm(row)
    now = datetime.now(UTC)
    # A real onboarding flow would let someone pick a handle; a sign-in
    # link doesn't have one to offer, so this is a starting point they can
    # change later, not the final identity — consent (still None here) is
    # what actually gates anything consequential (see owner.service.require_consent).
    handle = email.split("@")[0]
    owner = Owner(
        id=uuid.uuid4(), handle=handle, email=email, consent=None, created_at=now, last_active_at=now
    )
    session.add(owner_to_orm(owner))
    await session.flush()
    return owner


async def request_magic_link(session: AsyncSession, email: str, link_base_url: str) -> None:
    """Looks up or creates the owner by email, issues a single-use token,
    and delivers it. Returns nothing on purpose — the raw token must only
    ever exist in the delivered link, never in a value a caller could log
    or echo back in a response by accident.
    """
    owner = await _get_or_create_owner_by_email(session, email)
    raw_token = generate_magic_link_token()
    now = datetime.now(UTC)
    session.add(
        MagicLinkTokenORM(
            id=uuid.uuid4(), owner_id=owner.id, token_hash=hash_token(raw_token),
            expires_at=now + MAGIC_LINK_TTL, used_at=None, created_at=now,
        )
    )
    await session.flush()
    send_magic_link(email, f"{link_base_url}?token={raw_token}")


async def verify_magic_link(session: AsyncSession, raw_token: str) -> Owner | None:
    """Single-use: a token already marked used, or past its TTL, fails
    exactly like an unrecognised one — no distinct error message that would
    tell an attacker which case they'd hit.
    """
    row = (
        await session.execute(
            select(MagicLinkTokenORM).where(MagicLinkTokenORM.token_hash == hash_token(raw_token))
        )
    ).scalar_one_or_none()
    if row is None or row.used_at is not None or row.expires_at < datetime.now(UTC):
        return None
    row.used_at = datetime.now(UTC)
    await session.flush()
    owner_row = await session.get(OwnerORM, row.owner_id)
    return owner_from_orm(owner_row) if owner_row else None
