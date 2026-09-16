"""Method C — writing-sample ingestion. See About/spec.md §2.4.

Extracts *only* the voice profile — never the values layer (inferring
someone's loyalty from their group chat is unreliable and invasive, per the
spec). Third-party names are redacted at ingestion, before any other
processing, per the same section: "Names of other people in pasted logs are
redacted at ingestion, not at use."

Redaction here is a capitalised-token heuristic, not a real NER model — a
reasonable stand-in for this stage, but it should be swapped for a proper
named-entity recognizer before this method is exposed to real user data at
Phase 2 (About/plan.md M6+).
"""

from __future__ import annotations

import re

from otherworld.persona.scoring import clamp01

MIN_WORD_COUNT = 500  # [TUNE]
REDACTION_TOKEN = "[REDACTED]"

# Common capitalised words that are not names: pronouns, determiners,
# connectives, days, months, and the like — the words that legitimately
# start an English sentence. A name that always happens to open a sentence
# is exactly the case a "skip sentence-initial words" rule would miss, so
# this stoplist is the only exemption; it is necessarily incomplete, which
# is why this whole module is a stand-in for a real NER model (see the
# module docstring).
_NOT_NAMES = {
    "I", "We", "They", "He", "She", "It", "You", "This", "That", "These", "Those",
    "The", "A", "An", "And", "But", "So", "If", "Well",
    "Later", "Then", "Now", "Today", "Tomorrow", "Yesterday", "Meanwhile",
    "However", "Also", "Because", "When", "While", "Since", "Once",
    "Where", "Why", "How", "What", "Who",
    "Still", "Suddenly", "Finally", "Eventually", "Sometimes", "Usually", "Often",
    "Perhaps", "Maybe", "Actually", "Honestly", "Certainly", "Clearly", "Overall",
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December",
}

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_WORD_RE = re.compile(r"\b[A-Z][a-z]+\b")

_PROFANITY_WORDS = {"damn", "hell", "shit", "fuck", "crap", "ass"}


def redact_names(text: str) -> str:
    """Replace capitalised tokens that are not common English words with a
    redaction marker. Deliberately does NOT exempt sentence-initial words —
    a name that always happens to open a sentence would otherwise slip
    through every time. Errs toward over-redacting: a false positive costs
    a little voice signal, a false negative leaks a real person's name
    (ADR-007's concern extended to pasted logs).
    """
    words = text.split()
    out = []
    for word in words:
        core = re.match(r"[A-Za-z]+", word)
        if core and _WORD_RE.fullmatch(core.group(0)) and core.group(0) not in _NOT_NAMES:
            out.append(word.replace(core.group(0), REDACTION_TOKEN))
        else:
            out.append(word)
    return " ".join(out)


def extract_voice_profile(text: str) -> dict[str, object]:
    """text should already be redacted (see `redact_names`). Returns kwargs
    for `VoiceProfile`.
    """
    words = text.split()
    word_count = len(words) or 1

    sentences = [s for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    avg_sentence_len = word_count / max(1, len(sentences))
    verbosity = clamp01(avg_sentence_len / 25.0)

    contractions = len(re.findall(r"\b\w+'\w+\b", text))
    formality = clamp01(1.0 - (contractions / word_count) * 15)

    profanity_hits = sum(1 for w in words if w.strip(".,!?").lower() in _PROFANITY_WORDS)
    profanity_baseline = clamp01((profanity_hits / word_count) * 30)

    humour_style = "none"
    lowered = text.lower()
    for style in ("dry", "sarcastic", "absurd", "warm"):
        if style in lowered:
            humour_style = style
            break

    return {
        "verbosity": verbosity,
        "formality": formality,
        "humour_style": humour_style,
        "profanity_baseline": profanity_baseline,
    }


def ingest_writing_sample(raw_text: str) -> tuple[dict[str, object], str]:
    """Full Method C pipeline: redact, then extract voice only.

    Returns (voice_kwargs, redacted_text). Raises ValueError if the sample
    is shorter than MIN_WORD_COUNT — the spec's stated floor for a usable
    signal.
    """
    if len(raw_text.split()) < MIN_WORD_COUNT:
        raise ValueError(
            f"writing sample has fewer than {MIN_WORD_COUNT} words; "
            "About/spec.md §2.4 requires a longer sample for a usable signal"
        )
    redacted = redact_names(raw_text)
    return extract_voice_profile(redacted), redacted
