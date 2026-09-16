"""Method A — structured questionnaire. See About/spec.md §2.2.

30 items, ~8 minutes. Items A1-A20 map to the trait vector; A21-A24 map to
the voice profile; A25-A30 are free-text and feed voice/boundary/self-concept
rather than the trait vector directly (A29 feeds the boundary layer, per
spec.md's own note on that item).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from otherworld.persona.scoring import TRAIT_NAMES, clamp01

# How strongly a fully-consistent set of answers pulls a trait away from the
# neutral 0.5 default. [TUNE] — see About/spec.md's own [TUNE] convention.
TRAIT_SCALE = 0.35


@dataclass(frozen=True)
class QuestionnaireItem:
    id: str
    prompt: str
    options: dict[str, str]
    effects: dict[str, dict[str, float]] = field(default_factory=dict)


TRAIT_ITEMS: tuple[QuestionnaireItem, ...] = (
    QuestionnaireItem(
        "A1", "A friend borrows something and doesn't return it. You:",
        {"a": "ask directly the same week", "b": "drop a hint",
         "c": "say nothing and let it bother you", "d": "genuinely forget about it"},
        {"a": {"conflict_directness": 1.0, "grudge_retention": -0.3},
         "b": {"conflict_directness": 0.0, "grudge_retention": 0.0},
         "c": {"conflict_directness": -1.0, "grudge_retention": 1.0},
         "d": {"conflict_directness": -0.3, "grudge_retention": -1.0}},
    ),
    QuestionnaireItem(
        "A2", "Someone criticises your work in front of others. You:",
        {"a": "defend it on the spot", "b": "go quiet, raise it later privately",
         "c": "agree to end the moment", "d": "counter-criticise"},
        {"a": {"conflict_directness": 1.0, "emotional_expressiveness": 0.5},
         "b": {"conflict_directness": 0.0, "emotional_expressiveness": -0.3},
         "c": {"conflict_directness": -1.0, "emotional_expressiveness": -0.5},
         "d": {"conflict_directness": 1.0, "emotional_expressiveness": 1.0}},
    ),
    QuestionnaireItem(
        "A3", "You're in an argument you're losing but still believe you're right. You:",
        {"a": "keep going", "b": "concede publicly, privately disagree",
         "c": "change the subject", "d": "genuinely reconsider"},
        {"a": {"independence": 1.0, "honesty": 0.5},
         "b": {"independence": -0.3, "honesty": -1.0},
         "c": {"independence": -0.5, "honesty": -0.5},
         "d": {"independence": -1.0, "honesty": 1.0}},
    ),
    QuestionnaireItem(
        "A4", "After a serious falling-out with a close friend, a year later they reach out. You:",
        {"a": "pick up where you left off", "b": "talk, but carefully",
         "c": "reply politely, keep distance", "d": "don't reply"},
        {"a": {"forgiveness": 1.0, "grudge_retention": -1.0},
         "b": {"forgiveness": 0.5, "grudge_retention": 0.0},
         "c": {"forgiveness": -0.3, "grudge_retention": 0.5},
         "d": {"forgiveness": -1.0, "grudge_retention": 1.0}},
    ),
    QuestionnaireItem(
        "A5", "Someone apologises but you don't think they mean it. You:",
        {"a": "accept anyway", "b": "say you don't believe them",
         "c": "accept outwardly, withdraw inwardly", "d": "ask them to explain"},
        {"a": {"forgiveness": 0.5, "honesty": -0.5, "conflict_directness": -0.5},
         "b": {"forgiveness": -0.3, "honesty": 1.0, "conflict_directness": 1.0},
         "c": {"forgiveness": -0.5, "honesty": -1.0, "conflict_directness": -1.0},
         "d": {"forgiveness": 0.0, "honesty": 0.5, "conflict_directness": 0.5}},
    ),
    QuestionnaireItem(
        "A6", "A friend tells you something in confidence that affects another friend. You:",
        {"a": "keep the confidence", "b": "tell the affected friend",
         "c": "push the first friend to tell them", "d": "depends entirely on severity"},
        {"a": {"loyalty": 1.0, "honesty": -0.5},
         "b": {"loyalty": -0.5, "honesty": 1.0},
         "c": {"loyalty": 0.3, "honesty": 0.5},
         "d": {"loyalty": 0.0, "honesty": 0.0}},
    ),
    QuestionnaireItem(
        "A7", "You're asked your honest opinion on something a friend made and you don't like it. You:",
        {"a": "say so plainly", "b": "find the good parts",
         "c": "soften it heavily", "d": "say you like it"},
        {"a": {"honesty": 1.0, "emotional_expressiveness": 0.5},
         "b": {"honesty": -0.3, "emotional_expressiveness": 0.0},
         "c": {"honesty": -0.7, "emotional_expressiveness": -0.3},
         "d": {"honesty": -1.0, "emotional_expressiveness": -0.5}},
    ),
    QuestionnaireItem(
        "A8", "A friend is clearly in the wrong in a dispute with a stranger. You:",
        {"a": "back your friend publicly", "b": "stay out of it",
         "c": "tell your friend privately they're wrong", "d": "side with whoever's right"},
        {"a": {"loyalty": 1.0, "honesty": -0.5},
         "b": {"loyalty": -0.3, "honesty": 0.0},
         "c": {"loyalty": 0.5, "honesty": 1.0},
         "d": {"loyalty": -1.0, "honesty": 1.0}},
    ),
    QuestionnaireItem(
        "A9", "You could get something you want by bending a rule nobody's checking. You:",
        {"a": "do it", "b": "do it if others do",
         "c": "don't", "d": "don't, and think less of those who do"},
        {"a": {"honesty": -1.0, "risk_tolerance": 0.5},
         "b": {"honesty": -0.5, "risk_tolerance": 0.0},
         "c": {"honesty": 0.7, "risk_tolerance": -0.3},
         "d": {"honesty": 1.0, "risk_tolerance": -0.5}},
    ),
    QuestionnaireItem(
        "A10", "At a gathering where you know one person, you:",
        {"a": "meet several new people", "b": "stay with the person you know",
         "c": "talk to one new person properly", "d": "leave early"},
        {"a": {"sociability": 1.0, "independence": -0.3},
         "b": {"sociability": -0.3, "independence": 0.0},
         "c": {"sociability": 0.5, "independence": 0.0},
         "d": {"sociability": -1.0, "independence": 0.3}},
    ),
    QuestionnaireItem(
        "A11", "A week with no contact from your closest friend. You:",
        {"a": "reach out immediately", "b": "wait for them",
         "c": "don't notice", "d": "notice and feel it, but say nothing"},
        {"a": {"sociability": 1.0, "emotional_expressiveness": 0.5},
         "b": {"sociability": -0.3, "emotional_expressiveness": -0.3},
         "c": {"sociability": -1.0, "emotional_expressiveness": -0.7},
         "d": {"sociability": 0.0, "emotional_expressiveness": -0.7}},
    ),
    QuestionnaireItem(
        "A12", "You prefer:",
        {"a": "a few deep friendships", "b": "a wide circle",
         "c": "mostly your own company", "d": "whoever is around"},
        {"a": {"sociability": 0.0, "independence": 0.3},
         "b": {"sociability": 1.0, "independence": -0.3},
         "c": {"sociability": -1.0, "independence": 1.0},
         "d": {"sociability": 0.5, "independence": -0.5}},
    ),
    QuestionnaireItem(
        "A13", "Someone new joins a group you're part of. You:",
        {"a": "bring them in actively", "b": "be friendly if they approach",
         "c": "carry on as normal", "d": "watch first"},
        {"a": {"sociability": 1.0, "curiosity": 0.5},
         "b": {"sociability": 0.0, "curiosity": 0.0},
         "c": {"sociability": -0.5, "curiosity": -0.5},
         "d": {"sociability": -0.3, "curiosity": 0.3}},
    ),
    QuestionnaireItem(
        "A14", "Given a free day and no obligations, you:",
        {"a": "start a project", "b": "rest",
         "c": "see people", "d": "explore somewhere new"},
        {"a": {"ambition": 1.0, "curiosity": 0.3},
         "b": {"ambition": -1.0, "curiosity": -0.3},
         "c": {"sociability": 1.0, "ambition": -0.2},
         "d": {"curiosity": 1.0, "ambition": 0.3}},
    ),
    QuestionnaireItem(
        "A15", "A group task has no leader. You:",
        {"a": "take charge", "b": "wait to see if anyone does",
         "c": "do your part quietly", "d": "suggest someone else lead"},
        {"a": {"ambition": 1.0, "independence": 0.5},
         "b": {"ambition": -0.5, "independence": -0.3},
         "c": {"ambition": -0.3, "independence": 0.0},
         "d": {"ambition": -0.7, "independence": -0.5}},
    ),
    QuestionnaireItem(
        "A16", "You've been working on something for months with no result. You:",
        {"a": "keep going", "b": "change approach",
         "c": "stop", "d": "ask for help"},
        {"a": {"ambition": 1.0, "independence": 0.5},
         "b": {"ambition": 0.5, "independence": 0.3},
         "c": {"ambition": -1.0, "independence": 0.0},
         "d": {"ambition": 0.0, "independence": -1.0}},
    ),
    QuestionnaireItem(
        "A17", "A chance at something great with a real chance of losing what you have. You:",
        {"a": "take it", "b": "take a smaller version",
         "c": "decline", "d": "take it only with others alongside"},
        {"a": {"risk_tolerance": 1.0, "ambition": 0.5},
         "b": {"risk_tolerance": 0.3, "ambition": 0.2},
         "c": {"risk_tolerance": -1.0, "ambition": -0.3},
         "d": {"risk_tolerance": 0.3, "ambition": 0.2}},
    ),
    QuestionnaireItem(
        "A18", "You have more than you need and someone nearby has less. You:",
        {"a": "give without being asked", "b": "give if asked",
         "c": "give to people you know", "d": "keep it"},
        {"a": {"generosity": 1.0, "loyalty": 0.3},
         "b": {"generosity": 0.3, "loyalty": 0.0},
         "c": {"generosity": 0.0, "loyalty": 0.5},
         "d": {"generosity": -1.0, "loyalty": -0.3}},
    ),
    QuestionnaireItem(
        "A19", "Someone takes something of yours without asking. You:",
        {"a": "confront", "b": "let it go",
         "c": "take something back", "d": "stop trusting them but say nothing"},
        {"a": {"conflict_directness": 1.0, "grudge_retention": -0.3, "forgiveness": 0.0},
         "b": {"conflict_directness": -1.0, "grudge_retention": -0.5, "forgiveness": 0.5},
         "c": {"conflict_directness": 0.5, "grudge_retention": 0.0, "forgiveness": -0.3},
         "d": {"conflict_directness": -1.0, "grudge_retention": 1.0, "forgiveness": -1.0}},
    ),
    QuestionnaireItem(
        "A20", "When something upsets you, people around you:",
        {"a": "know immediately", "b": "find out later",
         "c": "rarely find out", "d": "find out from someone else"},
        {"a": {"emotional_expressiveness": 1.0},
         "b": {"emotional_expressiveness": 0.0},
         "c": {"emotional_expressiveness": -0.7},
         "d": {"emotional_expressiveness": -1.0}},
    ),
)

# A21-A24: voice items. Handled with dedicated tables rather than trait deltas.
HUMOUR_OPTIONS = {"a": "dry", "b": "warm", "c": "absurd", "d": "sarcastic", "e": "none"}
VERBOSITY_A22 = {"a": 1.0, "b": 0.6, "c": 0.3, "d": 0.0}
SOCIABILITY_A22 = {"a": 0.3, "b": 0.0, "c": -0.2, "d": -0.4}
PROFANITY_A23 = {"a": 1.0, "b": 0.6, "c": 0.3, "d": 0.0}
VERBOSITY_A24 = {"a": 1.0, "b": 0.6, "c": 0.2, "d": 0.0}
FORMALITY_A24 = {"a": 0.6, "b": 0.5, "c": 0.3, "d": 0.1}

FREE_TEXT_ITEM_IDS = ("A25", "A26", "A27", "A28", "A29", "A30")


def score_trait_vector(answers: dict[str, str]) -> dict[str, float]:
    """answers: item id -> option letter (e.g. {"A1": "a", ...}).

    Unanswered or unmapped traits default to 0.5, per spec.md §3.
    """
    accum: dict[str, list[float]] = {name: [] for name in TRAIT_NAMES}
    sociability_extra: list[float] = []

    for item in TRAIT_ITEMS:
        option = answers.get(item.id)
        if option is None:
            continue
        for trait, delta in item.effects.get(option, {}).items():
            accum[trait].append(delta)

    a22 = answers.get("A22")
    if a22 in SOCIABILITY_A22:
        sociability_extra.append(SOCIABILITY_A22[a22])
    if sociability_extra:
        accum["sociability"].extend(sociability_extra)

    scores: dict[str, float] = {}
    for trait in TRAIT_NAMES:
        deltas = accum[trait]
        avg = sum(deltas) / len(deltas) if deltas else 0.0
        scores[trait] = clamp01(0.5 + TRAIT_SCALE * avg)
    return scores


def score_voice_profile(answers: dict[str, str]) -> dict[str, object]:
    """Returns kwargs for `VoiceProfile` derived from A21-A24."""
    humour_style = HUMOUR_OPTIONS.get(answers.get("A21", ""), "none")

    verbosity_samples = []
    if answers.get("A22") in VERBOSITY_A22:
        verbosity_samples.append(VERBOSITY_A22[answers["A22"]])
    if answers.get("A24") in VERBOSITY_A24:
        verbosity_samples.append(VERBOSITY_A24[answers["A24"]])
    verbosity = sum(verbosity_samples) / len(verbosity_samples) if verbosity_samples else 0.5

    formality = FORMALITY_A24.get(answers.get("A24", ""), 0.5)
    profanity_baseline = PROFANITY_A23.get(answers.get("A23", ""), 0.5)

    return {
        "verbosity": clamp01(verbosity),
        "formality": clamp01(formality),
        "humour_style": humour_style,
        "profanity_baseline": clamp01(profanity_baseline),
    }


@dataclass
class QuestionnaireResult:
    trait_scores: dict[str, float]
    voice_kwargs: dict[str, object]
    free_text: dict[str, str]
    boundary_text: str | None  # A29


def score_questionnaire(
    answers: dict[str, str], free_text: dict[str, str] | None = None
) -> QuestionnaireResult:
    free_text = free_text or {}
    return QuestionnaireResult(
        trait_scores=score_trait_vector(answers),
        voice_kwargs=score_voice_profile(answers),
        free_text=free_text,
        boundary_text=free_text.get("A29"),
    )
