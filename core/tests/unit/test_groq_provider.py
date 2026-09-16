"""GroqLLMProvider's request/response translation, with the SDK mocked out.

No live network calls here — About/plan.md §11.2 forbids that in CI. This
only checks that our wrapper builds the right request shape and parses a
Groq-shaped response correctly; it cannot and does not prove the real API
behaves as expected (that needs a manually-triggered live check, same as
any other vendor integration).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from otherworld.llm.protocol import Prompt
from otherworld.llm.providers.groq import TIER1_MODEL, TIER2_MODEL, GroqLLMProvider


def _fake_response(text: str, prompt_tokens: int, completion_tokens: int) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


@pytest.mark.asyncio
async def test_tier1_sends_system_and_user_messages_and_parses_usage():
    provider = GroqLLMProvider(api_key="test-key")
    provider._client.chat.completions.create = AsyncMock(
        return_value=_fake_response('{"action": "idle"}', prompt_tokens=42, completion_tokens=7)
    )

    prompt = Prompt(system="You are Nyx.", messages=[{"role": "user", "content": "Tick 5."}])
    completion = await provider.tier1(prompt)

    assert completion.text == '{"action": "idle"}'
    assert completion.input_tokens == 42
    assert completion.output_tokens == 7
    assert completion.model == TIER1_MODEL

    call_kwargs = provider._client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == TIER1_MODEL
    assert call_kwargs["messages"][0] == {"role": "system", "content": "You are Nyx."}
    assert call_kwargs["messages"][1] == {"role": "user", "content": "Tick 5."}


@pytest.mark.asyncio
async def test_tier2_uses_the_larger_model():
    provider = GroqLLMProvider(api_key="test-key")
    provider._client.chat.completions.create = AsyncMock(
        return_value=_fake_response('{"action": "greet"}', prompt_tokens=10, completion_tokens=5)
    )

    prompt = Prompt(system="sys", messages=[{"role": "user", "content": "hi"}])
    completion = await provider.tier2(prompt)

    assert completion.model == TIER2_MODEL
    assert provider._client.chat.completions.create.call_args.kwargs["model"] == TIER2_MODEL


@pytest.mark.asyncio
async def test_missing_usage_does_not_crash():
    provider = GroqLLMProvider(api_key="test-key")
    provider._client.chat.completions.create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))], usage=None
        )
    )
    completion = await provider.tier1(Prompt(system="s", messages=[]))
    assert completion.input_tokens == 0
    assert completion.output_tokens == 0


@pytest.mark.asyncio
async def test_embed_falls_back_to_deterministic_mock():
    provider = GroqLLMProvider(api_key="test-key")
    v1 = await provider.embed("hello")
    v2 = await provider.embed("hello")
    assert v1 == v2  # deterministic
    assert len(v1) > 0
