"""Plane 1 — Owner lifecycle. Minimal for M1: enough to attach a persona to
a real person. The full consent gate (About/architecture.md §2) — real
auth, the four-flag ConsentGate blocking agent creation — is M6 scope
(About/plan.md). Personas captured now use a placeholder consent record so
capture can start before that plane exists; nothing here should be read as
the real consent flow.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from otherworld.models.owner import (
    ConsentFlags,
    IdentityMode,
    Owner,
    OwnerORM,
    VisibilityScope,
    owner_from_orm,
    owner_to_orm,
)


def _placeholder_consent() -> ConsentFlags:
    now = datetime.now(UTC)
    return ConsentFlags(
        identity_mode=IdentityMode.PSEUDONYMOUS,
        visibility_scope=VisibilityScope.PRIVATE,
        third_party_consent_intent=False,
        liability_acknowledged=True,
        tos_version="M1-dev-placeholder",
        acknowledged_at=now,
    )


async def get_or_create_owner(session: AsyncSession, handle: str, email: str) -> Owner:
    row = (await session.execute(select(OwnerORM).where(OwnerORM.handle == handle))).scalar_one_or_none()
    if row is not None:
        return owner_from_orm(row)

    now = datetime.now(UTC)
    owner = Owner(
        id=uuid.uuid4(),
        handle=handle,
        email=email,
        consent=_placeholder_consent(),
        created_at=now,
        last_active_at=now,
        status="active",
    )
    session.add(owner_to_orm(owner))
    await session.flush()
    return owner
