"""Groq LLM provider. See About/architecture.md §12, About/spec.md §15.3.

Tier 1 = `openai/gpt-oss-20b` (cheap, ~1000 tok/s — the high-volume tier).
Tier 2 = `openai/gpt-oss-120b` (better reasoning, ~500 tok/s — used only on
escalation triggers, About/architecture.md §12's list). Both hosted on
GroqCloud; model choice and current pricing recorded in About/spec.md §15.3.

Groq has no embeddings endpoint, so `embed()` falls back to the
deterministic mock hash (llm/providers/mock.py) until a real embedding
provider is chosen — tracked separately in About/README.md's open items,
since it doesn't block decision-variance the way Tier 1/2 completions do.
"""

from __future__ import annotations

import asyncio
import random
from typing import Literal, cast

from groq import AsyncGroq, RateLimitError
from groq.types.chat import ChatCompletion, ChatCompletionMessageParam

from otherworld.llm.protocol import Completion, Prompt
from otherworld.llm.providers.mock import MockLLMProvider

TIER1_MODEL = "openai/gpt-oss-120b"  # see the 2026-09-18 note below for why
TIER2_MODEL = "openai/gpt-oss-120b"
_APP_LEVEL_MAX_RETRIES = 6
_APP_LEVEL_MAX_BACKOFF_SECONDS = 20.0

# Both gpt-oss models are reasoning models: they spend a separate budget of
# "reasoning tokens" (in `message.reasoning`, not `content`) before ever
# producing the final answer — confirmed live: a 512-token budget was
# consumed entirely by 301 reasoning tokens on a trivial decision, leaving
# an empty `content` and a rejected completion. Capping effort keeps a
# high-volume Tier 1 tick cheap (About/context.md principle 7, "every tick
# costs money") and keeps `content` from being truncated away entirely.
#
# Tier 1 moved from 20b to 120b, and "low" effort to "medium" (2026-09-18).
# A real 5-person, 1008-tick M4 trial at 20b/"low" produced *zero* variety
# past sleep/idle/greet/form_goal for all 5 agents all week — Orion alone
# re-greeted 321 times — leaving too few importance>=0.3 events (spec.md
# §14 step 1) to even run the Recognition Metric. Three prompt-side fixes
# were tried and each produced the exact same pattern with no change at
# all: raising 20b's reasoning effort to "medium"; surfacing retrieved
# memory content in the prompt (previously computed and silently dropped —
# a real, separate bug, fixed regardless); and adding per-agent relationship
# context (bond state, trust — previously visible agents were opaque UUIDs
# with no social stakes attached). Isolated the real cause with a direct
# side-by-side test: identical prompt, identical real persona, only the
# model swapped — 20b stayed on greet/idle every time, 120b produced
# compliment/confide/form_goal/speak_to with real contextual reasoning
# ("close bond trust 0.81, i give a compliment") 10/10 tries. This was
# never a prompt problem — 20b isn't capable of using rich context for
# open-ended social choices, regardless of what it's given. Real inference
# cost stays trivial either way (About/plan.md M4's whole week ran under
# $1 on 20b; 120b is ~2x the per-token rate), so paying that for actually
# getting emergent behavior — the entire point of this trial — is an easy
# trade. This makes Tier 1 and Tier 2 functionally identical for now; the
# tiering split still exists in code (`TIER1_MODEL`/`TIER2_MODEL` as
# separate constants) so it's a one-line revert if a cheaper Tier 1 model
# is worth retrying later.
ReasoningEffort = Literal["none", "default", "low", "medium", "high"]
TIER1_REASONING_EFFORT: ReasoningEffort = "medium"
TIER2_REASONING_EFFORT: ReasoningEffort = "medium"


class GroqLLMProvider:
    """A real `LLMProvider`. `otherworld.llm.factory` always passes an
    explicit key from `otherworld.config.settings.groq_api_key` (loaded
    from `.env`, not the raw process environment); a caller that omits
    `api_key` falls back to the SDK's own convention of reading
    `GROQ_API_KEY` directly from `os.environ`.
    """

    def __init__(self, api_key: str | None = None) -> None:
        # The free/on-demand tier's tokens-per-minute limit is low enough
        # (confirmed by hitting it in a real M4 pilot run — 8000 TPM on
        # openai/gpt-oss-20b) that the SDK's default max_retries=2 isn't
        # always enough to ride out a per-minute window; the SDK already
        # backs off and respects Retry-After on 429s, it just needs more
        # attempts budgeted.
        self._client = AsyncGroq(api_key=api_key, max_retries=5) if api_key else AsyncGroq(max_retries=5)
        self._embed_fallback = MockLLMProvider()
        # Concurrency, not just volume, defeats the SDK's own retries: About/
        # plan.md's M4 real 5-agent run confirmed all 5 agents' decisions
        # fire in the same instant every tick (`runtime/scheduler.py`'s
        # `asyncio.gather`), so once usage is near the TPM ceiling, all 5
        # requests can land in the same rejected burst — and if their
        # retries land in the same synchronized burst again, the SDK's
        # 5-attempt budget gets burned in lockstep without the shared
        # window ever actually clearing. This app-level retry adds a random
        # jitter specifically to break that synchrony, on top of (not
        # instead of) the SDK's own retry budget above.
        self._rng = random.Random()

    async def tier1(self, prompt: Prompt) -> Completion:
        return await self._complete(prompt, TIER1_MODEL, TIER1_REASONING_EFFORT)

    async def tier2(self, prompt: Prompt) -> Completion:
        return await self._complete(prompt, TIER2_MODEL, TIER2_REASONING_EFFORT)

    async def _complete(self, prompt: Prompt, model: str, reasoning_effort: ReasoningEffort) -> Completion:
        # Our Prompt.messages is the provider-agnostic {"role", "content"}
        # shape (llm/protocol.py); Groq's SDK wants its own discriminated
        # TypedDict union. The cast is honest about that boundary rather
        # than widening our own protocol's type to match one vendor's SDK.
        messages = cast(
            list[ChatCompletionMessageParam],
            [{"role": "system", "content": prompt.system}, *prompt.messages],
        )
        response = await self._create_with_retry(model, messages, prompt, reasoning_effort)
        choice = response.choices[0]
        usage = response.usage
        return Completion(
            text=choice.message.content or "",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            model=model,
        )

    async def _create_with_retry(
        self,
        model: str,
        messages: list[ChatCompletionMessageParam],
        prompt: Prompt,
        reasoning_effort: ReasoningEffort,
    ) -> ChatCompletion:
        for attempt in range(_APP_LEVEL_MAX_RETRIES):
            try:
                return await self._client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=prompt.max_tokens,
                    temperature=prompt.temperature,
                    reasoning_effort=reasoning_effort,
                )
            except RateLimitError:
                if attempt == _APP_LEVEL_MAX_RETRIES - 1:
                    raise
                # Jitter (not just exponential backoff) specifically to
                # de-synchronise concurrent agents that all got rejected in
                # the same instant — see __init__'s docstring comment.
                backoff = min(2**attempt, _APP_LEVEL_MAX_BACKOFF_SECONDS)
                await asyncio.sleep(self._rng.uniform(0.0, backoff))
        raise AssertionError("unreachable: loop always returns or raises")

    async def embed(self, text: str) -> list[float]:
        return await self._embed_fallback.embed(text)
