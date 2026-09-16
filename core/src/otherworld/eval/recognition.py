"""The Recognition Metric. See About/spec.md §14, About/architecture.md §7.

The single most important test in the project — it validates assumption A1
(About/context.md §11): does an agent compiled from a persona actually
behave recognisably like the person it's from? Everything in Phase 1 exists
to answer this question before anything else gets built on top of it.

`RecognitionHarness` lives in the output plane conceptually (it consumes
events, About/architecture.md §7) even though nothing else in `output/`
exists yet — that package is still empty pending M10.
"""

from __future__ import annotations

import random
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from otherworld.models.events import ActionCategory, EventRecordORM
from otherworld.models.output import RecognitionTrial, recognition_trial_to_orm
from otherworld.persona.capture.writing import REDACTION_TOKEN, redact_names
from otherworld.safety.registry import ActionRegistry, UnknownActionError

MIN_SAMPLE_IMPORTANCE = 0.3  # spec.md §14 step 1
SAMPLE_SIZE = 10  # per side; 20 shown total

# A short, name-free, human-readable phrase per registered action. Kept
# deliberately generic — no target names, no owner-specific detail — since
# the whole point is testing recognition from *behaviour*, not from
# recognising a name that leaked into the description.
_ACTION_DESCRIPTIONS: dict[str, str] = {
    "move_to": "Moved to a new location",
    "follow": "Followed another agent",
    "flee": "Fled from something",
    "idle": "Stayed idle",
    "sleep": "Slept",
    "greet": "Greeted another agent",
    "speak_to": "Spoke to another agent",
    "ignore": "Ignored someone who addressed them",
    "join_group": "Joined a group",
    "leave_group": "Left a group",
    "confide": "Confided in another agent",
    "compliment": "Complimented another agent",
    "criticise": "Criticised another agent",
    "apologise": "Apologised to another agent",
    "forgive": "Forgave another agent",
    "reject": "Rejected someone",
    "betray": "Betrayed another agent's trust",
    "gather": "Gathered a resource",
    "build": "Built something",
    "give": "Gave an item to another agent",
    "request": "Requested an item from another agent",
    "trade": "Traded with another agent",
    "take": "Took something without asking",
    "destroy": "Destroyed something",
    "form_goal": "Formed a new goal",
    "abandon_goal": "Abandoned a goal",
    "reflect": "Reflected on recent experiences",
    "form_belief": "Formed a belief about another agent",
}


@dataclass(frozen=True)
class RecognitionQuestion:
    """One of the 20 presented items. Deliberately carries nothing that
    would identify its source agent — no display name, no handle — so the
    presentation layer can't leak provenance even by accident
    (About/plan.md T4.2, blinding).
    """

    event_id: uuid.UUID
    description: str


def event_category(action: str) -> ActionCategory:
    try:
        return ActionRegistry.resolve(action).category
    except UnknownActionError:
        return ActionCategory.INTERNAL


def describe_event(event: EventRecordORM) -> str:
    phrase = _ACTION_DESCRIPTIONS.get(event.action, f"Did '{event.action}'")
    # Defense in depth: nothing above ever includes a name, but redact
    # anyway in case a future milestone adds free text (an utterance) to
    # EventRecord and someone forgets to route it through here again.
    redacted = redact_names(phrase)
    if REDACTION_TOKEN in redacted:
        return redacted
    return phrase


class InsufficientEventsError(Exception):
    """Raised when an agent or world doesn't have enough eligible events yet
    to run a trial. Not a bug — it means "run the simulation longer."
    """


async def _eligible_events(session: AsyncSession, agent_id: uuid.UUID) -> list[EventRecordORM]:
    rows = (
        await session.execute(
            select(EventRecordORM).where(
                EventRecordORM.actor_id == agent_id,
                EventRecordORM.importance >= MIN_SAMPLE_IMPORTANCE,
            )
        )
    ).scalars().all()
    return list(rows)


def sample_own_actions(
    eligible: list[EventRecordORM], k: int, rng: random.Random
) -> list[EventRecordORM]:
    if len(eligible) < k:
        raise InsufficientEventsError(
            f"only {len(eligible)} events with importance >= {MIN_SAMPLE_IMPORTANCE}; need {k}"
        )
    return rng.sample(eligible, k)


