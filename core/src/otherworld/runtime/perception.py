"""Perception. See About/architecture.md §4.

M2's world has no tile map yet (ADR-008: the tile world is built last) —
agents share a single abstract room. `Observation` here is deliberately
thin; it grows real spatial content (perception_radius, zones, features) at
M3/M5 without changing this module's contract: `observe()` is still the
sole perception entry point (invariant I4).
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from otherworld.models.agent import Agent


class AddressedSpeech(BaseModel):
    from_agent_id: uuid.UUID
    utterance: str


class Observation(BaseModel):
    tick: int
    agent_id: uuid.UUID
    zone: str = "room"
    visible_agents: list[uuid.UUID] = Field(default_factory=list)
    addressed_speech: list[AddressedSpeech] = Field(default_factory=list)


class PerceptionService:
    @staticmethod
    def observe(agent: Agent, tick: int, other_agents_present: list[uuid.UUID] | None = None) -> Observation:
        return Observation(
            tick=tick,
            agent_id=agent.id,
            visible_agents=list(other_agents_present or []),
            addressed_speech=[],
        )
