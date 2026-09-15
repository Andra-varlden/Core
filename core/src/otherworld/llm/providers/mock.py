"""A deterministic, no-network mock provider.

Used by simulation tests (About/plan.md §11.2 — "no live calls in CI") and
by anything exercising the tick loop before real cassettes exist. Output is a
pure function of the prompt content, so repeated runs are byte-identical —
required for the determinism tests (T2.2, T3.2, T5.2).
"""

from __future__ import annotations

import hashlib

from otherworld.llm.protocol import Completion, Prompt


def _seeded_float(seed_text: str, salt: str) -> float:
    digest = hashlib.sha256(f"{salt}:{seed_text}".encode()).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


class MockLLMProvider:
    """Deterministic stand-in for a real `LLMProvider`. No network access."""

    async def tier1(self, prompt: Prompt) -> Completion:
        return self._respond(prompt, model="mock-tier1")

    async def tier2(self, prompt: Prompt) -> Completion:
        return self._respond(prompt, model="mock-tier2")

    async def embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in digest] * 12  # 32 * 12 = 384-d deterministic vector

    def _respond(self, prompt: Prompt, model: str) -> Completion:
        joined = prompt.system + "".join(m.get("content", "") for m in prompt.messages)
        digest = hashlib.sha256(joined.encode()).hexdigest()[:8]
        return Completion(
            text=f'{{"action": "idle", "targets": [], "reasoning": "mock-{digest}"}}',
            input_tokens=len(joined) // 4,
            output_tokens=16,
            model=model,
        )