def sample_decoy_actions(
    candidates: list[EventRecordORM], own_sample: list[EventRecordORM], k: int, rng: random.Random
) -> list[EventRecordORM]:
    """Category-matched decoy sampling (About/plan.md T4.1)."""
    if len(candidates) < k:
        raise InsufficientEventsError(f"only {len(candidates)} candidate decoy events; need {k}")

    target_counts = Counter(event_category(e.action) for e in own_sample)
    pool_by_category: dict[ActionCategory, list[EventRecordORM]] = defaultdict(list)
    for e in candidates:
        pool_by_category[event_category(e.action)].append(e)

    chosen: list[EventRecordORM] = []
    remaining = list(candidates)
    for category, count in target_counts.items():
        available = pool_by_category.get(category, [])
        take = rng.sample(available, min(count, len(available)))
        chosen.extend(take)
        for t in take:
            remaining.remove(t)

    # Top up with random picks if category-matching couldn't fill k —
    # happens when the decoy agent hasn't done enough of some category yet.
    while len(chosen) < k and remaining:
        pick = rng.choice(remaining)
        chosen.append(pick)
        remaining.remove(pick)

    return chosen[:k]


async def pick_decoy_agent(
    session: AsyncSession, world_id: uuid.UUID, exclude_agent_id: uuid.UUID, rng: random.Random
) -> uuid.UUID:
    rows = (
        await session.execute(
            select(EventRecordORM.actor_id)
            .where(EventRecordORM.world_id == world_id, EventRecordORM.actor_id != exclude_agent_id)
            .distinct()
        )
    ).scalars().all()
    if not rows:
        raise InsufficientEventsError(f"no other agent with events in world {world_id}")
    return rng.choice(list(rows))


@dataclass
class PreparedTrial:
    questions: list[RecognitionQuestion]  # shuffled; 20 items
    ground_truth: dict[uuid.UUID, bool]  # event_id -> True if it was the owner's own agent
    own_agent_action_ids: list[uuid.UUID]
    decoy_action_ids: list[uuid.UUID]


class RecognitionHarness:
    @staticmethod
    async def prepare_trial(
        session: AsyncSession,
        world_id: uuid.UUID,
        own_agent_id: uuid.UUID,
        rng: random.Random,
        decoy_agent_id: uuid.UUID | None = None,
    ) -> PreparedTrial:
        """Steps 1-4 of spec.md §14's protocol."""
        own_eligible = await _eligible_events(session, own_agent_id)
        own_sample = sample_own_actions(own_eligible, SAMPLE_SIZE, rng)

        if decoy_agent_id is None:
            decoy_agent_id = await pick_decoy_agent(session, world_id, own_agent_id, rng)
        decoy_candidates = await _eligible_events(session, decoy_agent_id)
        decoy_sample = sample_decoy_actions(decoy_candidates, own_sample, SAMPLE_SIZE, rng)

        all_events = [*own_sample, *decoy_sample]
        rng.shuffle(all_events)

        questions = [RecognitionQuestion(event_id=e.id, description=describe_event(e)) for e in all_events]
        own_ids = {e.id for e in own_sample}
        ground_truth = {e.id: (e.id in own_ids) for e in all_events}

        return PreparedTrial(
            questions=questions,
            ground_truth=ground_truth,
            own_agent_action_ids=[e.id for e in own_sample],
            decoy_action_ids=[e.id for e in decoy_sample],
        )

    @staticmethod
    def score(prepared: PreparedTrial, owner_selections: set[uuid.UUID]) -> float:
        """Recognition accuracy: correct identifications / 20 (spec.md §17)."""
        total = len(prepared.questions)
        correct = sum(
            1
            for q in prepared.questions
            if (q.event_id in owner_selections) == prepared.ground_truth[q.event_id]
        )
        return correct / total if total else 0.0

    @staticmethod
    async def record_trial(
        session: AsyncSession,
        owner_id: uuid.UUID,
        persona_version: int,
        prepared: PreparedTrial,
        owner_selections: set[uuid.UUID],
    ) -> RecognitionTrial:
        accuracy = RecognitionHarness.score(prepared, owner_selections)
        trial = RecognitionTrial(
            id=uuid.uuid4(),
            owner_id=owner_id,
            own_agent_action_ids=prepared.own_agent_action_ids,
            decoy_action_ids=prepared.decoy_action_ids,
            owner_selections=list(owner_selections),
            accuracy=accuracy,
            run_at=datetime.now(UTC),
            persona_version=persona_version,
        )
        session.add(recognition_trial_to_orm(trial))
        await session.flush()
        return trial


def interpret(accuracy: float) -> str:
    """spec.md §14's interpretation table."""
    if accuracy <= 0.55:
        return "FAILED — chance level. Assumption A1 has failed. Stop; return to persona capture."
    if accuracy < 0.70:
        return "WEAK — add method D (scenario replay); re-test before proceeding."
    if accuracy < 0.85:
        return "PASS — proceed to Phase 2."
    return "STRONG — proceed; use as the headline validation result."
