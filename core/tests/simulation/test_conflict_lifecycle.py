"""T5.6, T5.7 — About/plan.md M5 acceptance tests: conflict triggers and
terminal transitions observed end-to-end through `runtime/resolver.py`,
against a real database, rather than just the pure functions in
`social/conflict.py` (already covered by `tests/unit/test_conflict.py`).
"""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime

import pytest

from otherworld.llm.providers.mock import MockLLMProvider
from otherworld.models.agent import Position
from otherworld.models.persona import PersonaObject, TraitVector, VoiceProfile
from otherworld.models.relationship import BondState
from otherworld.persona.compiler import AgentBundle, Compiler
from otherworld.runtime.resolver import Resolver
from otherworld.social.engine import get_edge, get_or_create_edge, save_edge

NOW = datetime.now(UTC)
ACTOR_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
TARGET_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
POSITION = Position(x=0, y=0, facing="s")


def _persona(**trait_overrides: float) -> PersonaObject:
    return PersonaObject(
        id=uuid.uuid4(), owner_id=uuid.uuid4(), version=1,
        voice=VoiceProfile(verbosity=0.4, formality=0.5, humour_style="dry", profanity_baseline=0.1),
        values=TraitVector(**trait_overrides), source_methods=["A"], created_at=NOW,
    )


def _bundle(**trait_overrides: float) -> AgentBundle:
    return Compiler.compile(_persona(**trait_overrides))


async def _make_friend_edge(session, world_id: uuid.UUID, rng: random.Random) -> None:
    """Seeds an established, bonded edge directly (skipping the many-tick
    climb) so a single `betray` can be tested against a real bonded state.
    """
    edge, _ = await get_or_create_edge(session, world_id, ACTOR_ID, TARGET_ID, uuid.uuid4(), tick=0)
    edge = edge.model_copy(update={"trust": 0.6, "bond_state": BondState.FRIEND})
    await save_edge(session, edge)


@pytest.mark.asyncio
async def test_betray_opens_a_conflict_and_strains_a_friend_edge(db_session):
    """T5.6 — the BETRAYAL trigger fires off a real `betray` action and
    moves a bonded edge to Strained."""
    world_id = uuid.uuid4()
    rng = random.Random(1)
    await _make_friend_edge(db_session, world_id, rng)

    await Resolver.resolve(
        db_session, MockLLMProvider(), rng, world_id, ACTOR_ID, POSITION, tick=10,
        action="betray", targets=[TARGET_ID], reasoning="test", bundles={TARGET_ID: _bundle()},
    )

    edge = await get_edge(db_session, world_id, ACTOR_ID, TARGET_ID)
    assert edge is not None
    assert edge.bond_state == BondState.STRAINED
    assert len(edge.conflict_log) == 1
    assert edge.conflict_log[0].resolution is None


@pytest.mark.asyncio
async def test_forgive_completes_repair_from_strained(db_session):
    """T5.7 — Repaired terminal transition, observed via the `forgive`
    action rather than by calling `resolve_conflict` directly."""
    world_id = uuid.uuid4()
    rng = random.Random(2)
    await _make_friend_edge(db_session, world_id, rng)

    await Resolver.resolve(
        db_session, MockLLMProvider(), rng, world_id, ACTOR_ID, POSITION, tick=10,
        action="betray", targets=[TARGET_ID], reasoning="test", bundles={TARGET_ID: _bundle()},
    )
    await Resolver.resolve(
        db_session, MockLLMProvider(), rng, world_id, TARGET_ID, POSITION, tick=20,
        action="forgive", targets=[ACTOR_ID], reasoning="test", bundles={ACTOR_ID: _bundle()},
    )

    edge = await get_edge(db_session, world_id, ACTOR_ID, TARGET_ID)
    assert edge is not None
    assert edge.bond_state in (BondState.FRIEND, BondState.ACQUAINTANCE)
    assert edge.conflict_log[0].resolution == "repaired"


@pytest.mark.asyncio
async def test_escalating_action_while_strained_leads_to_feud(db_session):
    """T5.7 — Feud terminal transition, via a second `take` while Strained."""
    world_id = uuid.uuid4()
    rng = random.Random(3)
    await _make_friend_edge(db_session, world_id, rng)

    await Resolver.resolve(
        db_session, MockLLMProvider(), rng, world_id, ACTOR_ID, POSITION, tick=10,
        action="betray", targets=[TARGET_ID], reasoning="test", bundles={TARGET_ID: _bundle()},
    )
    await Resolver.resolve(
        db_session, MockLLMProvider(), rng, world_id, ACTOR_ID, POSITION, tick=11,
        action="take", targets=[TARGET_ID], reasoning="test", bundles={TARGET_ID: _bundle()},
    )

    edge = await get_edge(db_session, world_id, ACTOR_ID, TARGET_ID)
    assert edge is not None
    assert edge.bond_state == BondState.FEUD


@pytest.mark.asyncio
async def test_apologise_repair_roll_uses_target_traits(db_session):
    """T5.8-adjacent — a highly forgiving, non-grudge-holding target repairs
    reliably; the roll reads the *target's* bundle, not the actor's."""
    world_id = uuid.uuid4()
    rng = random.Random(4)
    await _make_friend_edge(db_session, world_id, rng)

    await Resolver.resolve(
        db_session, MockLLMProvider(), rng, world_id, ACTOR_ID, POSITION, tick=10,
        action="betray", targets=[TARGET_ID], reasoning="test", bundles={TARGET_ID: _bundle()},
    )
    forgiving_target = _bundle(forgiveness=1.0, grudge_retention=0.0)
    resolved = False
    for i, seed in enumerate(range(100, 130)):
        edge = await get_edge(db_session, world_id, ACTOR_ID, TARGET_ID)
        if edge is not None and edge.bond_state != BondState.STRAINED:
            resolved = True
            break
        await Resolver.resolve(
            db_session, MockLLMProvider(), random.Random(seed), world_id, ACTOR_ID, POSITION,
            tick=12 + i, action="apologise", targets=[TARGET_ID], reasoning="test",
            bundles={TARGET_ID: forgiving_target},
        )
    edge = await get_edge(db_session, world_id, ACTOR_ID, TARGET_ID)
    assert edge is not None
    assert resolved or edge.bond_state != BondState.STRAINED
