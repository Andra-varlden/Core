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

from otherworld.config import settings
from otherworld.models.events import ActionCategory, EventRecordORM
from otherworld.models.output import RecognitionTrial, recognition_trial_to_orm
from otherworld.persona.capture.writing import REDACTION_TOKEN, redact_names
from otherworld.safety.registry import ActionRegistry, UnknownActionError
from otherworld.social.engine import get_edge

MIN_SAMPLE_IMPORTANCE = 0.3  # spec.md §14 step 1 — kept for reference; no
# longer the quiz's own eligibility gate, see `_distinctive_action_types`.
#
# DEVIATION from spec.md §14 step 1, 2026-09-19 then revised 2026-09-20:
# importance>=0.3 turned out to be the wrong filter entirely for *this*
# purpose. Only relationship-milestone transitions (stranger->acquaintance->
# friend->close_bond) ever clear it, and those are near-identical, mechanical
# state-machine steps every agent goes through the same way — they carry no
# personality signal a real person could recognise ("did I become someone's
# friend at hour 8 or hour 16?" isn't something anyone could know about
# themselves). Confirmed live: two real people's questions were frequently
# byte-identical text, and even after a same-day timing tie-breaker was
# added, accuracy stayed at chance level (5-trial averages of 43-60%) for
# all 5 real people — not noise, a genuine floor. Meanwhile the population's
# actual *routine* behaviour (Orion gives gifts in 60%+ of interactions vs.
# a ~20% population average; Atlas/Jiths confide far more than average) is
# exactly the kind of thing a real person COULD recognise about themselves,
# and was being thrown away because it never reaches 0.3 importance.
# `_distinctive_action_types` replaces the importance floor with a
# per-person "does this action more than the population average" filter,
# which also removes the sample-size ceiling this session found (routine
# actions number in the hundreds per person, not ~30 total population-wide),
# so SAMPLE_SIZE is restored to spec's original N=10.
SAMPLE_SIZE = 10  # per side; 20 shown total.

# Excluded from distinctiveness scoring entirely: universal/mechanical, not
# a choice that varies by persona (spec.md §5.1 calls idle/sleep/move_to
# "routine movement", its own lowest tier — everyone does these the same).
_NON_DISTINCTIVE_ACTIONS = {"idle", "sleep", "move_to", "follow", "flee"}
# How many of an agent's most-distinctive action types feed the quiz pool.
# Capped rather than unbounded so the quiz stays about what's genuinely
# characteristic, not just "everything they've ever done."
_DISTINCTIVE_ACTION_TYPES = 3

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

# Real distinguishing content for the quiz, without ever showing raw AI
# reasoning text (deliberately excluded — About/models/events.py's
# `ProposedAction.reasoning` docstring: "never shown raw to users", since
# it's uncensored model output). Found live during the M4 real trial: with
# only the generic phrase above, two "greet" events are *literally
# identical text* — no way to actually recognise anything, since the
# template carries zero information about who or what changed. Each
# EventRecord's `relationship_deltas` already holds real, structured,
# always-safe data (the bond state that resulted, About/spec.md §6) —
# this is what actually distinguishes "greeted a total stranger" from
# "greeted someone they'd just become friends with", and it costs nothing
# extra to compute: it's already on every event, including ones already
# collected before this fix.
_BOND_TRANSITION_PHRASES: dict[str, str] = {
    "acquaintance": "which made them acquaintances",
    "friend": "which made them friends",
    "close_bond": "which formed a close bond",
    "strained": "which strained the relationship",
    "broken": "which broke off the relationship",
    "feud": "sparking a feud",
}
_BOND_STATE_PHRASES: dict[str, str] = {
    "stranger": "with a stranger",
    "acquaintance": "with an acquaintance",
    "friend": "with a friend",
    "close_bond": "with someone they share a close bond with",
    "strained": "with someone they're currently at odds with",
    "broken": "with someone they've cut ties with",
    "feud": "with someone they're feuding with",
}
# Actions whose own description already ends "...to/from/with another
# agent" — appending a plain "with a friend"-style clause to those would
# read as a double preposition ("gave an item to another agent with a
# friend"). Rephrased with an em dash instead once routine (non-milestone)
# actions started reaching the quiz far more often (About/eval/recognition.py's
# `SAMPLE_SIZE` docstring) and this stopped being a rare edge case.
_PREPOSITION_ENDING_ACTIONS = {"give", "request", "trade", "confide"}


