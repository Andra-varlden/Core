"""T1.5 — About/plan.md M1 acceptance test, method C name redaction."""

from otherworld.persona.capture.writing import ingest_writing_sample, redact_names

_PARAGRAPH = (
    "John gave me a ride to the market and Sarah helped me carry the boxes "
    "up the stairs. Later Priya called to check in, which I always appreciate. "
)


def test_names_are_redacted_before_processing():
    sample = _PARAGRAPH * 40  # comfortably over the 500-word floor
    voice_kwargs, redacted = ingest_writing_sample(sample)

    assert "John" not in redacted
    assert "Sarah" not in redacted
    assert "Priya" not in redacted
    assert "[REDACTED]" in redacted
    assert isinstance(voice_kwargs["verbosity"], float)


def test_short_sample_is_rejected():
    import pytest

    with pytest.raises(ValueError):
        ingest_writing_sample("Too short.")


def test_sentence_initial_capitals_are_not_treated_as_names():
    text = "Monday was a long day. I went home early."
    redacted = redact_names(text)
    assert "Monday" in redacted
    assert "[REDACTED]" not in redacted
