"""M6 T6.3 (real consent flow) and T6.6 (capture UI backend): the HTTP
surface a non-technical person's browser drives, in place of `cli.capture`'s
blocking `input()` prompts."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx

from otherworld.api.deps import get_current_owner
from otherworld.api.main import app
from otherworld.db import get_session
from otherworld.models.owner import Owner, OwnerORM, owner_from_orm, owner_to_orm
from otherworld.owner.service import ConsentRequiredError, require_consent


def _owner(handle: str) -> Owner:
    now = datetime.now(UTC)
    return Owner(
        id=uuid.uuid4(), handle=handle, email=f"{handle}@example.com", consent=None,
        created_at=now, last_active_at=now,
    )


async def _client(db_session, owner: Owner) -> httpx.AsyncClient:
    async def _override_get_session():
        yield db_session

    async def _override_get_current_owner():
        # Re-fetches by id rather than closing over `owner`, so a test that
        # mutates the owner mid-flow (e.g. sets consent) sees that change on
        # its next request — matching the real dependency, which always
        # reads fresh from the session cookie's owner_id.
        row = await db_session.get(OwnerORM, owner.id)
        return owner_from_orm(row)

    app.dependency_overrides[get_session] = _override_get_session
    app.dependency_overrides[get_current_owner] = _override_get_current_owner
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_method_a_items_lists_all_thirty_items_and_boundary_options(db_session):
    owner = _owner("itemsA")
    db_session.add(owner_to_orm(owner))
    await db_session.commit()
    client = await _client(db_session, owner)
    try:
        response = await client.get("/api/v1/persona/method-a/items")
        assert response.status_code == 200
        body = response.json()
        assert len(body["choice_items"]) == 24  # A1-A20 trait items + A21-A24 voice items
        assert len(body["free_text_items"]) == 6  # A25-A30
        assert {opt["key"] for opt in body["boundary_options"]} == {
            "no_profanity", "no_real_occupation", "no_theft", "no_advocacy",
        }  # no_romance/no_violence are always-on, never offered as a choice
    finally:
        app.dependency_overrides.clear()
        await client.aclose()


async def test_method_a_submission_builds_and_saves_a_persona(db_session):
    owner = _owner("submitA")
    db_session.add(owner_to_orm(owner))
    await db_session.commit()
    client = await _client(db_session, owner)
    try:
        answers = {f"A{i}": "a" for i in range(1, 25)}
        free_text = {
            "A25": "We talked it out.", "A26": "Kind and funny.", "A27": "honestly",
            "A28": "Wake, work, walk.", "A29": "Never betray a friend.", "A30": "That I care a lot.",
        }
        response = await client.post(
            "/api/v1/persona/method-a",
            json={"answers": answers, "free_text": free_text, "enabled_boundaries": ["no_theft"]},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["version"] == 1
        assert body["source_methods"] == ["A"]
        descriptions = {b["description"] for b in body["boundaries"]}
        assert "Never betray a friend." in descriptions  # A29 free text -> boundary
        assert any("theft" in d for d in descriptions)  # opted-in toggle applied

        get_response = await client.get("/api/v1/persona/me")
        assert get_response.status_code == 200
        assert get_response.json()["id"] == body["id"]
    finally:
        app.dependency_overrides.clear()
        await client.aclose()


async def test_method_b_prompts_lists_every_interview_prompt(db_session):
    owner = _owner("promptsB")
    db_session.add(owner_to_orm(owner))
    await db_session.commit()
    client = await _client(db_session, owner)
    try:
        response = await client.get("/api/v1/persona/method-b/prompts")
        assert response.status_code == 200
        body = response.json()
        assert len(body["prompts"]) == 12  # 10 trait prompts + boundary + voice
    finally:
        app.dependency_overrides.clear()
        await client.aclose()


async def test_method_b_submission_builds_and_saves_a_persona(db_session):
    owner = _owner("submitB")
    db_session.add(owner_to_orm(owner))
    await db_session.commit()
    client = await _client(db_session, owner)
    try:
        answers = {
            "conflict": "I confronted them about it directly the same day.",
            "criticism": "I told them the truth, straightforward and honest.",
            "boundary": "Never anything violent.",
            "voice": "I say 'for real' a lot, dry sense of humour.",
        }
        response = await client.post(
            "/api/v1/persona/method-b", json={"answers": answers, "enabled_boundaries": []}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["source_methods"] == ["B"]
        assert body["values"]["conflict_directness"] > 0.5  # confronted -> above neutral
        assert any("Never anything violent." == b["description"] for b in body["boundaries"])
    finally:
        app.dependency_overrides.clear()
        await client.aclose()


async def test_consent_endpoint_completes_the_gate_and_unblocks_require_consent(db_session):
    owner = _owner("consentflow")
    db_session.add(owner_to_orm(owner))
    await db_session.commit()
    client = await _client(db_session, owner)
    try:
        response = await client.put(
            "/api/v1/owners/me/consent",
            json={
                "identity_mode": "pseudonymous", "visibility_scope": "private",
                "third_party_consent_intent": False, "liability_acknowledged": True,
            },
        )
        assert response.status_code == 200
        assert response.json()["consent_complete"] is True

        me = await client.get("/api/v1/owners/me")
        assert me.json()["consent_complete"] is True
    finally:
        app.dependency_overrides.clear()
        await client.aclose()


async def test_declining_liability_acknowledgement_does_not_complete_the_gate(db_session):
    owner = _owner("declineconsent")
    db_session.add(owner_to_orm(owner))
    await db_session.commit()
    client = await _client(db_session, owner)
    try:
        response = await client.put(
            "/api/v1/owners/me/consent",
            json={
                "identity_mode": "pseudonymous", "visibility_scope": "private",
                "third_party_consent_intent": False, "liability_acknowledged": False,
            },
        )
        assert response.status_code == 200
        assert response.json()["consent_complete"] is False

        row = await db_session.get(OwnerORM, owner.id)
        refreshed = owner_from_orm(row)
        try:
            require_consent(refreshed)
            raise AssertionError("should have raised")
        except ConsentRequiredError:
            pass
    finally:
        app.dependency_overrides.clear()
        await client.aclose()
