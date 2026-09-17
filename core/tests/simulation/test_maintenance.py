"""About/plan.md M5: the periodic maintenance scan (`social/maintenance.py`)
actually drives trust decay, decay-driven demotion, Strained timeout/
escalation, and the scan-tied conflict triggers (NEGLECT, CONTAGION) against
a real database — the gap About/plan.md's T5.1 run found: these all existed
as tested pure functions but nothing ever called them."""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime

import pytest

from otherworld.config import settings
from otherworld.models.persona import PersonaObject, TraitVector, VoiceProfile
from otherworld.models.relationship import BondState, ConflictTrigger
from otherworld.persona.compiler import Compiler
from otherworld.social.conflict import open_conflict
from otherworld.social.engine import get_edge, get_or_create_edge, save_edge
from otherworld.social.maintenance import run_maintenance_scan

NOW = datetime.now(UTC)
A_ID, B_ID, C_ID = uuid.UUID(int=1), uuid.UUID(int=2), uuid.UUID(int=3)


def _persona(**trait_overrides: float) -> PersonaObject:
    return PersonaObject(
        id=uuid.uuid4(), owner_id=uuid.uuid4(), version=1,
        voice=VoiceProfile(verbosity=0.4, formality=0.5, humour_style="dry", profanity_baseline=0.1),
        values=TraitVector(**trait_overrides), source_methods=["A"], created_at=NOW,
    )


def _bundle(**trait_overrides: float):
    return Compiler.compile(_persona(**trait_overrides))


@pytest.mark.asyncio
async def test_scan_decays_trust_and_demotes_a_stale_friend_edge(db_session):
    world_id = uuid.uuid4()
    edge, _ = await get_or_create_edge(db_session, world_id, A_ID, B_ID, uuid.uuid4(), tick=0)
    edge = edge.model_copy(update={"bond_state": BondState.FRIEND, "trust": 0.26, "last_contact_tick": 0})
    await save_edge(db_session, edge)

    await run_maintenance_scan(db_session, world_id, {}, random.Random(1), tick=2000)

    updated = await get_edge(db_session, world_id, A_ID, B_ID)
    assert updated is not None
    assert updated.trust < 0.26  # decayed
    assert updated.bond_state == BondState.ACQUAINTANCE  # demoted once trust crossed demote_friend_below


@pytest.mark.asyncio
async def test_scan_times_out_a_strained_edge_to_broken(db_session):
    world_id = uuid.uuid4()
    edge, _ = await get_or_create_edge(db_session, world_id, A_ID, B_ID, uuid.uuid4(), tick=0)
    edge = edge.model_copy(update={"bond_state": BondState.FRIEND, "trust": 0.5})
    edge = open_conflict(edge, ConflictTrigger.BETRAYAL, theme="money", tick=0, rng_id=uuid.uuid4())
    await save_edge(db_session, edge)

    await run_maintenance_scan(
        db_session, world_id, {}, random.Random(1),
        tick=settings.conflict.strained_to_broken_ticks + 1,
    )

    updated = await get_edge(db_session, world_id, A_ID, B_ID)
    assert updated is not None
    assert updated.bond_state == BondState.BROKEN


@pytest.mark.asyncio
async def test_scan_escalates_a_strained_edge_to_feud_on_trust_collapse(db_session):
    world_id = uuid.uuid4()
    edge, _ = await get_or_create_edge(db_session, world_id, A_ID, B_ID, uuid.uuid4(), tick=0)
    edge = edge.model_copy(update={"bond_state": BondState.FRIEND, "trust": -0.5})
    edge = open_conflict(edge, ConflictTrigger.BETRAYAL, theme="money", tick=0, rng_id=uuid.uuid4())
    await save_edge(db_session, edge)

    await run_maintenance_scan(db_session, world_id, {}, random.Random(1), tick=10)

    updated = await get_edge(db_session, world_id, A_ID, B_ID)
    assert updated is not None
    assert updated.bond_state == BondState.FEUD


