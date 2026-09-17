"""Retrieval. See About/spec.md §5.2.

    score = w_r * recency + w_i * importance + w_v * relevance
    recency = exp(-decay_rate * ticks_since)

`rank_memories` is a pure function of its inputs (no DB, no clock) so it can
be checked against a hand-computed fixture (About/plan.md T2.4) without a
database. `RetrievalService` is the thin, DB-aware wrapper used at runtime.
"""

from __future__ import annotations

import math
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from otherworld.config import settings
from otherworld.models.memory import MemoryRecord, MemoryRecordORM, memory_from_orm


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def score_memory(memory: MemoryRecord, query_embedding: list[float], current_tick: int) -> float:
    m = settings.memory
    ticks_since = max(0, current_tick - memory.tick)
    recency = math.exp(-m.recency_decay_rate * ticks_since)
    relevance = _cosine_similarity(query_embedding, memory.embedding)
    return (
        m.weight_recency * recency
        + m.weight_importance * memory.importance
        + m.weight_relevance * relevance
    )


def rank_memories(
    memories: list[MemoryRecord], query_embedding: list[float], current_tick: int, k: int
) -> list[MemoryRecord]:
    scored = [(score_memory(m, query_embedding, current_tick), m) for m in memories]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [m for _, m in scored[:k]]


def _score_components(importance: float, ticks_since: int, relevance: float) -> float:
    """Same formula as `score_memory`, taking already-computed components
    instead of a `MemoryRecord` + raw embeddings — used when relevance came
    back pre-computed from the database (see `RetrievalService.retrieve`),
    so scoring the candidate pool doesn't need the embeddings in Python at
    all."""
    m = settings.memory
    recency = math.exp(-m.recency_decay_rate * max(0, ticks_since))
    return m.weight_recency * recency + m.weight_importance * importance + m.weight_relevance * relevance


class RetrievalService:
    @staticmethod
    async def retrieve(
        session: AsyncSession,
        agent_id: uuid.UUID,
        query_embedding: list[float],
        current_tick: int,
        tier: int,
    ) -> list[MemoryRecord]:
        """Fetches a bounded candidate pool — the most recent memories plus
        the most important ones, each a plain index-backed query, with
        cosine relevance computed by pgvector in SQL rather than by
        deserialising every candidate's 1536-float embedding into Python
        and looping over it — then re-scores that pool against the full
        recency+importance+relevance formula (About/spec.md §5.2) to get
        the true top-k, and only *then* fetches the handful of full
        records (with embeddings) the caller actually gets back.

        Both the unbounded scan and the Python-side cosine loop were real,
        measured bugs (profiled during About/plan.md T5.1's pilot run):
        fetching every memory an agent has and scoring all of them in
        Python is O(agent's total memory count) *per call*, so total cost
        grows quadratically with tick count as memory accumulates; and even
        after bounding the candidate pool, doing the 1536-dimension cosine
        similarity in a pure-Python loop for every candidate, every
        decision, every tick, dominated the profile (500+ seconds of a
        ~1150s, 150-tick/20-agent run) — pgvector exists precisely so this
        computation happens in the database instead.

        Ordering by pgvector distance with a LIMIT alone doesn't fix the
        scan cost (without an ANN index, Postgres still computes the
        distance for every matching row before it can sort and limit) —
        the two plain-index queries below (`(agent_id, tick)` and
        `(agent_id, importance)`, added alongside this fix) bound *that*
        part; asking pgvector for the distance only on those already-
        bounded rows is what removes the Python-side cost.
        """
        k = settings.memory.retrieval_k_tier2 if tier == 2 else settings.memory.retrieval_k_tier1
        pool_size = max(k * 5, 50)  # [TUNE] revisit once there's real traffic to tune against
        distance = MemoryRecordORM.embedding.cosine_distance(query_embedding).label("distance")

        recent = await session.execute(
            select(MemoryRecordORM.id, MemoryRecordORM.importance, MemoryRecordORM.tick, distance)
            .where(MemoryRecordORM.agent_id == agent_id)
            .order_by(MemoryRecordORM.tick.desc())
            .limit(pool_size)
        )
        important = await session.execute(
            select(MemoryRecordORM.id, MemoryRecordORM.importance, MemoryRecordORM.tick, distance)
            .where(MemoryRecordORM.agent_id == agent_id)
            .order_by(MemoryRecordORM.importance.desc())
            .limit(pool_size)
        )

        candidates = {row.id: row for row in (*recent, *important)}
        if not candidates:
            return []

        scored = [
            (
                _score_components(row.importance, current_tick - row.tick, 1.0 - row.distance),
                memory_id,
            )
            for memory_id, row in candidates.items()
        ]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        top_ids = [memory_id for _, memory_id in scored[:k]]

        rows = (
            await session.execute(select(MemoryRecordORM).where(MemoryRecordORM.id.in_(top_ids)))
        ).scalars()
        by_id = {row.id: memory_from_orm(row) for row in rows}
        return [by_id[memory_id] for memory_id in top_ids if memory_id in by_id]
