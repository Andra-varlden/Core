"""T0.3 — round-trip every model: construct -> persist -> load -> compare."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from otherworld.models.agent import Agent, AgentStatus, Goal, Position, agent_from_orm, agent_to_orm
from otherworld.models.events import EventRecord, event_from_orm, event_to_orm
from otherworld.models.memory import (
    EMBEDDING_DIM,
    MemoryKind,
    MemoryRecord,
    memory_from_orm,
    memory_to_orm,
)
from otherworld.models.output import (
    Highlight,
    RecognitionTrial,
    highlight_from_orm,
    highlight_to_orm,
    recognition_trial_from_orm,
    recognition_trial_to_orm,
)
from otherworld.models.owner import (
    ConsentFlags,
    IdentityMode,
    Owner,
    VisibilityScope,
    owner_from_orm,
    owner_to_orm,
)
from otherworld.models.persona import (
    BoundaryRule,
    PersonaObject,
    SeededRelationship,
    TraitVector,
    VoiceProfile,
    persona_from_orm,
    persona_to_orm,
)
from otherworld.models.relationship import (
    BondState,
    ConflictRecord,
    ConflictTrigger,
    RelationshipEdge,
    edge_from_orm,
    edge_to_orm,
)
from otherworld.models.world import (
    Feature,
    FeatureORM,
    TerrainType,
    Tile,
    TileORM,
    World,
    Zone,
    feature_from_orm,
    feature_to_orm,
    tile_from_orm,
    tile_to_orm,
    world_from_orm,
    world_to_orm,
    zone_from_orm,
    zone_to_orm,
)

NOW = datetime.now(UTC)


async def _roundtrip(session, pydantic_obj, orm_obj, from_fn, table_pk_attr="id"):
    session.add(orm_obj)
    await session.flush()
    row = await session.get(type(orm_obj), getattr(orm_obj, table_pk_attr))
    reloaded = from_fn(row)
    assert reloaded == pydantic_obj
    return reloaded


@pytest.mark.asyncio
async def test_owner_roundtrip(db_session):
    owner = Owner(
        id=uuid.uuid4(),
        handle="hana",
        email="hana@example.com",
        consent=ConsentFlags(
            identity_mode=IdentityMode.PSEUDONYMOUS,
            visibility_scope=VisibilityScope.PRIVATE,
            third_party_consent_intent=True,
            liability_acknowledged=True,
            tos_version="2026-09-14",
            acknowledged_at=NOW,
        ),
        created_at=NOW,
        last_active_at=NOW,
        status="active",
    )
    await _roundtrip(db_session, owner, owner_to_orm(owner), owner_from_orm)


@pytest.mark.asyncio
async def test_persona_roundtrip(db_session):
    owner_id = uuid.uuid4()
    persona = PersonaObject(
        id=uuid.uuid4(),
        owner_id=owner_id,
        version=1,
        voice=VoiceProfile(
            verbosity=0.4, formality=0.6, humour_style="dry", profanity_baseline=0.1,
            characteristic_phrases=["fair enough"], diction_notes="terse, understated",
        ),
        values=TraitVector(),
        social=[
            SeededRelationship(
                counterpart_owner_id=uuid.uuid4(), claimed_bond="friend", mutual_accepted=True,
                accepted_at=NOW, shared_context=["college roommates"],
            )
        ],
        boundaries=[
            BoundaryRule(
                id=uuid.uuid4(), description="no romance",
                predicate="category != romance", severity="block",
            )
        ],
        source_methods=["A", "B"],
        field_confidence={"loyalty": 0.8},
        created_at=NOW,
        compiled_at=None,
    )
    await _roundtrip(db_session, persona, persona_to_orm(persona), persona_from_orm)


@pytest.mark.asyncio
async def test_agent_roundtrip(db_session):
    agent = Agent(
        id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        persona_version=1,
        world_id=uuid.uuid4(),
        display_name="Nyx",
        status=AgentStatus.ACTIVE,
        position=Position(x=3, y=4, facing="n"),
        goals=[
            Goal(id=uuid.uuid4(), description="make a friend", priority=0.7, origin="self", created_tick=0)
        ],
        current_path=[(3, 4), (3, 5)],
        last_tick=42,
        created_at=NOW,
    )
    await _roundtrip(db_session, agent, agent_to_orm(agent), agent_from_orm)


@pytest.mark.asyncio
async def test_memory_roundtrip(db_session):
    memory = MemoryRecord(
        id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        kind=MemoryKind.EPISODIC,
        content="Met Nyx at the market square.",
        embedding=[0.1] * EMBEDDING_DIM,
        importance=0.6,
        tick=10,
        subjects=[uuid.uuid4()],
        source_event_id=uuid.uuid4(),
        derived_from=[],
        created_at=NOW,
    )
    await _roundtrip(db_session, memory, memory_to_orm(memory), memory_from_orm)


@pytest.mark.asyncio
async def test_relationship_edge_roundtrip(db_session):
    a, b = sorted([uuid.uuid4(), uuid.uuid4()], key=str)
    edge = RelationshipEdge(
        id=uuid.uuid4(),
        world_id=uuid.uuid4(),
        agent_a_id=a,
        agent_b_id=b,
        trust=0.4,
        bond_state=BondState.ACQUAINTANCE,
        seeded=False,
        conflict_log=[
            ConflictRecord(
                id=uuid.uuid4(), trigger=ConflictTrigger.NEGLECT, theme="silence",
                severity=0.3, occurred_tick=5, resolved_tick=None, resolution=None,
            )
        ],
        shared_memory_ids=[uuid.uuid4()],
        contact_count=3,
        last_contact_tick=5,
        created_tick=1,
    )
    await _roundtrip(db_session, edge, edge_to_orm(edge), edge_from_orm)


def test_relationship_edge_rejects_unordered_pair():
    a, b = sorted([uuid.uuid4(), uuid.uuid4()], key=str)
    with pytest.raises(ValueError):
        RelationshipEdge(
            id=uuid.uuid4(), world_id=uuid.uuid4(), agent_a_id=b, agent_b_id=a,
            trust=0.0, last_contact_tick=0, created_tick=0,
        )


@pytest.mark.asyncio
async def test_world_zone_feature_tile_roundtrip(db_session):
    world = World(
        id=uuid.uuid4(), name="Arrival World", width=60, height=60,
        current_tick=0, population=0, population_cap=20, status="open", created_at=NOW,
    )
    await _roundtrip(db_session, world, world_to_orm(world), world_from_orm)

    zone = Zone(id=uuid.uuid4(), world_id=world.id, name="Market square", bounds=(0, 0, 10, 10))
    await _roundtrip(db_session, zone, zone_to_orm(zone), zone_from_orm)

    feature = Feature(id=uuid.uuid4(), x=2, y=2, kind="bench", state={})
    feature_orm = feature_to_orm(feature, world.id)
    db_session.add(feature_orm)
    await db_session.flush()
    reloaded = feature_from_orm(await db_session.get(FeatureORM, feature.id))
    assert reloaded == feature

    tile = Tile(x=1, y=1, terrain=TerrainType.GRASS, walkable=True, zone_id=None)
    tile_orm = tile_to_orm(tile, world.id)
    db_session.add(tile_orm)
    await db_session.flush()
    row = (
        await db_session.execute(
            select(TileORM).where(TileORM.world_id == world.id, TileORM.x == 1, TileORM.y == 1)
        )
    ).scalar_one()
    assert tile_from_orm(row) == tile


@pytest.mark.asyncio
async def test_event_record_roundtrip(db_session):
    event = EventRecord(
        id=uuid.uuid4(), world_id=uuid.uuid4(), tick=7, actor_id=uuid.uuid4(),
        action="greet", targets=[uuid.uuid4()], witnesses=[uuid.uuid4()],
        position=Position(x=1, y=1, facing="s"), relationship_deltas=[{"trust": 0.03}],
        importance=0.6, owner_override=False, created_at=NOW,
    )
    await _roundtrip(db_session, event, event_to_orm(event), event_from_orm)


@pytest.mark.asyncio
async def test_highlight_and_recognition_trial_roundtrip(db_session):
    highlight = Highlight(
        id=uuid.uuid4(), world_id=uuid.uuid4(), event_ids=[uuid.uuid4()], arc_id=uuid.uuid4(),
        narration="Nyx met a stranger at the market.", importance=0.7,
        participants=[uuid.uuid4()], visibility=VisibilityScope.PUBLIC, created_at=NOW,
    )
    await _roundtrip(db_session, highlight, highlight_to_orm(highlight), highlight_from_orm)

    trial = RecognitionTrial(
        id=uuid.uuid4(), owner_id=uuid.uuid4(),
        own_agent_action_ids=[uuid.uuid4() for _ in range(10)],
        decoy_action_ids=[uuid.uuid4() for _ in range(10)],
        owner_selections=[uuid.uuid4() for _ in range(10)],
        accuracy=0.7, run_at=NOW, persona_version=1,
    )
    await _roundtrip(db_session, trial, recognition_trial_to_orm(trial), recognition_trial_from_orm)
