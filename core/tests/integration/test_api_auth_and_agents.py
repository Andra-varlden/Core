"""M6 scope: end-to-end through the real ASGI app — sign in via magic link,
then hit the consent-gated agent-creation endpoint (T6.3). Uses `httpx`'s
ASGI transport in-process (no real network, no server process), running in
the *same* event loop as the test so the overridden `get_session` dependency
can safely share the test's `db_session` transaction.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx

from otherworld.api.deps import SESSION_COOKIE_NAME, get_current_owner
from otherworld.api.main import app
from otherworld.db import get_session
from otherworld.models.owner import ConsentFlags, IdentityMode, Owner, VisibilityScope, owner_to_orm
from otherworld.models.world import World, world_to_orm


async def _client(db_session) -> httpx.AsyncClient:
    async def _override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_request_link_always_202s_and_never_reveals_whether_the_email_exists(db_session):
    client = await _client(db_session)
    try:
        response = await client.post("/api/v1/auth/request-link", json={"email": "anyone@example.com"})
        assert response.status_code == 202
    finally:
        app.dependency_overrides.clear()
        await client.aclose()


async def test_verify_rejects_a_bogus_token(db_session):
    client = await _client(db_session)
    try:
        response = await client.get("/api/v1/auth/verify", params={"token": "not-a-real-token"})
        assert response.status_code == 400
    finally:
        app.dependency_overrides.clear()
        await client.aclose()


async def test_full_sign_in_flow_sets_a_working_session_cookie(db_session, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "otherworld.auth.service.send_magic_link",
        lambda email, link_url: captured.update(link_url=link_url),
    )
    client = await _client(db_session)
    try:
        await client.post("/api/v1/auth/request-link", json={"email": "flow@example.com"})
        raw_token = captured["link_url"].split("token=")[1]

        response = await client.get("/api/v1/auth/verify", params={"token": raw_token})
        assert response.status_code == 200
        assert SESSION_COOKIE_NAME in response.cookies
    finally:
        app.dependency_overrides.clear()
        await client.aclose()


async def test_create_agent_is_blocked_without_consent(db_session):
    owner = Owner(
        id=uuid.uuid4(), handle="noconsent", email="noconsent@example.com", consent=None,
        created_at=datetime.now(UTC), last_active_at=datetime.now(UTC),
    )
    db_session.add(owner_to_orm(owner))
    await db_session.flush()

    async def _override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session
    app.dependency_overrides[get_current_owner] = lambda: owner
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    try:
        response = await client.post(
            "/api/v1/agents", json={"world_id": str(uuid.uuid4()), "display_name": "Test"}
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()
        await client.aclose()


async def test_create_agent_succeeds_for_a_consented_owner_with_a_persona(db_session):
    from otherworld.models.persona import PersonaObject, TraitVector, VoiceProfile
    from otherworld.persona.service import save_persona

    owner = Owner(
        id=uuid.uuid4(), handle="consented2", email="consented2@example.com",
        consent=ConsentFlags(
            identity_mode=IdentityMode.PSEUDONYMOUS, visibility_scope=VisibilityScope.PRIVATE,
            third_party_consent_intent=False, liability_acknowledged=True,
            tos_version="v1", acknowledged_at=datetime.now(UTC),
        ),
        created_at=datetime.now(UTC), last_active_at=datetime.now(UTC),
    )
    db_session.add(owner_to_orm(owner))
    persona = PersonaObject(
        id=uuid.uuid4(), owner_id=owner.id, version=1,
        voice=VoiceProfile(verbosity=0.4, formality=0.5, humour_style="dry", profanity_baseline=0.1),
        values=TraitVector(), source_methods=["A"], created_at=datetime.now(UTC),
    )
    await save_persona(db_session, persona)

    world = World(
        id=uuid.uuid4(), name="api-test-world", width=1, height=1, current_tick=0,
        population=0, population_cap=1, status="open", created_at=datetime.now(UTC),
    )
    db_session.add(world_to_orm(world))
    await db_session.commit()

    async def _override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session
    app.dependency_overrides[get_current_owner] = lambda: owner
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    try:
        response = await client.post(
            "/api/v1/agents", json={"world_id": str(world.id), "display_name": "Test Agent"}
        )
        assert response.status_code == 201
        assert "agent_id" in response.json()
    finally:
        app.dependency_overrides.clear()
        await client.aclose()
