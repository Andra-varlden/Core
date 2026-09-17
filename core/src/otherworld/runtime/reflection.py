"""Reflection: belief formation from episodic memory. See About/spec.md §5.3.

Due when either `reflection.interval_ticks` have passed since the agent's
last reflection, or the sum of importance across episodic memories written
since then exceeds `reflection.importance_sum_trigger` (About/config.py's
`ReflectionConfig`).

Modelled as a scheduler-driven side effect rather than an LLM-chosen
`ActionRegistry` action: the trigger condition is purely mechanical (elapsed
ticks or an importance sum crossing a threshold), so there's nothing for the
model to meaningfully decide by choosing to call `reflect` versus not — and
routing it through the decision loop would make T5.2's determinism test
depend on a real model reliably picking `reflect` exactly when due, which it
has no way to know without already being told. `About/architecture.md`
already treats the sleep window the same way (Tier 0, scheduler-driven,
never touching `DecisionEngine`); this follows that precedent. Reflection
runs alongside an agent's normal tick action, not instead of it — it's a
memory-maintenance pass, not a spatial/social act with its own event record.

Persona re-grounding is mandatory (About/spec.md §5.3, guards against
personality collapse, failure mode F2): the prompt always carries
`bundle.identity_prompt`, never just the memory list.

Each source memory's `subjects` (who it involved) are surfaced alongside
its content, even though the content text itself is anonymised
("Another agent did 'betray' to me" — About/runtime/resolver.py never
names names in what it writes). That's what lets a belief carry a real
`about_agent_id` — required for `social/gossip.py` to find "beliefs about a
third party" at all, not just self-reflection.
"""

from __future__ import annotations

import json
import random
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from otherworld.config import settings
from otherworld.llm.protocol import LLMProvider, Prompt
from otherworld.models.memory import MemoryKind, MemoryRecord, MemoryRecordORM, memory_to_orm
from otherworld.persona.compiler import AgentBundle
from otherworld.runtime.determinism import seeded_uuid
from otherworld.runtime.json_util import extract_json_object

_RESPONSE_INSTRUCTION = (
    "Respond with JSON only, no other text, no markdown code fences: "
    '{"beliefs": [{"text": "<belief, first-person>", '
    '"about_agent_id": "<id from [subjects: ...] above, or null for yourself/the world>", '
    '"valence": <-1.0 to 1.0, how negative or positive this belief is>}]}. '
    "Give 1 to 3 beliefs, grounded only in the memories listed above."
)


@dataclass(frozen=True)
class _ParsedBelief:
    content: str
    valence: float
    about_agent_id: uuid.UUID | None


def _parse_beliefs(text: str) -> list[_ParsedBelief]:
    try:
        data = json.loads(extract_json_object(text))
    except (json.JSONDecodeError, TypeError):
        return []
    beliefs = data.get("beliefs") if isinstance(data, dict) else None
    if not isinstance(beliefs, list):
        return []

    parsed: list[_ParsedBelief] = []
    for entry in beliefs[:3]:
        if not isinstance(entry, dict):
            continue
        content = str(entry.get("text", "")).strip()
        if not content:
            continue
        try:
            valence = max(-1.0, min(1.0, float(entry.get("valence", 0.0))))
        except (TypeError, ValueError):
            valence = 0.0
        about_agent_id: uuid.UUID | None
        try:
            about_agent_id = uuid.UUID(str(entry.get("about_agent_id")))
        except (TypeError, ValueError):
            about_agent_id = None
        parsed.append(_ParsedBelief(content=content, valence=valence, about_agent_id=about_agent_id))
    return parsed


async def _importance_sum_since(session: AsyncSession, agent_id: uuid.UUID, since_tick: int) -> float:
    total = (
        await session.execute(
            select(func.sum(MemoryRecordORM.importance)).where(
                MemoryRecordORM.agent_id == agent_id,
                MemoryRecordORM.kind == MemoryKind.EPISODIC.value,
                MemoryRecordORM.tick > since_tick,
            )
        )
    ).scalar_one_or_none()
    return float(total) if total is not None else 0.0


async def is_reflection_due(
    session: AsyncSession, agent_id: uuid.UUID, last_reflection_tick: int, tick: int
) -> bool:
    if tick - last_reflection_tick >= settings.reflection.interval_ticks:
        return True
    importance_sum = await _importance_sum_since(session, agent_id, last_reflection_tick)
    return importance_sum > settings.reflection.importance_sum_trigger


def _memory_line(row: MemoryRecordORM, agent_id: uuid.UUID) -> str:
    others = [str(s) for s in row.subjects if s != agent_id]
    prefix = f"[subjects: {', '.join(others)}] " if others else ""
    return f"- {prefix}{row.content}"


class ReflectionService:
    @staticmethod
    async def reflect(
        session: AsyncSession,
        provider: LLMProvider,
        rng: random.Random,
        agent_id: uuid.UUID,
        bundle: AgentBundle,
        last_reflection_tick: int,
        tick: int,
        created_at: datetime,
    ) -> list[MemoryRecord]:
        """Synthesises the top `reflection.input_memory_count` episodic
        memories since the last reflection into 1-3 belief records. Returns
        the newly written beliefs — empty if there was nothing to reflect
        on, or the model's completion didn't parse into any usable belief.
        Reflection never raises on a bad completion; an agent that has
        nothing coherent to say about itself this round just doesn't.
        """
        rows = (
            await session.execute(
                select(MemoryRecordORM)
                .where(
                    MemoryRecordORM.agent_id == agent_id,
                    MemoryRecordORM.kind == MemoryKind.EPISODIC.value,
                    MemoryRecordORM.tick > last_reflection_tick,
                )
                .order_by(MemoryRecordORM.importance.desc())
                .limit(settings.reflection.input_memory_count)
            )
        ).scalars().all()
        if not rows:
            return []

        memory_lines = "\n".join(_memory_line(row, agent_id) for row in rows)
        user_content = f"Memories since your last reflection:\n{memory_lines}\n\n{_RESPONSE_INSTRUCTION}"
        prompt = Prompt(system=bundle.identity_prompt, messages=[{"role": "user", "content": user_content}])
        completion = await provider.tier2(prompt)
        beliefs_parsed = _parse_beliefs(completion.text)
        if not beliefs_parsed:
            return []

        valid_subjects = {s for row in rows for s in row.subjects}
        source_ids = [row.id for row in rows]
        mean_importance = sum(row.importance for row in rows) / len(rows)

        written: list[MemoryRecord] = []
        for entry in beliefs_parsed:
            subject = entry.about_agent_id if entry.about_agent_id in valid_subjects else agent_id

            embedding = await provider.embed(entry.content)
            belief = MemoryRecord(
                id=seeded_uuid(rng),
                agent_id=agent_id,
                kind=MemoryKind.BELIEF,
                content=entry.content,
                embedding=embedding,
                importance=mean_importance,
                tick=tick,
                subjects=[subject],
                derived_from=source_ids,
                hop_count=0,
                valence=entry.valence,
                created_at=created_at,
            )
            session.add(memory_to_orm(belief))
            written.append(belief)

        await session.flush()
        return written
