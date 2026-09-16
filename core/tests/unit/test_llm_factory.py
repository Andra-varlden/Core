"""otherworld.llm.factory picks a real provider only when one is configured."""

from __future__ import annotations

from otherworld.config import settings
from otherworld.llm.factory import get_default_provider
from otherworld.llm.providers.groq import GroqLLMProvider
from otherworld.llm.providers.mock import MockLLMProvider


def test_falls_back_to_mock_when_no_key_configured(monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", None)
    assert isinstance(get_default_provider(), MockLLMProvider)


def test_picks_groq_when_key_configured(monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "test-key")
    assert isinstance(get_default_provider(), GroqLLMProvider)
