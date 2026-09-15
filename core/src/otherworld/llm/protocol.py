"""The LLM provider abstraction. See About/architecture.md §12.

Rule: no module outside `otherworld.llm` may import a vendor SDK. Everything
goes through this protocol, so swapping a model is a config change, never a
code change. Tier 0 never touches this interface — it is pure Python rules.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel


class Prompt(BaseModel):
    system: str
    messages: list[dict[str, str]]
    max_tokens: int = 512
    temperature: float = 0.7


class Completion(BaseModel):
    text: str
    input_tokens: int
    output_tokens: int
    model: str


class LLMProvider(Protocol):
    async def tier1(self, prompt: Prompt) -> Completion: ...
    async def tier2(self, prompt: Prompt) -> Completion: ...
    async def embed(self, text: str) -> list[float]: ...
