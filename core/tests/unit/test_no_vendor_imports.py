"""T0.8 — grep test: no vendor SDK import outside core/llm/.

About/architecture.md §12: "no module outside otherworld.llm may import a
vendor SDK. Everything goes through the protocol."
"""

from __future__ import annotations

import re
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "otherworld"

# Add real vendor SDK package names here as they are introduced.
VENDOR_SDK_MODULES = ("openai", "anthropic", "google.generativeai", "cohere")

IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+([\w.]+)", re.MULTILINE)


def test_no_vendor_sdk_import_outside_llm_package():
    violations: list[str] = []
    for path in SRC_ROOT.rglob("*.py"):
        rel = path.relative_to(SRC_ROOT)
        if rel.parts[0] == "llm":
            continue
        text = path.read_text(encoding="utf-8")
        for match in IMPORT_RE.finditer(text):
            module = match.group(1)
            if any(module == vendor or module.startswith(vendor + ".") for vendor in VENDOR_SDK_MODULES):
                violations.append(f"{rel}: {module}")
    assert not violations, f"vendor SDK imported outside otherworld.llm: {violations}"
