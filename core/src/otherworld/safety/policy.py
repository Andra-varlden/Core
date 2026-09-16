"""Platform policy filter (Validator filter 2). See About/spec.md §11.1.

A minimal keyword-based stand-in for the classifier-backed policy engine
that M7 ("Safety and moderation for real", About/plan.md) builds out. Good
enough to prove the filter pipeline and its ordering now; not a substitute
for the real thing before any real-world exposure.
"""

from __future__ import annotations

from otherworld.models.events import ProposedAction

# [TUNE] Absolute prohibitions per spec.md §11.1 that a keyword check can
# catch at all. Real coverage (hate speech, harassment, self-harm, etc.)
# needs a classifier — this list is not that.
_BLOCKED_SUBSTRINGS = (
    "kill yourself",
    "commit suicide",
)


class PolicyEngine:
    @staticmethod
    def evaluate(action: ProposedAction) -> bool:
        """True if `action` is allowed (no policy violation found)."""
        utterance = str(action.params.get("utterance", "")).lower()
        return not any(phrase in utterance for phrase in _BLOCKED_SUBSTRINGS)
