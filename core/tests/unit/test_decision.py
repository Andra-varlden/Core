"""About/plan.md M4: the decision prompt must actually surface what
`RetrievalService` retrieved — the real 5-person trial found that without
this, a real model has nothing to react to and reliably defaults to
generic greet/idle/sleep for an entire simulated week (see
`runtime/decision.py`'s `_recent_memory_summary` docstring)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from otherworld.llm.protocol import Completion, Prompt
from otherworld.models.agent import Agent, AgentStatus, Position
from otherworld.models.memory import MemoryKind, MemoryRecord
from otherworld.models.persona import PersonaObject, TraitVector, VoiceProfile
from otherworld.models.relationship import BondState, RelationshipEdge
from otherworld.persona.compiler import Compiler
from otherworld.runtime.decision import DecisionEngine
from otherworld.runtime.perception import Observation

NOW = datetime.now(UTC)
AGENT_ID = uuid.uuid4()
OTHER_ID = uuid.uuid4()
THIRD_ID = uuid.uuid4()


class _CapturingProvider:
    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.last_prompt: Prompt | None = None

    async def tier1(self, prompt: Prompt) -> Completion:
        self.last_prompt = prompt
        return Completion(text=self.response_text, input_tokens=1, output_tokens=1, model="test")

    async def tier2(self, prompt: Prompt) -> Completion:
        return await self.tier1(prompt)

    async def embed(self, text: str) -> list[float]:
        return [0.0]


def _agent() -> Agent:
    return Agent(
        id=AGENT_ID, owner_id=uuid.uuid4(), persona_version=1, world_id=uuid.uuid4(),
        display_name="A", status=AgentStatus.ACTIVE, position=Position(x=0, y=0, facing="s"),
        goals=[], created_at=NOW,
    )


def _bundle():
    persona = PersonaObject(
        id=uuid.uuid4(), owner_id=uuid.uuid4(), version=1,
        voice=VoiceProfile(verbosity=0.4, formality=0.5, humour_style="dry", profanity_baseline=0.1),
        values=TraitVector(), source_methods=["A"], created_at=NOW,
    )
    return Compiler.compile(persona)


def _memory(content: str, tick: int) -> MemoryRecord:
    return MemoryRecord(
        id=uuid.uuid4(), agent_id=AGENT_ID, kind=MemoryKind.EPISODIC, content=content,
        embedding=[0.0], importance=0.5, tick=tick, subjects=[AGENT_ID, OTHER_ID], created_at=NOW,
    )


@pytest.mark.asyncio
async def test_decide_surfaces_retrieved_memory_content_in_the_prompt():
    provider = _CapturingProvider('{"action": "idle", "targets": [], "params": {}, "reasoning": "x"}')
    retrieved = [_memory("Another agent did 'betray' to me at tick 10.", tick=10)]
    observation = Observation(tick=20, agent_id=AGENT_ID, zone="room", visible_agents=[OTHER_ID])

    await DecisionEngine.decide(_agent(), _bundle(), observation, retrieved, provider, tick=20, tier=1)

    assert provider.last_prompt is not None
    user_content = provider.last_prompt.messages[0]["content"]
    assert "Another agent did 'betray' to me at tick 10." in user_content


@pytest.mark.asyncio
async def test_decide_surfaces_relationship_context_for_visible_agents():
    provider = _CapturingProvider('{"action": "idle", "targets": [], "params": {}, "reasoning": "x"}')
    observation = Observation(tick=20, agent_id=AGENT_ID, zone="room", visible_agents=[OTHER_ID])
    a_id, b_id = sorted([AGENT_ID, OTHER_ID], key=str)  # RelationshipEdge requires agent_a_id < agent_b_id
    edge = RelationshipEdge(
        id=uuid.uuid4(), world_id=uuid.uuid4(), agent_a_id=a_id, agent_b_id=b_id,
        trust=0.62, bond_state=BondState.FRIEND, last_contact_tick=5, created_tick=0,
    )

    await DecisionEngine.decide(
        _agent(), _bundle(), observation, [], provider, tick=20, tier=1,
        relationships={OTHER_ID: edge},
    )

    user_content = provider.last_prompt.messages[0]["content"]  # type: ignore[union-attr]
    assert f"{OTHER_ID} (friend, trust 0.62)" in user_content


@pytest.mark.asyncio
async def test_decide_notes_no_history_for_a_visible_agent_with_no_edge():
    provider = _CapturingProvider('{"action": "idle", "targets": [], "params": {}, "reasoning": "x"}')
    observation = Observation(tick=20, agent_id=AGENT_ID, zone="room", visible_agents=[OTHER_ID])

    await DecisionEngine.decide(_agent(), _bundle(), observation, [], provider, tick=20, tier=1)

    user_content = provider.last_prompt.messages[0]["content"]  # type: ignore[union-attr]
    assert f"{OTHER_ID} (no relationship history yet)" in user_content


@pytest.mark.asyncio
async def test_decide_nudges_toward_the_least_contacted_visible_agent():
    """Regression test for the M4 real trial's hub finding: once one
    relationship pulls ahead, the trust/bond_state framing alone gives the
    model no reason to ever reach out to whoever it's barely spoken to —
    `_relationship_context_summary` must actively flag whichever visible
    agent has the lowest `contact_count`."""
    provider = _CapturingProvider('{"action": "idle", "targets": [], "params": {}, "reasoning": "x"}')
    observation = Observation(
        tick=20, agent_id=AGENT_ID, zone="room", visible_agents=[OTHER_ID, THIRD_ID]
    )
    a1, b1 = sorted([AGENT_ID, OTHER_ID], key=str)
    a2, b2 = sorted([AGENT_ID, THIRD_ID], key=str)
    favoured = RelationshipEdge(
        id=uuid.uuid4(), world_id=uuid.uuid4(), agent_a_id=a1, agent_b_id=b1,
        trust=1.0, bond_state=BondState.CLOSE_BOND, contact_count=500, last_contact_tick=19, created_tick=0,
    )
    neglected = RelationshipEdge(
        id=uuid.uuid4(), world_id=uuid.uuid4(), agent_a_id=a2, agent_b_id=b2,
        trust=-1.0, bond_state=BondState.ACQUAINTANCE, contact_count=3, last_contact_tick=1, created_tick=0,
    )

    await DecisionEngine.decide(
        _agent(), _bundle(), observation, [], provider, tick=20, tier=1,
        relationships={OTHER_ID: favoured, THIRD_ID: neglected},
    )

    user_content = provider.last_prompt.messages[0]["content"]  # type: ignore[union-attr]
    assert f"{THIRD_ID} (acquaintance, trust -1.00) — you interact with them far less" in user_content
    assert "you interact with them far less" not in user_content.split(str(THIRD_ID))[0]  # not on OTHER_ID


@pytest.mark.asyncio
async def test_decide_does_not_nudge_when_contact_counts_are_even():
    provider = _CapturingProvider('{"action": "idle", "targets": [], "params": {}, "reasoning": "x"}')
    observation = Observation(
        tick=20, agent_id=AGENT_ID, zone="room", visible_agents=[OTHER_ID, THIRD_ID]
    )
    a1, b1 = sorted([AGENT_ID, OTHER_ID], key=str)
    a2, b2 = sorted([AGENT_ID, THIRD_ID], key=str)
    edge1 = RelationshipEdge(
        id=uuid.uuid4(), world_id=uuid.uuid4(), agent_a_id=a1, agent_b_id=b1,
        trust=0.1, bond_state=BondState.ACQUAINTANCE, contact_count=5, last_contact_tick=19, created_tick=0,
    )
    edge2 = RelationshipEdge(
        id=uuid.uuid4(), world_id=uuid.uuid4(), agent_a_id=a2, agent_b_id=b2,
        trust=0.1, bond_state=BondState.ACQUAINTANCE, contact_count=5, last_contact_tick=19, created_tick=0,
    )

    await DecisionEngine.decide(
        _agent(), _bundle(), observation, [], provider, tick=20, tier=1,
        relationships={OTHER_ID: edge1, THIRD_ID: edge2},
    )

    user_content = provider.last_prompt.messages[0]["content"]  # type: ignore[union-attr]
    assert "you interact with them far less" not in user_content


@pytest.mark.asyncio
async def test_decide_omits_the_memory_section_when_nothing_was_retrieved():
    provider = _CapturingProvider('{"action": "idle", "targets": [], "params": {}, "reasoning": "x"}')
    observation = Observation(tick=20, agent_id=AGENT_ID, zone="room", visible_agents=[])

    await DecisionEngine.decide(_agent(), _bundle(), observation, [], provider, tick=20, tier=1)

    assert provider.last_prompt is not None
    assert "What you remember" not in provider.last_prompt.messages[0]["content"]
