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
from otherworld.models.agent import Agent, AgentStatus, Goal, Position
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

    await run_maintenance_scan(db_session, world_id, [], {}, random.Random(1), tick=2000)

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
        db_session, world_id, [], {}, random.Random(1),
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

    await run_maintenance_scan(db_session, world_id, [], {}, random.Random(1), tick=10)

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
        db_session, world_id, [], {}, random.Random(1), tick=settings.conflict.neglect_ticks + 1
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

    await run_maintenance_scan(db_session, world_id, [], {}, random.Random(1), tick=10)

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

    await run_maintenance_scan(db_session, world_id, [], bundles, random.Random(1), tick=10)

    updated_ac = await get_edge(db_session, world_id, A_ID, C_ID)
    assert updated_ac is not None
    assert updated_ac.bond_state == BondState.STRAINED
    assert updated_ac.conflict_log[0].trigger == ConflictTrigger.CONTAGION


@pytest.mark.asyncio
async def test_contagion_uses_this_scans_own_decay_demoted_state_not_stale_data(db_session):
    """Regression test for the M4 real-trial post-mortem audit: `edges` was
    fetched once and never actually updated in place (pydantic models are
    copy-on-write, and rebinding the loop variable doesn't mutate the list),
    so CONTAGION/VALUE_CLASH always saw every edge's state from BEFORE this
    scan's own decay and decay-driven demotion ran, one whole scan interval
    stale. Here A-B starts Friend but has gone silent long enough that this
    exact scan's own decay demotes it below Friend before CONTAGION's
    Friend+ eligibility check runs a few lines later — A-C must NOT get
    contagion from B's feud with C, because A isn't Friend+ with B anymore
    as of this scan.
    """
    world_id = uuid.uuid4()

    ab, _ = await get_or_create_edge(db_session, world_id, A_ID, B_ID, uuid.uuid4(), tick=0)
    # trust=0.30 with no contact since tick 0 decays to well below
    # `demote_friend_below` (0.25) by the time this scan runs at tick 2000.
    ab = ab.model_copy(update={"bond_state": BondState.FRIEND, "trust": 0.30, "last_contact_tick": 0})
    await save_edge(db_session, ab)

    bc, _ = await get_or_create_edge(db_session, world_id, B_ID, C_ID, uuid.uuid4(), tick=0)
    bc = bc.model_copy(update={"bond_state": BondState.FEUD, "trust": -0.8})
    await save_edge(db_session, bc)

    # last_contact_tick kept recent so A-C doesn't ALSO decay/demote on its
    # own this scan — the point is to isolate whether CONTAGION incorrectly
    # fires onto it, not to also exercise A-C's own staleness.
    ac, _ = await get_or_create_edge(db_session, world_id, A_ID, C_ID, uuid.uuid4(), tick=0)
    ac = ac.model_copy(update={"bond_state": BondState.ACQUAINTANCE, "trust": 0.1, "last_contact_tick": 1990})
    await save_edge(db_session, ac)

    bundles = {A_ID: _bundle(loyalty=0.9, independence=0.1)}

    await run_maintenance_scan(db_session, world_id, [], bundles, random.Random(1), tick=2000)

    demoted_ab = await get_edge(db_session, world_id, A_ID, B_ID)
    assert demoted_ab is not None and demoted_ab.bond_state != BondState.FRIEND

    updated_ac = await get_edge(db_session, world_id, A_ID, C_ID)
    assert updated_ac is not None
    assert updated_ac.bond_state == BondState.ACQUAINTANCE  # no contagion — A-B wasn't Friend+ this scan
    assert updated_ac.conflict_log == []


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

    await run_maintenance_scan(db_session, world_id, [], bundles, random.Random(1), tick=10)

    updated_ac = await get_edge(db_session, world_id, A_ID, C_ID)
    assert updated_ac is not None
    assert updated_ac.bond_state == BondState.ACQUAINTANCE


def _agent(agent_id, goals=()) -> Agent:
    return Agent(
        id=agent_id, owner_id=uuid.uuid4(), persona_version=1, world_id=uuid.uuid4(),
        display_name=str(agent_id), status=AgentStatus.ACTIVE,
        position=Position(x=0, y=0, facing="s"), goals=list(goals), created_at=NOW,
    )


def _exclusive_goal(target_id) -> Goal:
    return Goal(
        id=uuid.uuid4(), description="win them over", priority=0.5, origin="self",
        created_tick=0, target_agent_id=target_id, exclusive=True,
    )


@pytest.mark.asyncio
async def test_scan_opens_a_value_clash_when_two_bonded_agents_target_the_same_third_party(db_session):
    world_id = uuid.uuid4()
    edge, _ = await get_or_create_edge(db_session, world_id, A_ID, B_ID, uuid.uuid4(), tick=0)
    edge = edge.model_copy(update={"bond_state": BondState.ACQUAINTANCE, "trust": 0.2})
    await save_edge(db_session, edge)

    agents = [_agent(A_ID, [_exclusive_goal(C_ID)]), _agent(B_ID, [_exclusive_goal(C_ID)])]

    await run_maintenance_scan(db_session, world_id, agents, {}, random.Random(1), tick=10)

    updated = await get_edge(db_session, world_id, A_ID, B_ID)
    assert updated is not None
    assert updated.bond_state == BondState.STRAINED
    assert updated.conflict_log[0].trigger == ConflictTrigger.VALUE_CLASH


@pytest.mark.asyncio
async def test_scan_does_not_open_value_clash_for_non_exclusive_or_different_targets(db_session):
    world_id = uuid.uuid4()
    edge, _ = await get_or_create_edge(db_session, world_id, A_ID, B_ID, uuid.uuid4(), tick=0)
    edge = edge.model_copy(update={"bond_state": BondState.ACQUAINTANCE, "trust": 0.2})
    await save_edge(db_session, edge)

    non_exclusive = Goal(
        id=uuid.uuid4(), description="be near them", priority=0.5, origin="self",
        created_tick=0, target_agent_id=C_ID, exclusive=False,
    )
    agents = [_agent(A_ID, [_exclusive_goal(C_ID)]), _agent(B_ID, [non_exclusive])]

    await run_maintenance_scan(db_session, world_id, agents, {}, random.Random(1), tick=10)

    updated = await get_edge(db_session, world_id, A_ID, B_ID)
    assert updated is not None
    assert updated.bond_state == BondState.ACQUAINTANCE


@pytest.mark.asyncio
async def test_scan_damping_factor_of_zero_suppresses_a_new_trigger(db_session):
    world_id = uuid.uuid4()
    edge, _ = await get_or_create_edge(db_session, world_id, A_ID, B_ID, uuid.uuid4(), tick=0)
    edge = edge.model_copy(update={"bond_state": BondState.FRIEND, "trust": 0.9, "last_contact_tick": 0})
    await save_edge(db_session, edge)

    await run_maintenance_scan(
        db_session, world_id, [], {}, random.Random(1), tick=settings.conflict.neglect_ticks + 1,
        damping_factor=0.0,
    )

    updated = await get_edge(db_session, world_id, A_ID, B_ID)
    assert updated is not None
    assert updated.bond_state == BondState.FRIEND
    assert updated.conflict_log == []
