"""About/plan.md M5: `RetrievalService.retrieve` must stay bounded-cost as
an agent's memory count grows — the bug T5.1's pilot run surfaced (fetching
every memory and scoring all of them in Python every tick, O(ticks^2)
overall) is exactly what this guards against."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from otherworld.llm.providers.mock import MockLLMProvider
from otherworld.models.memory import MemoryKind, MemoryRecord, memory_to_orm
from otherworld.runtime.retrieval import RetrievalService

NOW = datetime.now(UTC)
AGENT_ID = uuid.uuid4()


async def _seed(session, count: int, importance: float = 0.1) -> None:
    for i in range(count):
        record = MemoryRecord(
            id=uuid.uuid4(), agent_id=AGENT_ID, kind=MemoryKind.EPISODIC, content=f"filler {i}",
            embedding=await MockLLMProvider().embed(f"filler-{i}"), importance=importance, tick=i,
            subjects=[AGENT_ID], created_at=NOW,
        )
        session.add(memory_to_orm(record))
    await session.flush()


@pytest.mark.asyncio
async def test_retrieve_returns_at_most_k_even_with_a_large_memory_pool(db_session):
    await _seed(db_session, count=300)
    query_embedding = await MockLLMProvider().embed("query")

    results = await RetrievalService.retrieve(db_session, AGENT_ID, query_embedding, current_tick=300, tier=1)

    assert len(results) == 5  # retrieval_k_tier1 default


@pytest.mark.asyncio
async def test_retrieve_scales_sublinearly_with_memory_count(db_session):
    """Not a strict perf assertion (that's fragile in CI) — just confirms
    retrieval doesn't visibly balloon as the pool grows 10x, the way it did
    before candidate-pool bounding."""
    import time

    query_embedding = await MockLLMProvider().embed("query")

    await _seed(db_session, count=50)
    start = time.perf_counter()
    await RetrievalService.retrieve(db_session, AGENT_ID, query_embedding, current_tick=50, tier=1)
    small_elapsed = time.perf_counter() - start

    await _seed(db_session, count=950)  # now 1000 total
    start = time.perf_counter()
    await RetrievalService.retrieve(db_session, AGENT_ID, query_embedding, current_tick=1000, tier=1)
    large_elapsed = time.perf_counter() - start

    # A 20x memory-count increase should not produce a 20x time increase —
    # the old (buggy) linear-scan-in-Python behaviour would.
    assert large_elapsed < small_elapsed * 10
