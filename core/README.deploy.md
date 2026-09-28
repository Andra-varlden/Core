# Deploying `core` (M6)

One Docker image, two Railway services running the same code with different
start commands. No default `CMD` in the Dockerfile — each service sets its
own, so a misconfigured service fails loudly on boot rather than silently
running the wrong role.

## Services

| Service | Start command | Role |
|---|---|---|
| `web` | `uvicorn otherworld.api.main:app --host 0.0.0.0 --port $PORT` | API, plus the `web/` frontend served from the same app (see below) |
| `worker` | `python -m otherworld.worker` | The unattended simulation — real-time paced, runs forever |

The frontend (Stage 6's capture UI and dashboard, plain HTML/CSS/JS, no
build step) is *not* a separate Railway service — `api.main` mounts
`core/web/` as static files on the same app that serves `/api/v1/*`, so the
whole thing is same-origin: no CORS configuration, and the session cookie
just works. `APP_BASE_URL` below is this `web` service's own public URL.

Both need the same environment variables (Railway: attach the same Postgres
and Redis plugins to both services, or share one variable group):

- `DATABASE_URL` — `postgresql+asyncpg://...` (async driver, for the app)
- `DATABASE_URL_SYNC` — `postgresql+psycopg://...` (sync driver, for Alembic)
- `REDIS_URL`
- `GROQ_API_KEY`
- `SESSION_SECRET` — a real random secret; the code default is dev-only and
  insecure (anyone who knows it can forge any owner's session)
- `APP_BASE_URL` — where the `web` frontend is reachable, used to build the
  magic-link verify URL an email points at
- `DEBUG` — set to `false`; this makes the session cookie `Secure`, without
  which the browser silently drops it over plain http-only dev defaults
- `RESEND_API_KEY` — optional; without it, magic links are logged instead of
  emailed (fine for internal testing, not for real users)

## Migrations

Run `alembic upgrade head` as a Railway **pre-deploy** step (or manually,
once), never inside either service's own start command — `web` and `worker`
can redeploy independently, and two services racing to run migrations at
the same moment is exactly the kind of thing that corrupts a schema.

## Status

All six M6 stages are built and tested: deploy skeleton, auth/consent,
mutual invitations, deletion cascade, cost trace persistence, and the `web`
capture UI + dashboard. `core/web/` pages: `index.html` (request a sign-in
link) → `verify.html` (consumes the emailed link, sets the session cookie) →
`onboarding.html` (hub: consent, then persona capture, tracks what's left) →
`consent.html`, `capture-a.html` (Method A, ~8 min), `capture-b.html`
(Method B, 15-20 min, the one T6.6 names) → `dashboard.html` (cost per
agent-day and tier shares, from `otherworld.output.cost`).

## The one thing only a human can do here

Everything above is ready to deploy, but actually deploying requires a
Railway account — creating one, connecting this repo, and setting the four
env vars above per service isn't something that can be done without you.
Once that's set up, T6.1 (72-hour unattended run) and T6.2 (kill mid-tick,
confirm it resumes) can be verified for real against the live deployment.
