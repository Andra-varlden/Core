"""Persisted decision traces. See About/architecture.md §17, About/plan.md
M6 T6.7 — before this, `runtime.trace.TraceLog` only ever lived in memory
for the length of one process's run and was thrown away, so there was
nothing durable to build a cost dashboard on top of.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from otherworld.db import Base
from otherworld.runtime.trace import DecisionTrace


class DecisionTraceORM(Base):
    __tablename__ = "decision_traces"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    tick: Mapped[int] = mapped_column(Integer, index=True)
    observation_summary: Mapped[str] = mapped_column(String)
    retrieved_memory_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    prompt_hash: Mapped[str] = mapped_column(String)
    tier_used: Mapped[int] = mapped_column(Integer, index=True)
    raw_completion: Mapped[str] = mapped_column(String)
    parsed_action: Mapped[str] = mapped_column(String)
    validator_result: Mapped[str] = mapped_column(String)
    latency_ms: Mapped[float] = mapped_column(Float)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    estimated_cost_usd: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


def decision_trace_to_orm(trace: DecisionTrace) -> DecisionTraceORM:
    return DecisionTraceORM(
        id=uuid.uuid4(),
        agent_id=trace.agent_id,
        tick=trace.tick,
        observation_summary=trace.observation_summary,
        retrieved_memory_ids=[str(m) for m in trace.retrieved_memory_ids],
        prompt_hash=trace.prompt_hash,
        tier_used=trace.tier_used,
        raw_completion=trace.raw_completion,
        parsed_action=trace.parsed_action,
        validator_result=trace.validator_result,
        latency_ms=trace.latency_ms,
        input_tokens=trace.input_tokens,
        output_tokens=trace.output_tokens,
        estimated_cost_usd=trace.estimated_cost_usd,
        created_at=trace.created_at,
    )
