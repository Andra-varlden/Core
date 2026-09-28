# M6 (About/plan.md): a single image runs as either the web/API service or
# the background worker (the continuous simulation), selected by the start
# command each Railway service is configured with — not by separate images,
# so both always ship the exact same code.
FROM python:3.12-slim AS base

# psycopg[binary] avoids needing build-essential/libpq-dev, but alembic and
# asyncpg both still need a C toolchain absent from -slim for their sdists
# on some platforms; keep the image lean by installing only what's missing.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
COPY web ./web

RUN pip install --no-cache-dir .

# Migrations run as a Railway pre-deploy step (or manually), not baked into
# the image start command — a worker and a web service deploying at the
# same time must never race to run `alembic upgrade head` twice.
ENV PYTHONUNBUFFERED=1

# No default CMD: each Railway service sets its own (see README.deploy.md) —
#   web:    uvicorn otherworld.api.main:app --host 0.0.0.0 --port $PORT
#   worker: python -m otherworld.worker
