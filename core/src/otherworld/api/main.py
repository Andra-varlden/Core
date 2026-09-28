"""The API service. See About/spec.md §16: FastAPI, all routes under
`/api/v1`. This is the M6 skeleton — just enough to deploy and health-check;
real routes (auth, dashboard, invitations) land as their own milestones'
scope is built out, each as its own router included here.

The `web` frontend (Stage 6, plan.md's "`web` repo created") is served from
this same app via the static mount at the bottom of this file, rather than
as a separate deployed service — a static, no-build-step frontend and its
API sharing one origin means the session cookie just works, with no CORS
configuration to get right. Registered last, and only for paths the API
routers above don't already claim, per Starlette's route-then-mount
resolution order.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from otherworld.api.agents import router as agents_router
from otherworld.api.auth import router as auth_router
from otherworld.api.dashboard import router as dashboard_router
from otherworld.api.invitations import router as invitations_router
from otherworld.api.owners import router as owners_router
from otherworld.api.persona import router as persona_router
from otherworld.db import async_session_factory

app = FastAPI(title="Otherworld API")
app.include_router(auth_router)
app.include_router(agents_router)
app.include_router(invitations_router)
app.include_router(owners_router)
app.include_router(persona_router)
app.include_router(dashboard_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Railway (or any host) hits this to decide if the service is up. Also
    checks the DB connection, not just that the process is alive — a
    process that's up but can't reach Postgres is not actually healthy.
    """
    async with async_session_factory() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ok"}


def _find_web_dir() -> Path | None:
    # `Path.cwd() / "web"` is the one that's actually right once this is
    # `pip install`-ed (Docker's WORKDIR is `/app`, `web/` is copied there
    # too — see Dockerfile — but the installed package itself then lives
    # under site-packages, nowhere near the source tree). The `__file__`-
    # relative guess is kept only as a fallback for running straight out of
    # a source checkout with a different working directory.
    for candidate in (Path.cwd() / "web", Path(__file__).resolve().parents[3] / "web"):
        if candidate.is_dir():
            return candidate
    return None


_WEB_DIR = _find_web_dir()
if _WEB_DIR is not None:
    app.mount("/", StaticFiles(directory=_WEB_DIR, html=True), name="web")
