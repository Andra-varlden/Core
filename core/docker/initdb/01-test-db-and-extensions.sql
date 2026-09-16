-- Runs once, on first container creation with a fresh volume.
-- Tests must never run against the dev database: About/plan.md's test
-- suite creates and drops the full schema per test (tests/conftest.py),
-- which would otherwise wipe out whatever `alembic upgrade head` and the
-- CLI (otherworld.cli.capture) have built up in the dev database.
CREATE DATABASE otherworld_test;

CREATE EXTENSION IF NOT EXISTS vector;
\connect otherworld_test
CREATE EXTENSION IF NOT EXISTS vector;
