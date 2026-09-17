"""Gossip propagation and pile-on damping. See About/spec.md §8.1, §8.2.

Wired into the tick loop via the `confide` action (About/runtime/resolver.py):
an agent shares one of its own beliefs about a visible third party, and
`GossipService.propagate` produces the listener's own, distorted, hop-
incremented version of it. `hop_count` and `valence` (About/models/memory.py)
travel with the belief itself rather than being passed around separately —
a retelling is *of* a specific prior belief, so its lineage should be
derivable from that belief alone, not from bookkeeping the caller has to
get right every time.
"""

from __future__ import annotations

import json
import random
import uuid
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from otherworld.config import settings
from otherworld.llm.protocol import LLMProvider, Prompt
from otherworld.models.memory import MemoryKind, MemoryRecord, MemoryRecordORM, memory_from_orm, memory_to_orm
from otherworld.runtime.determinism import seeded_uuid
from otherworld.runtime.json_util import extract_json_object
from otherworld.social.engine import trust_normalised

_RESPONSE_INSTRUCTION = (
    "Respond with JSON only, no other text, no markdown code fences: "
    '{"belief": "<the belief, retold in your own words>"}.'
)


def eligible_to_propagate(importance: float) -> bool:
    return importance >= settings.gossip.min_importance_to_propagate


def within_hop_limit(hop_count: int) -> bool:
    return hop_count < settings.gossip.max_hops


def inherited_belief_strength(source_strength: float, trust_ab: float) -> float:
    """About/spec.md §8.1: `source_strength × trust(A,B) × propagation_decay`."""
    return source_strength * trust_normalised(trust_ab) * settings.gossip.propagation_decay


def weighted_belief_strength(direct_experience_strength: float | None, inherited_strength: float) -> float:
    """An agent with a direct edge to the belief's subject weights its own
    experience at `direct_experience_weight`x any inherited belief — About/
    spec.md §8.1's last rule. Returns whichever the listener should actually
    hold, not both. Not yet invoked in the live path: it's a belief-
    *consolidation* concern (which of several beliefs about the same
    subject wins), and there's no belief-merging step in this codebase yet
    — each retelling is just written as its own record.
    """
    if direct_experience_strength is None:
        return inherited_strength
    return direct_experience_strength * settings.gossip.direct_experience_weight


@dataclass(frozen=True)
class PileOnStatus:
    holder_count: int
    suppressed: bool
    watch_signal: bool


def check_pileon(holder_ids: Collection[uuid.UUID]) -> PileOnStatus:
    """About/spec.md §8.2. `holder_ids` are the distinct agents who hold a
    negative inherited belief about some single subject, with no direct
    experience of their own."""
    count = len(set(holder_ids))
    triggered = count > settings.gossip.pileon_agent_threshold
    return PileOnStatus(holder_count=count, suppressed=triggered, watch_signal=triggered)


async def check_pileon_for_subject(
    session: AsyncSession, subject_id: uuid.UUID, excluding_agent_id: uuid.UUID | None = None
) -> PileOnStatus:
    """Queries the distinct agents currently holding a negative (`valence <
    0`), inherited (`hop_count > 0` — gossiped, not witnessed first-hand)
    belief about `subject_id`, and evaluates About/spec.md §8.2 against them.
    `excluding_agent_id`: the about-to-receive listener, so a propagation
    that would create the (N+1)th holder is checked *before* it's written,
    not after.
    """
    rows = (
        await session.execute(
            select(MemoryRecordORM.agent_id).where(
                MemoryRecordORM.subjects.contains([subject_id]),  # GIN-indexed
                MemoryRecordORM.kind == MemoryKind.BELIEF.value,
                MemoryRecordORM.hop_count > 0,
                MemoryRecordORM.valence < 0,
            )
        )
    ).scalars().all()
    holders = {row for row in rows if row != excluding_agent_id}
    return check_pileon(holders)


def _parse_retelling(text: str) -> str | None:
    try:
        data = json.loads(extract_json_object(text))
    except (json.JSONDecodeError, TypeError):
        return None
    belief = data.get("belief") if isinstance(data, dict) else None
    stripped = str(belief).strip() if belief is not None else ""
    return stripped or None


class GossipService:
    @staticmethod
    async def propagate(
        provider: LLMProvider,
        rng: random.Random,
        source_belief: MemoryRecord,
        listener_id: uuid.UUID,
        subject_id: uuid.UUID,
        trust_ab: float,
        tick: int,
        created_at: datetime,
    ) -> MemoryRecord | None:
        """One retelling: A shares `source_belief` (about `subject_id`) with
        `listener_id`. Returns the listener's new, distorted belief record,
        or `None` if it doesn't qualify to propagate (below the importance
        floor, or already at the hop limit).
        """
        if not eligible_to_propagate(source_belief.importance) or not within_hop_limit(
            source_belief.hop_count
        ):
            return None

        strength = inherited_belief_strength(source_belief.importance, trust_ab)
        prompt = Prompt(
            system="You are retelling something you heard, in your own words, with your own spin.",
            messages=[
                {
                    "role": "user",
                    "content": f'What you heard: "{source_belief.content}" {_RESPONSE_INSTRUCTION}',
                }
            ],
        )
        completion = await provider.tier1(prompt)
        retold = _parse_retelling(completion.text) or source_belief.content
        embedding = await provider.embed(retold)

        return MemoryRecord(
            id=seeded_uuid(rng),
            agent_id=listener_id,
            kind=MemoryKind.BELIEF,
            content=retold,
            embedding=embedding,
            importance=min(1.0, max(0.0, strength)),
            tick=tick,
            subjects=[subject_id],
            derived_from=[source_belief.id],
            hop_count=source_belief.hop_count + 1,
            valence=source_belief.valence,
            created_at=created_at,
        )


async def get_shareable_beliefs(
    session: AsyncSession, agent_id: uuid.UUID, limit: int = 5
) -> list[MemoryRecord]:
    """About/spec.md §8.1's gossip-eligible beliefs, queried directly rather
    than relying on them surviving `RetrievalService`'s general Tier-1/2
    candidate pool — About/plan.md T5.10/T5.11's actual root cause: reflection
    forms real about-a-third-party beliefs correctly, but a belief's
    importance almost never outscores a same-tick high-importance episodic
    event (a `betray` at 0.95 vs. spec.md §5.2's recency-heavy formula), so
    the general pool starves `confide` of anything real to share — 36,000+
    beliefs formed in About/plan.md's acceptance runs, `hop_count` never once
    above 0. A belief always carries exactly one subject (`runtime/
    reflection.py`), so "about someone else" is `subjects` not containing
    `agent_id` (GIN-indexed, `models/memory.py`).
    """
    rows = (
        await session.execute(
            select(MemoryRecordORM)
            .where(
                MemoryRecordORM.agent_id == agent_id,
                MemoryRecordORM.kind == MemoryKind.BELIEF.value,
                MemoryRecordORM.importance >= settings.gossip.min_importance_to_propagate,
                ~MemoryRecordORM.subjects.contains([agent_id]),
            )
            .order_by(MemoryRecordORM.importance.desc(), MemoryRecordORM.tick.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [memory_from_orm(row) for row in rows]


async def save_propagated_belief(session: AsyncSession, belief: MemoryRecord) -> None:
    session.add(memory_to_orm(belief))
    await session.flush()
