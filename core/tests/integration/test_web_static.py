"""M6 T6.6: the static frontend is served from the same app as the API,
and doesn't shadow any API route registered before it (otherworld.api.main
mounts StaticFiles at "/" last, specifically so this holds)."""

from __future__ import annotations

import httpx

from otherworld.api.main import app
from otherworld.db import get_session


async def test_frontend_pages_are_served_from_the_same_app():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for page in ("index.html", "verify.html", "onboarding.html", "consent.html",
                     "capture-a.html", "capture-b.html", "dashboard.html"):
            response = await client.get(f"/{page}")
            assert response.status_code == 200, page
            assert "text/html" in response.headers["content-type"]


async def test_api_routes_are_not_shadowed_by_the_static_mount(db_session):
    async def _override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/auth/request-link", json={"email": "shadow@example.com"})
            assert response.status_code == 202  # not a 404 from the static mount swallowing the path
    finally:
        app.dependency_overrides.clear()
