"""M6 scope T6.5, invariant I7: owner deletion cascade with zero residue."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from otherworld.models.agent import AgentORM, Position, agent_to_orm
from otherworld.models.auth import MagicLinkTokenORM
from otherworld.models.events import EventRecord, EventRecordORM, event_to_orm
from otherworld.models.memory import MemoryKind, MemoryRecord, MemoryRecordORM, memory_to_orm
from otherworld.models.output import RecognitionTrial, recognition_trial_to_orm
from otherworld.models.owner import OwnerORM
from otherworld.llm.providers.mock import MockLLMProvider
from otherworld.models.persona import PersonaObject, PersonaObjectORM, TraitVector, VoiceProfile
from otherworld.models.relationship import RelationshipEdgeORM
from otherworld.owner.deletion import delete_owner
from otherworld.owner.service import get_or_create_owner
from otherworld.persona.binder import Binder
from otherworld.persona.compiler import Compiler
from otherworld.persona.service import save_persona
from otherworld.runtime.clock import tick_to_datetime
from otherworld.social.engine import get_or_create_edge, save_edge

NOW = datetime.now(UTC)
POS = Position(x=0, y=0, facing="s")


async def _seed_two_owners_who_interacted(db_session, world_id):
    """Owner A (to be deleted) and Owner B (to survive), with real shared
    history: A's own event/memory, B's event/memory that references A as a
    witness/subject, and a relationship edge between their agents."""
    owner_a = await get_or_create_owner(db_session, "ToDelete", "todelete@example.com")
    owner_b = await get_or_create_owner(db_session, "Survivor", "survivor@example.com")

    persona_a = PersonaObject(
        id=uuid.uuid4(), owner_id=owner_a.id, version=1,
        voice=VoiceProfile(verbosity=0.4, formality=0.5, humour_style="dry", profanity_baseline=0.1),
        values=TraitVector(), source_methods=["A"], created_at=NOW,
    )
    persona_b = persona_a.model_copy(update={"id": uuid.uuid4(), "owner_id": owner_b.id})
    await save_persona(db_session, persona_a)
    await save_persona(db_session, persona_b)

    agent_a = Binder.bind(
        Compiler.compile(persona_a), owner_id=owner_a.id, persona_version=1, world_id=world_id,
        display_name="A", spawned_at=tick_to_datetime(0),
    )
    agent_b = Binder.bind(
        Compiler.compile(persona_b), owner_id=owner_b.id, persona_version=1, world_id=world_id,
        display_name="B", spawned_at=tick_to_datetime(0),
    )
    db_session.add(agent_to_orm(agent_a))
    db_session.add(agent_to_orm(agent_b))

    # A's own event and memory.
    a_event = EventRecord(
        id=uuid.uuid4(), world_id=world_id, tick=1, actor_id=agent_a.id, action="greet",
        targets=[agent_b.id], witnesses=[], position=POS, relationship_deltas=[],
        importance=0.15, owner_override=False, created_at=NOW,
    )
    db_session.add(event_to_orm(a_event))
    a_memory = MemoryRecord(
        id=uuid.uuid4(), agent_id=agent_a.id, kind=MemoryKind.EPISODIC, content="I greeted someone.",
        embedding=await MockLLMProvider().embed("greeted"), importance=0.15, tick=1,
        subjects=[agent_a.id, agent_b.id], created_at=NOW,
    )
    db_session.add(memory_to_orm(a_memory))

    # B's own event where A is a witness, and B's memory with A as a subject.
    b_event = EventRecord(
        id=uuid.uuid4(), world_id=world_id, tick=2, actor_id=agent_b.id, action="reflect",
        targets=[], witnesses=[agent_a.id], position=POS, relationship_deltas=[],
        importance=0.05, owner_override=False, created_at=NOW,
    )
    db_session.add(event_to_orm(b_event))
    b_memory = MemoryRecord(
        id=uuid.uuid4(), agent_id=agent_b.id, kind=MemoryKind.EPISODIC, content="Someone greeted me.",
        embedding=await MockLLMProvider().embed("greeted-back"), importance=0.15, tick=1,
        subjects=[agent_a.id, agent_b.id], created_at=NOW,
    )
    db_session.add(memory_to_orm(b_memory))

    edge, _ = await get_or_create_edge(db_session, world_id, agent_a.id, agent_b.id, uuid.uuid4(), tick=1)
    await save_edge(db_session, edge)

    trial = RecognitionTrial(
        id=uuid.uuid4(), owner_id=owner_a.id, own_agent_action_ids=[a_event.id], decoy_action_ids=[],
        owner_selections=[], accuracy=0.5, run_at=NOW, persona_version=1,
    )
    db_session.add(recognition_trial_to_orm(trial))

    db_session.add(
        MagicLinkTokenORM(
            id=uuid.uuid4(), owner_id=owner_a.id, token_hash="deadbeef",
            expires_at=NOW, used_at=None, created_at=NOW,
        )
    )

    await db_session.commit()
    return owner_a, owner_b, agent_a, agent_b, b_event.id, b_memory.id


async def test_deletion_removes_the_owners_own_data_entirely(db_session):
    world_id = uuid.uuid4()
    owner_a, owner_b, agent_a, agent_b, _b_event_id, _b_memory_id = await _seed_two_owners_who_interacted(
        db_session, world_id
    )

    receipt = await delete_owner(db_session, owner_a.id)
    await db_session.commit()

    assert receipt.personas_deleted == 1
    assert receipt.agents_deleted == 1
    assert receipt.own_events_deleted == 1
    assert receipt.own_memories_deleted == 1
    assert receipt.relationship_edges_deleted == 1
    assert receipt.magic_link_tokens_deleted == 1
    assert receipt.recognition_trials_deleted == 1

    assert await db_session.get(OwnerORM, owner_a.id) is None
    assert (
        await db_session.execute(select(PersonaObjectORM).where(PersonaObjectORM.owner_id == owner_a.id))
    ).scalar_one_or_none() is None


async def test_deletion_anonymises_but_does_not_delete_the_survivors_data(db_session):
    world_id = uuid.uuid4()
    owner_a, owner_b, agent_a, agent_b, b_event_id, b_memory_id = await _seed_two_owners_who_interacted(
        db_session, world_id
    )

    receipt = await delete_owner(db_session, owner_a.id)
    await db_session.commit()

    assert receipt.other_events_anonymised == 1
    assert receipt.other_memories_anonymised == 1

    # Owner B and their agent survive untouched.
    assert await db_session.get(OwnerORM, owner_b.id) is not None

    surviving_event = await db_session.get(EventRecordORM, b_event_id)
    assert surviving_event is not None
    assert str(agent_a.id) not in surviving_event.witnesses  # reference stripped
    assert surviving_event.actor_id == agent_b.id  # event itself preserved

    surviving_memory = await db_session.get(MemoryRecordORM, b_memory_id)
    assert surviving_memory is not None
    assert agent_a.id not in surviving_memory.subjects  # reference stripped
    assert agent_b.id in surviving_memory.subjects  # B's own presence untouched


async def test_zero_residue_no_table_references_the_deleted_agent_anywhere(db_session):
    """T6.5's literal acceptance test: scan every table that could possibly
    hold a reference to the deleted agent and assert none remain."""
    world_id = uuid.uuid4()
    owner_a, owner_b, agent_a, agent_b, _b_event_id, _b_memory_id = await _seed_two_owners_who_interacted(
        db_session, world_id
    )

    await delete_owner(db_session, owner_a.id)
    await db_session.commit()

    all_events = (await db_session.execute(select(EventRecordORM))).scalars().all()
    for row in all_events:
        assert row.actor_id != agent_a.id
        assert str(agent_a.id) not in row.targets
        assert str(agent_a.id) not in row.witnesses

    all_memories = (await db_session.execute(select(MemoryRecordORM))).scalars().all()
    for row in all_memories:
        assert row.agent_id != agent_a.id
        assert agent_a.id not in row.subjects

    assert await db_session.get(AgentORM, agent_a.id) is None
    remaining_edges = (await db_session.execute(select(RelationshipEdgeORM))).scalars().all()
    for edge in remaining_edges:
        assert agent_a.id not in (edge.agent_a_id, edge.agent_b_id)


async def test_deleting_an_already_deleted_owner_is_a_harmless_no_op(db_session):
    world_id = uuid.uuid4()
    owner_a, *_ = await _seed_two_owners_who_interacted(db_session, world_id)
    await delete_owner(db_session, owner_a.id)
    await db_session.commit()

    receipt = await delete_owner(db_session, owner_a.id)  # second call, nothing left to find
    await db_session.commit()

    assert receipt.personas_deleted == 0
    assert receipt.agents_deleted == 0
