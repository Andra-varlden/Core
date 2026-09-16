"""Pick a real provider if one is configured, else the deterministic mock.

The only place besides tests that should construct a concrete
`LLMProvider` — callers (CLIs, later the API) ask for "the provider",
not for a specific vendor class.
"""

from __future__ import annotations

from otherworld.config import settings
from otherworld.llm.protocol import LLMProvider


def get_default_provider() -> LLMProvider:
    if settings.groq_api_key:
        from otherworld.llm.providers.groq import GroqLLMProvider

        return GroqLLMProvider(api_key=settings.groq_api_key)

    from otherworld.llm.providers.mock import MockLLMProvider

    return MockLLMProvider()
