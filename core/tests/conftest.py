from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from otherworld.config import settings
from otherworld.db import Base
from otherworld.models import agent, events, memory, output, owner, persona, relationship, world  # noqa: F401


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """A fresh engine per test, bound to that test's event loop, against the
    dedicated test database (never `otherworld.config.settings.database_url`
    — this fixture creates and drops the full schema every test, which would
    periodically wipe the dev database and anything the CLI put there).

    `otherworld.db.engine` is also unsuitable for a second reason: it is a
    module-level singleton meant for the app's single long-lived loop.
    pytest-asyncio gives each test its own loop, so reusing that singleton
    here would leak asyncpg connections across loops. Tests get their own
    throwaway engine instead.
    """
    engine = create_async_engine(settings.test_database_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
