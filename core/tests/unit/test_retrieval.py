"""T2.4 — About/plan.md M2 acceptance test: retrieval matches a hand-computed fixture.

Formula, About/spec.md §5.2:
    score = w_r * recency + w_i * importance + w_v * relevance
    recency = exp(-decay_rate * ticks_since)
Defaults (About/spec.md §20): decay_rate=0.005, w_r=0.25, w_i=0.35, w_v=0.40.
"""

import math
import uuid
from datetime import UTC, datetime

from otherworld.models.memory import MemoryKind, MemoryRecord
from otherworld.runtime.retrieval import rank_memories, score_memory

AGENT_ID = uuid.uuid4()
NOW = datetime.now(UTC)


def _memory(tick: int, importance: float, embedding: list[float]) -> MemoryRecord:
    return MemoryRecord(
        id=uuid.uuid4(), agent_id=AGENT_ID, kind=MemoryKind.EPISODIC, content="x",
        embedding=embedding, importance=importance, tick=tick, created_at=NOW,
    )


def test_score_matches_hand_computed_formula():
    query = [1.0, 0.0]
    memory = _memory(tick=50, importance=0.6, embedding=[1.0, 0.0])  # perfectly relevant
    current_tick = 100

    expected_recency = math.exp(-0.005 * 50)
    expected = 0.25 * expected_recency + 0.35 * 0.6 + 0.40 * 1.0
    assert abs(score_memory(memory, query, current_tick) - expected) < 1e-9


def test_rank_memories_orders_by_score_and_respects_k():
    query = [1.0, 0.0]
    current_tick = 100

    # A: old but important and relevant.
    a = _memory(tick=10, importance=0.9, embedding=[1.0, 0.0])
    # B: recent but unimportant and irrelevant (orthogonal embedding).
    b = _memory(tick=99, importance=0.1, embedding=[0.0, 1.0])
    # C: recent, important, relevant — should rank highest.
    c = _memory(tick=98, importance=0.9, embedding=[1.0, 0.0])

    ranked = rank_memories([a, b, c], query, current_tick, k=2)

    assert ranked == [c, a]  # c highest (recent+important+relevant); b excluded by k


def test_rank_memories_hand_computed_order():
    query = [1.0, 0.0]
    current_tick = 100

    m1 = _memory(tick=0, importance=0.5, embedding=[1.0, 0.0])
    m2 = _memory(tick=100, importance=0.5, embedding=[1.0, 0.0])

    s1 = 0.25 * math.exp(-0.005 * 100) + 0.35 * 0.5 + 0.40 * 1.0
    s2 = 0.25 * math.exp(-0.005 * 0) + 0.35 * 0.5 + 0.40 * 1.0
    assert s2 > s1  # more recent memory scores higher, all else equal

    ranked = rank_memories([m1, m2], query, current_tick, k=2)
    assert ranked == [m2, m1]
