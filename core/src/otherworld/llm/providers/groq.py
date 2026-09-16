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

from typing import Literal, cast

from groq import AsyncGroq
from groq.types.chat import ChatCompletionMessageParam

from otherworld.llm.protocol import Completion, Prompt
from otherworld.llm.providers.mock import MockLLMProvider

TIER1_MODEL = "openai/gpt-oss-20b"
TIER2_MODEL = "openai/gpt-oss-120b"

# Both gpt-oss models are reasoning models: they spend a separate budget of
# "reasoning tokens" (in `message.reasoning`, not `content`) before ever
# producing the final answer — confirmed live: a 512-token budget was
# consumed entirely by 301 reasoning tokens on a trivial decision, leaving
# an empty `content` and a rejected completion. Capping effort keeps a
# high-volume Tier 1 tick cheap (About/context.md principle 7, "every tick
# costs money") and keeps `content` from being truncated away entirely.
ReasoningEffort = Literal["none", "default", "low", "medium", "high"]
TIER1_REASONING_EFFORT: ReasoningEffort = "low"
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
        response = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=prompt.max_tokens,
            temperature=prompt.temperature,
            reasoning_effort=reasoning_effort,
        )
        choice = response.choices[0]
        usage = response.usage
        return Completion(
            text=choice.message.content or "",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            model=model,
        )

    async def embed(self, text: str) -> list[float]:
        return await self._embed_fallback.embed(text)
