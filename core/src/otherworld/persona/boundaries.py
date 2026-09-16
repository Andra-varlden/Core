"""The boundary layer. See About/spec.md §2.6.

Boundary capture is separate, explicit, and never mixed with personality
capture (About/context.md principle 5, ADR-007's spirit extended to
boundaries). A `BoundaryRule.predicate` is a tiny compiled matcher expression,
evaluated by the Safety plane's Validator filter 1 in About/architecture.md
§5. The grammar is intentionally minimal for M1:

    category == "<value>"
    action == "<value>"
    contains(utterance, "<value>")

Real-world evaluation context is a `PredicateContext`. A malformed predicate
is a bug in this module, not a runtime input, so `compile_boundary` is the
only place new predicate shapes get added.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from otherworld.models.persona import BoundaryRule, BoundarySeverity

_PREDICATE_RE = re.compile(
    r'^(?P<kind>category|action)\s*==\s*"(?P<value>[^"]+)"$|'
    r'^contains\((?P<field>utterance)\s*,\s*"(?P<needle>[^"]+)"\)$'
)


@dataclass(frozen=True)
class PredicateContext:
    category: str | None = None
    action: str | None = None
    utterance: str = ""


# The default toggles offered at capture time (spec.md §2.6).
DEFAULT_BOUNDARY_TOGGLES: dict[str, tuple[str, str]] = {
    "no_romance": ("no romance or intimacy", 'category == "romance"'),
    "no_profanity": ("no profanity", 'category == "profanity"'),
    "no_real_occupation": (
        "no discussion of the owner's real occupation or location",
        'category == "real_identity"',
    ),
    "no_violence": ("no violence", 'category == "violence"'),
    "no_theft": ("no theft", 'action == "take"'),
    "no_advocacy": (
        "no religious or political advocacy",
        'category == "advocacy"',
    ),
}


def default_boundaries(enabled: set[str] | None = None) -> list[BoundaryRule]:
    """Boundary rules for the toggles the owner turned on.

    Phase 1-2 default per spec.md §2.6: romance/intimacy and violence are
    blocked platform-wide regardless of owner choice (see also §11.1), so
    those two are always included.
    """
    enabled = enabled or set()
    always_on = {"no_romance", "no_violence"}
    rules = []
    for key in always_on | enabled:
        description, predicate = DEFAULT_BOUNDARY_TOGGLES[key]
        rules.append(
            BoundaryRule(id=uuid.uuid4(), description=description, predicate=predicate, severity="block")
        )
    return rules


def compile_free_text_boundary(text: str, severity: BoundarySeverity = "block_and_notify") -> BoundaryRule:
    """Compile a free-text "never do this" answer (spec.md item A29) into a
    keyword-matching predicate against the utterance an agent is about to say.
    """
    keyword = text.strip().strip(".").lower()
    return BoundaryRule(
        id=uuid.uuid4(),
        description=text.strip(),
        predicate=f'contains(utterance, "{keyword}")',
        severity=severity,
    )


def evaluate_boundary(rule: BoundaryRule, context: PredicateContext) -> bool:
    """True if the context violates the boundary (i.e. the action should be blocked)."""
    match = _PREDICATE_RE.match(rule.predicate)
    if not match:
        raise ValueError(f"unrecognised boundary predicate: {rule.predicate!r}")

    if match.group("kind") == "category":
        return context.category == match.group("value")
    if match.group("kind") == "action":
        return context.action == match.group("value")

    needle = match.group("needle")
    return needle.lower() in context.utterance.lower()