def _relationship_clause(action: str, relationship_deltas: list[dict[str, object]]) -> str:
    if not relationship_deltas:
        return ""
    delta = relationship_deltas[0]
    before, after = delta.get("bond_state_before"), delta.get("bond_state_after")
    if before != after and isinstance(after, str) and after in _BOND_TRANSITION_PHRASES:
        return f", {_BOND_TRANSITION_PHRASES[after]}"
    if isinstance(after, str) and after in _BOND_STATE_PHRASES:
        phrase = _BOND_STATE_PHRASES[after]
        if action in _PREPOSITION_ENDING_ACTIONS:
            phrase = phrase.split(" ", 1)[1]  # drop the leading "with"/"from"-clashing preposition
            return f" — {phrase}"
        return f" {phrase}"
    return ""


def _timing_clause(elapsed_ticks: int | None) -> str:
    """Found live during the M4 real trial's post-mortem: every qualifying
    event across all 5 real people collapses to one of only ~3 possible
    sentences ("Greeted another agent, which made them acquaintances" /
    "...friends" / "Gave an item to another agent, which formed a close
    bond"), because relationship-milestone transitions are the *only* thing
    that ever clears the importance floor (see `eval/recognition.py`'s
    `SAMPLE_SIZE` docstring) and there are only a handful of distinct
    (action, resulting bond state) pairs in the whole population. Two
    people's questions — or an owner's own question and a decoy's — were
    frequently byte-identical text, making the quiz unanswerable above
    chance by construction, not because the underlying behaviour was
    unrecognisable. How long a relationship took to reach that milestone
    (fast trust vs. slow trust is a real persona-driven behavioural
    difference, About/spec.md's trait model) is real, safe, per-event
    content — no names, no raw reasoning — and is different for almost
    every event, breaking the collision.
    """
    if elapsed_ticks is None or elapsed_ticks < 0:
        return ""
    minutes = elapsed_ticks * settings.world.in_world_minutes_per_tick
    hours = minutes / 60
    days = hours / 24
    # Fine-grained hour buckets below a day: in a world where everyone
    # meets everyone at once (all 5 real people, About/runtime/scheduler.py's
    # `_materialise_new_encounters`), nearly every milestone happens within
    # the first in-world day — a single coarse "within a day" bucket was
    # tried first and still collapsed most of the population's events back
    # together (9 unique descriptions out of 30 real events, up from ~3,
    # but still a lot of collisions). Hours resolve almost all of that
    # remaining variance, since the actual ticks are rarely equal.
    if hours < 1:
        return ", moments after meeting them"
    if days < 1:
        return f", about {hours:.0f} hours after meeting them"
    if days < 7:
        return f", {days:.0f} days after meeting them"
    if days < 30:
        weeks = days / 7
        return f", about {weeks:.0f} week{'s' if weeks >= 1.5 else ''} after meeting them"
    months = days / 30
    return f", about {months:.0f} month{'s' if months >= 1.5 else ''} after meeting them"


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


def describe_event(event: EventRecordORM, elapsed_ticks: int | None = None) -> str:
    # `_ACTION_DESCRIPTIONS`'s values are a fixed, hand-written table with
    # no names in them, ever — redacting them was a real, live bug found
    # 2026-09-18: `redact_names` (built for free-text writing samples,
    # About/persona/capture/writing.py) treats *any* sentence-initial
    # capitalised word not in its whitelist as name-like, and every phrase
    # here starts with one ("Greeted", "Complimented", ...), so it
    # redacted the action verb itself on every single question, making the
    # actual Recognition Metric trial unreadable ("[REDACTED] another
    # agent"). Only the fallback below (an action not in the table) still
    # goes through it, as defence in depth against a future milestone
    # adding real free text to EventRecord.
    known = _ACTION_DESCRIPTIONS.get(event.action)
    if known is not None:
        return (
            known
            + _relationship_clause(event.action, event.relationship_deltas)
            + _timing_clause(elapsed_ticks)
        )
    fallback = f"Did '{event.action}'"
    redacted = redact_names(fallback)
    return redacted if REDACTION_TOKEN in redacted else fallback


class InsufficientEventsError(Exception):
    """Raised when an agent or world doesn't have enough eligible events yet
    to run a trial. Not a bug — it means "run the simulation longer."
    """


