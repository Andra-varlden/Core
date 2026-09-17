"""Defensive JSON extraction from LLM completions.

Real models routinely ignore a "no markdown fences" instruction and wrap
the JSON in ```json ... ``` anyway, or add a sentence before/after it
(observed live during M4's Groq pilot runs). Shared by `runtime/decision.py`
(action proposals) and `runtime/reflection.py` (belief synthesis) — both
parse a single JSON object out of an otherwise-untrusted completion.
"""

from __future__ import annotations


def extract_json_object(text: str) -> str:
    """Try the raw text first; if that fails, fall back to the first
    {...} span."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:]
        stripped = stripped.strip()
    start, end = stripped.find("{"), stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return stripped[start : end + 1]
    return stripped
