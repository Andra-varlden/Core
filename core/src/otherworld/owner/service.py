"""Plane 1 — Owner lifecycle.

`get_or_create_owner` below is the M1-era CLI/dev helper (`cli.capture`,
`cli.run_world`, `worker.py`'s test fixtures) — it still issues a placeholder
consent record so local testing never needs a real sign-in flow. The real
path a real person goes through is `otherworld.auth.service` (magic-link
sign-in, M6): a new owner from `request_magic_link` starts with
`consent=None`, and `require_consent` below is what actually blocks
anything consequential (agent creation) until they've completed the real
consent flow — About/architecture.md §2's four-flag ConsentGate.
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


class ConsentRequiredError(Exception):
    """Raised when an action that needs the real consent gate (agent
    creation) is attempted before an owner has completed it. See
    About/plan.md T6.3: "Agent creation refused when flags incomplete."
    """


def require_consent(owner: Owner) -> None:
    """A record existing isn't enough — About/architecture.md §2's
    `liability_acknowledged` flag explicitly "Blocks agent creation if
    false," so a `False` value must refuse exactly like a missing record,
    not just be stored inertly.
    """
    if owner.consent is None or not owner.consent.liability_acknowledged:
        raise ConsentRequiredError(f"owner {owner.id} has not completed the consent flow")


# About/architecture.md §2: `liability_acknowledged` carries "a timestamp and
# ToS version" alongside the bool. Both are set here, server-side, rather
# than accepted from the client — an owner agreeing today to version X of
# the ToS is a legal record; letting a client pick its own version or
# backdate the timestamp would make that record worthless.
CURRENT_TOS_VERSION = "v1"


async def set_consent(
    session: AsyncSession,
    owner: Owner,
    identity_mode: IdentityMode,
    visibility_scope: VisibilityScope,
    third_party_consent_intent: bool,
    liability_acknowledged: bool,
) -> Owner:
    """The real consent flow (About/plan.md M6, T6.3) a signed-in owner
    completes once before they can spawn an agent — distinct from
    `get_or_create_owner`'s dev-only placeholder record.
    """
    updated = owner.model_copy(
        update={
            "consent": ConsentFlags(
                identity_mode=identity_mode,
                visibility_scope=visibility_scope,
                third_party_consent_intent=third_party_consent_intent,
                liability_acknowledged=liability_acknowledged,
                tos_version=CURRENT_TOS_VERSION,
                acknowledged_at=datetime.now(UTC),
            )
        }
    )
    row = await session.get(OwnerORM, owner.id)
    row.consent = updated.consent.model_dump(mode="json")
    await session.flush()
    return updated
