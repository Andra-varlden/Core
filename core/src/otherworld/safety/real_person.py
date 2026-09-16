"""Real-person protection (Validator filter 3). See About/architecture.md §5,
About/spec.md §11.2.

The highest-severity filter: it is the mechanism by which the product could
cause real-world harm to someone who never consented to be here. Detection
here is the same capitalised-token heuristic used for writing-sample
redaction (persona/capture/writing.py) — a stand-in for real named-entity
recognition, not a substitute for it before real-world exposure (M7).
"""

from __future__ import annotations

from otherworld.models.events import ProposedAction
from otherworld.persona.capture.writing import REDACTION_TOKEN, redact_names


class RealPersonGuard:
    @staticmethod
    def evaluate(action: ProposedAction, agent_display_name: str) -> bool:
        """True if `action` names no one but the agent's own owner-facing
        display name.
        """
        utterance = str(action.params.get("utterance", ""))
        if not utterance:
            return True
        # The agent's own display name is not a real-person violation.
        sanitized = utterance.replace(agent_display_name, "")
        return REDACTION_TOKEN not in redact_names(sanitized)
