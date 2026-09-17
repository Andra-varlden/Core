"""A deterministic, no-network mock provider.

Used by simulation tests (About/plan.md §11.2 — "no live calls in CI") and
by anything exercising the tick loop before real cassettes exist. Output is a
pure function of the prompt content, so repeated runs are byte-identical —
required for the determinism tests (T2.2, T3.2, T5.2).
"""

from __future__ import annotations

import hashlib
import json
import re

from otherworld.llm.protocol import Completion, Prompt
from otherworld.models.memory import EMBEDDING_DIM

_UNMET_AGENTS_RE = re.compile(r"never interacted with before: \[([^\]]*)\]")
_REFLECTION_MARKER = "Memories since your last reflection"
_SUBJECTS_RE = re.compile(r"\[subjects: ([^\]]*)\]")


class MockLLMProvider:
    """Deterministic stand-in for a real `LLMProvider`. No network access."""

    async def tier1(self, prompt: Prompt) -> Completion:
        return self._respond(prompt, model="mock-tier1")

    async def tier2(self, prompt: Prompt) -> Completion:
        return self._respond(prompt, model="mock-tier2")

    async def embed(self, text: str) -> list[float]:
        # Must match memory_records.embedding's fixed pgvector dimension
        # (EMBEDDING_DIM) exactly, or inserts fail with a dimension mismatch.
        values: list[float] = []
        block = text.encode()
        while len(values) < EMBEDDING_DIM:
            digest = hashlib.sha256(block).digest()
            values.extend(b / 255.0 for b in digest)
            block = digest
        return values[:EMBEDDING_DIM]

    def _respond(self, prompt: Prompt, model: str) -> Completion:
        joined = prompt.system + "".join(m.get("content", "") for m in prompt.messages)
        digest = hashlib.sha256(joined.encode()).hexdigest()[:8]

        # `runtime/reflection.py` sends a belief-shaped prompt, not an
        # action-shaped one — exercising real belief creation in simulation
        # tests (T5.9) needs a deterministic response here too, not just an
        # empty completion that `_parse_beliefs` quietly discards.
        if _REFLECTION_MARKER in joined:
            subject_match = _SUBJECTS_RE.search(joined)
            about_agent_id = subject_match.group(1).split(",")[0].strip() if subject_match else None
            belief = {
                "text": f"mock-{digest}: I've been noticing a pattern lately.",
                "about_agent_id": about_agent_id,
                # Deterministic sign from the digest, so some mock beliefs
                # exercise gossip's pile-on path (About/spec.md §8.2 needs a
                # *negative* inherited belief) without every belief being one.
                "valence": -0.6 if int(digest, 16) % 2 == 0 else 0.6,
            }
            belief_json = json.dumps({"beliefs": [belief]})
            return Completion(text=belief_json, input_tokens=len(joined) // 4, output_tokens=16, model=model)

        # A simple, deterministic default: greet someone you've never met.
        # A real Tier-2 model would very plausibly do this too; scripting it
        # here lets the tick loop exercise first-contact organically instead
        # of needing a bespoke fake provider for every simulation test.
        match = _UNMET_AGENTS_RE.search(joined)
        unmet_ids = [s.strip() for s in match.group(1).split(",") if s.strip()] if match else []
        if unmet_ids:
            action_json = json.dumps(
                {
                    "action": "greet",
                    "targets": [unmet_ids[0]],
                    "reasoning": f"mock-{digest}: greeting a stranger",
                }
            )
            return Completion(text=action_json, input_tokens=len(joined) // 4, output_tokens=16, model=model)

        return Completion(
            text=f'{{"action": "idle", "targets": [], "reasoning": "mock-{digest}"}}',
            input_tokens=len(joined) // 4,
            output_tokens=16,
            model=model,
        )