def compute_distinctiveness(
    agent_counts: Counter[str], population_counts: Counter[str]
) -> dict[str, float]:
    """(this agent's share of that action among their own actions) minus
    (the population's share of it) — positive means the agent does it more
    than average, which is exactly the kind of thing a real person could
    recognise about their own habits ("yeah, I'm the one who's always
    giving people things"). See `SAMPLE_SIZE`'s docstring for why this
    replaced the importance floor.
    """
    agent_total = sum(agent_counts.values())
    population_total = sum(population_counts.values())
    if agent_total == 0 or population_total == 0:
        return {}
    return {
        action: (count / agent_total) - (population_counts.get(action, 0) / population_total)
        for action, count in agent_counts.items()
    }


def _distinctive_action_types(
    distinctiveness: dict[str, float], top_n: int = _DISTINCTIVE_ACTION_TYPES
) -> list[str]:
    ranked = sorted(
        (a for a, score in distinctiveness.items() if score > 0), key=lambda a: -distinctiveness[a]
    )
    return ranked[:top_n]


async def _action_counts(
    session: AsyncSession, world_id: uuid.UUID, agent_id: uuid.UUID | None = None
) -> Counter[str]:
    query = select(EventRecordORM.action).where(
        EventRecordORM.world_id == world_id,
        EventRecordORM.action.not_in(_NON_DISTINCTIVE_ACTIONS),
    )
    if agent_id is not None:
        query = query.where(EventRecordORM.actor_id == agent_id)
    rows = (await session.execute(query)).scalars().all()
    return Counter(rows)


async def _distinctive_eligible_events(
    session: AsyncSession, world_id: uuid.UUID, agent_id: uuid.UUID
) -> list[EventRecordORM]:
    """The owner's quiz pool: real events from their own most-distinctive
    action types (see `compute_distinctiveness`), regardless of importance.
    """
    agent_counts = await _action_counts(session, world_id, agent_id)
    population_counts = await _action_counts(session, world_id)
    distinctive_types = _distinctive_action_types(compute_distinctiveness(agent_counts, population_counts))
    if not distinctive_types:
        return []
    rows = (
        await session.execute(
            select(EventRecordORM).where(
                EventRecordORM.actor_id == agent_id,
                EventRecordORM.action.in_(distinctive_types),
            )
        )
    ).scalars().all()
    return list(rows)


async def _non_mechanical_events(session: AsyncSession, agent_id: uuid.UUID) -> list[EventRecordORM]:
    """The decoy's candidate pool: broad on purpose — `sample_decoy_actions`
    below narrows it down to whatever categories the owner's sample needs.
    """
    rows = (
        await session.execute(
            select(EventRecordORM).where(
                EventRecordORM.actor_id == agent_id,
                EventRecordORM.action.not_in(_NON_DISTINCTIVE_ACTIONS),
            )
        )
    ).scalars().all()
    return list(rows)


def sample_own_actions(
    eligible: list[EventRecordORM], k: int, rng: random.Random
) -> list[EventRecordORM]:
    if len(eligible) < k:
        raise InsufficientEventsError(f"only {len(eligible)} eligible events; need {k}")
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


async def _elapsed_ticks_since_met(
    session: AsyncSession, world_id: uuid.UUID, event: EventRecordORM
) -> int | None:
    """How long after this pair first met did `event` happen — see
    `_timing_clause`'s docstring for why this matters for the quiz."""
    if not event.targets:
        return None
    try:
        target_id = uuid.UUID(event.targets[0])
    except (TypeError, ValueError):
        return None
    edge = await get_edge(session, world_id, event.actor_id, target_id)
    if edge is None:
        return None
    return event.tick - edge.created_tick


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
        """Steps 1-4 of spec.md §14's protocol (revised 2026-09-20 —
        distinctive-action sampling, not an importance floor; see
        `SAMPLE_SIZE`'s docstring)."""
        own_eligible = await _distinctive_eligible_events(session, world_id, own_agent_id)
        own_sample = sample_own_actions(own_eligible, SAMPLE_SIZE, rng)

        if decoy_agent_id is None:
            decoy_agent_id = await pick_decoy_agent(session, world_id, own_agent_id, rng)
        decoy_candidates = await _non_mechanical_events(session, decoy_agent_id)
        decoy_sample = sample_decoy_actions(decoy_candidates, own_sample, SAMPLE_SIZE, rng)

        all_events = [*own_sample, *decoy_sample]
        rng.shuffle(all_events)

        questions = [
            RecognitionQuestion(
                event_id=e.id,
                description=describe_event(e, await _elapsed_ticks_since_met(session, world_id, e)),
            )
            for e in all_events
        ]
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
