"""T2.10 — About/plan.md M2 acceptance test: no wall-clock time in runtime/
decision paths (About/architecture.md §13's determinism requirement).
"""

from __future__ import annotations

import re
from pathlib import Path

RUNTIME_ROOT = Path(__file__).resolve().parents[2] / "src" / "otherworld" / "runtime"

_WALL_CLOCK_RE = re.compile(r"datetime\.now\(|time\.time\(\)")


def test_no_wall_clock_calls_in_runtime_package():
    violations: list[str] = []
    for path in RUNTIME_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for match in _WALL_CLOCK_RE.finditer(text):
            violations.append(f"{path.relative_to(RUNTIME_ROOT)}: {match.group(0)}")
    assert not violations, f"wall-clock call found in otherworld.runtime: {violations}"
