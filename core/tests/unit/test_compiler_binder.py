"""Compiler + Binder: About/plan.md M2 scope ("Compiler and binder")."""

import uuid

from otherworld.models.agent import AgentStatus
from otherworld.models.persona import BoundaryRule, PersonaObject, TraitVector, VoiceProfile
from otherworld.persona.binder import Binder
from otherworld.persona.compiler import Compiler
from otherworld.runtime.clock import tick_to_datetime
from otherworld.safety.registry import REGISTRY_VERSION

_PERSONA = PersonaObject(
    id=uuid.uuid4(),
    owner_id=uuid.uuid4(),
    version=1,
    voice=VoiceProfile(verbosity=0.5, formality=0.5, humour_style="dry", profanity_baseline=0.1,
                        characteristic_phrases=["fair enough"]),
    values=TraitVector(ambition=0.8, curiosity=0.8),
    boundaries=[
        BoundaryRule(
            id=uuid.uuid4(), description="no violence",
            predicate='category == "violence"', severity="block",
        )
    ],
    source_methods=["A"],
    created_at=tick_to_datetime(0),
)


def test_compiler_produces_identity_prompt_and_weights():
    bundle = Compiler.compile(_PERSONA)
    assert "dry" in bundle.identity_prompt
    assert "fair enough" in bundle.identity_prompt
    assert "no violence" in bundle.identity_prompt
    assert bundle.decision_weights["ambition"] == 0.8
    assert bundle.action_space_ref == REGISTRY_VERSION
    assert bundle.boundary_ruleset == _PERSONA.boundaries


def test_compiler_seeds_goals_from_high_traits():
    bundle = Compiler.compile(_PERSONA)
    assert len(bundle.initial_goals) == 2  # ambition and curiosity both >= threshold


def test_binder_produces_spawnable_agent():
    bundle = Compiler.compile(_PERSONA)
    world_id = uuid.uuid4()
    agent = Binder.bind(
        bundle,
        owner_id=_PERSONA.owner_id,
        persona_version=_PERSONA.version,
        world_id=world_id,
        display_name="Nyx",
        spawned_at=tick_to_datetime(0),
    )
    assert agent.status == AgentStatus.ACTIVE
    assert agent.world_id == world_id
    assert agent.persona_version == 1
    assert agent.goals == []
    assert agent.last_tick == 0
