"""M6 scope: the magic-link request/verify flow (About/plan.md, spec.md §16).

No Resend account needed to test this — `resend_api_key` is unset by
default, so `auth.email.send_magic_link` logs the link instead of sending
it (see its own docstring); these tests read the token straight out of the
DB the same way that dev-mode log line would show it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from otherworld.auth.service import request_magic_link, verify_magic_link
from otherworld.models.auth import MagicLinkTokenORM
from otherworld.models.owner import ConsentFlags, IdentityMode, Owner, OwnerORM, VisibilityScope
from otherworld.owner.service import ConsentRequiredError, require_consent


async def test_request_magic_link_creates_an_owner_with_no_consent_yet(db_session):
    await request_magic_link(db_session, "new-person@example.com", "https://app.example/verify")

    row = (
        await db_session.execute(select(OwnerORM).where(OwnerORM.email == "new-person@example.com"))
    ).scalar_one()
    assert row.consent is None  # real consent flow hasn't happened yet
    assert row.handle == "new-person"


async def test_request_magic_link_reuses_an_existing_owner_by_email(db_session):
    await request_magic_link(db_session, "repeat@example.com", "https://app.example/verify")
    await request_magic_link(db_session, "repeat@example.com", "https://app.example/verify")

    rows = (
        await db_session.execute(select(OwnerORM).where(OwnerORM.email == "repeat@example.com"))
    ).scalars().all()
    assert len(rows) == 1  # not duplicated
    tokens = (
        await db_session.execute(select(MagicLinkTokenORM).where(MagicLinkTokenORM.owner_id == rows[0].id))
    ).scalars().all()
    assert len(tokens) == 2  # each request still issues its own token


async def test_verify_magic_link_round_trips_via_the_stored_hash(db_session, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "otherworld.auth.service.send_magic_link",
        lambda email, link_url: captured.update(link_url=link_url),
    )

    await request_magic_link(db_session, "verify-me@example.com", "https://app.example/verify")
    raw_token = captured["link_url"].split("token=")[1]

    owner = await verify_magic_link(db_session, raw_token)
    assert owner is not None
    assert owner.email == "verify-me@example.com"


async def test_verify_magic_link_rejects_reuse_of_an_already_used_token(db_session, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "otherworld.auth.service.send_magic_link",
        lambda email, link_url: captured.update(link_url=link_url),
    )
    await request_magic_link(db_session, "onceonly@example.com", "https://app.example/verify")
    raw_token = captured["link_url"].split("token=")[1]

    first = await verify_magic_link(db_session, raw_token)
    second = await verify_magic_link(db_session, raw_token)
    assert first is not None
    assert second is None


async def test_verify_magic_link_rejects_an_unrecognised_token(db_session):
    assert await verify_magic_link(db_session, "totally-made-up-token") is None


def test_require_consent_blocks_an_owner_with_no_consent_record():
    owner = Owner(
        id=uuid.uuid4(), handle="nobody", email="nobody@example.com", consent=None,
        created_at=datetime.now(UTC), last_active_at=datetime.now(UTC),
    )
    try:
        require_consent(owner)
        raise AssertionError("should have raised")
    except ConsentRequiredError:
        pass


def test_require_consent_allows_an_owner_with_a_completed_consent_record():
    owner = Owner(
        id=uuid.uuid4(), handle="consented", email="consented@example.com",
        consent=ConsentFlags(
            identity_mode=IdentityMode.PSEUDONYMOUS, visibility_scope=VisibilityScope.PRIVATE,
            third_party_consent_intent=False, liability_acknowledged=True,
            tos_version="v1", acknowledged_at=datetime.now(UTC),
        ),
        created_at=datetime.now(UTC), last_active_at=datetime.now(UTC),
    )
    require_consent(owner)  # must not raise
