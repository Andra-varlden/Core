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


class RetrievalService:
    @staticmethod
    async def retrieve(
        session: AsyncSession,
        agent_id: uuid.UUID,
        query_embedding: list[float],
        current_tick: int,
        tier: int,
    ) -> list[MemoryRecord]:
        k = settings.memory.retrieval_k_tier2 if tier == 2 else settings.memory.retrieval_k_tier1
        rows = (
            await session.execute(select(MemoryRecordORM).where(MemoryRecordORM.agent_id == agent_id))
        ).scalars()
        memories = [memory_from_orm(row) for row in rows]
        return rank_memories(memories, query_embedding, current_tick, k)