@pytest.mark.asyncio
async def test_scan_opens_a_neglect_trigger_on_a_stale_high_trust_edge(db_session):
    world_id = uuid.uuid4()
    edge, _ = await get_or_create_edge(db_session, world_id, A_ID, B_ID, uuid.uuid4(), tick=0)
    # trust=0.9 so it's still >= friend_trust_threshold after this scan's own decay pass.
    edge = edge.model_copy(update={"bond_state": BondState.FRIEND, "trust": 0.9, "last_contact_tick": 0})
    await save_edge(db_session, edge)

    await run_maintenance_scan(
        db_session, world_id, {}, random.Random(1), tick=settings.conflict.neglect_ticks + 1
    )

    updated = await get_edge(db_session, world_id, A_ID, B_ID)
    assert updated is not None
    assert updated.bond_state == BondState.STRAINED
    assert updated.conflict_log[0].trigger == ConflictTrigger.NEGLECT


@pytest.mark.asyncio
async def test_scan_does_not_open_neglect_on_a_fresh_edge(db_session):
    world_id = uuid.uuid4()
    edge, _ = await get_or_create_edge(db_session, world_id, A_ID, B_ID, uuid.uuid4(), tick=0)
    edge = edge.model_copy(update={"bond_state": BondState.FRIEND, "trust": 0.5, "last_contact_tick": 0})
    await save_edge(db_session, edge)

    await run_maintenance_scan(db_session, world_id, {}, random.Random(1), tick=10)

    updated = await get_edge(db_session, world_id, A_ID, B_ID)
    assert updated is not None
    assert updated.bond_state == BondState.FRIEND
    assert updated.conflict_log == []


@pytest.mark.asyncio
async def test_scan_applies_contagion_from_a_feuding_friend(db_session):
    """A is Friend+ with B; B is Feuding with C; A has an existing edge to
    C — About/spec.md §7.1's CONTAGION trigger should open on A-C."""
    world_id = uuid.uuid4()

    ab, _ = await get_or_create_edge(db_session, world_id, A_ID, B_ID, uuid.uuid4(), tick=0)
    ab = ab.model_copy(update={"bond_state": BondState.FRIEND, "trust": 0.6})
    await save_edge(db_session, ab)

    bc, _ = await get_or_create_edge(db_session, world_id, B_ID, C_ID, uuid.uuid4(), tick=0)
    bc = bc.model_copy(update={"bond_state": BondState.FEUD, "trust": -0.8})
    await save_edge(db_session, bc)

    ac, _ = await get_or_create_edge(db_session, world_id, A_ID, C_ID, uuid.uuid4(), tick=0)
    ac = ac.model_copy(update={"bond_state": BondState.ACQUAINTANCE, "trust": 0.1})
    await save_edge(db_session, ac)

    # High loyalty, low independence => high contagion_susceptibility.
    bundles = {A_ID: _bundle(loyalty=0.9, independence=0.1)}

    await run_maintenance_scan(db_session, world_id, bundles, random.Random(1), tick=10)

    updated_ac = await get_edge(db_session, world_id, A_ID, C_ID)
    assert updated_ac is not None
    assert updated_ac.bond_state == BondState.STRAINED
    assert updated_ac.conflict_log[0].trigger == ConflictTrigger.CONTAGION


@pytest.mark.asyncio
async def test_scan_skips_contagion_for_a_highly_independent_agent(db_session):
    world_id = uuid.uuid4()

    ab, _ = await get_or_create_edge(db_session, world_id, A_ID, B_ID, uuid.uuid4(), tick=0)
    ab = ab.model_copy(update={"bond_state": BondState.FRIEND, "trust": 0.6})
    await save_edge(db_session, ab)

    bc, _ = await get_or_create_edge(db_session, world_id, B_ID, C_ID, uuid.uuid4(), tick=0)
    bc = bc.model_copy(update={"bond_state": BondState.FEUD, "trust": -0.8})
    await save_edge(db_session, bc)

    ac, _ = await get_or_create_edge(db_session, world_id, A_ID, C_ID, uuid.uuid4(), tick=0)
    ac = ac.model_copy(update={"bond_state": BondState.ACQUAINTANCE, "trust": 0.1})
    await save_edge(db_session, ac)

    # independence=1.0 => contagion_susceptibility is exactly 0.
    bundles = {A_ID: _bundle(loyalty=0.9, independence=1.0)}

    await run_maintenance_scan(db_session, world_id, bundles, random.Random(1), tick=10)

    updated_ac = await get_edge(db_session, world_id, A_ID, C_ID)
    assert updated_ac is not None
    assert updated_ac.bond_state == BondState.ACQUAINTANCE
