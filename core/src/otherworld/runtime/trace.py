"""Decision tracing. See About/architecture.md §17.

Non-negotiable from M2 onward — emergent behaviour cannot be debugged after
the fact without a full trace of every Tier 1/2 decision. Persisted as
structured JSON lines for now (About/architecture.md §11's "Trace log"
storage row: "Structured JSON -> file, later ClickHouse or similar").
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel


class DecisionTrace(BaseModel):
    agent_id: uuid.UUID
    tick: int
    observation_summary: str
    retrieved_memory_ids: list[uuid.UUID]
    prompt_hash: str
    tier_used: int
    raw_completion: str
    parsed_action: str
    validator_result: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    created_at: datetime


class TraceLog:
    """In-memory collector, optionally flushed to a JSONL file."""

    def __init__(self) -> None:
        self.entries: list[DecisionTrace] = []

    def record(self, trace: DecisionTrace) -> None:
        self.entries.append(trace)

    def write_jsonl(self, path: Path) -> None:
        with path.open("a", encoding="utf-8") as f:
            for entry in self.entries:
                f.write(entry.model_dump_json() + "\n")
