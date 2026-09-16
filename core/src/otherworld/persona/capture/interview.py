"""Method B — conversational interview. See About/spec.md §2.3.

The interviewer asks a grounded, scenario-shaped question per trait area
("You said you'd let it go — has that actually happened?"), the owner
answers in free text, and the engine extracts a trait signal from the
answer. Extraction here is a deterministic keyword matcher rather than an
LLM call: About/plan.md §11.2 forbids live LLM calls in CI, and a solo-build
M1 doesn't yet have provider keys configured (About/README.md open items).
`extract_signal` is the seam — swap it for an `LLMProvider.tier2`-backed
extractor later without touching the rest of the engine.

Stop condition (spec.md §2.3): every trait at confidence >= 0.6, or 25
simulated minutes elapsed. The functional `score_interview` here computes a
finished result from a full transcript; `InterviewSession` (below) is the
turn-by-turn version an interactive CLI drives.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from otherworld.persona.scoring import TRAIT_NAMES, clamp01

MIN_CONFIDENCE = 0.6
MAX_SESSION_SECONDS = 25 * 60

# Scale applied to keyword-hit balance when nudging a trait away from 0.5.
TRAIT_SCALE = 0.2
# Confidence gained per keyword hit (up or down), regardless of direction.
CONFIDENCE_PER_HIT = 0.15
BASE_CONFIDENCE = 0.5


@dataclass(frozen=True)
class InterviewPrompt:
    id: str
    prompt: str
    traits: tuple[str, ...]


INTERVIEW_PROMPTS: tuple[InterviewPrompt, ...] = (
    InterviewPrompt("conflict", "Tell me about a time a friend let you down. What did you do?",
                     ("conflict_directness", "grudge_retention")),
    InterviewPrompt("criticism", "How do you react when someone criticises your work in front of others?",
                     ("honesty", "emotional_expressiveness")),
    InterviewPrompt("falling_out", "Describe a serious falling-out you had and what happened afterward.",
                     ("forgiveness", "grudge_retention")),
    InterviewPrompt("confidence", "A friend tells you something in confidence that affects someone "
                                   "else you both know. What do you do?",
                     ("loyalty", "honesty")),
    InterviewPrompt("risk", "Tell me about a time you took a real risk for something you wanted.",
                     ("risk_tolerance", "ambition")),
    InterviewPrompt("generosity", "Someone you know needs help and you have more than enough. What happens?",
                     ("generosity", "loyalty")),
    InterviewPrompt("social", "Describe how you act at a gathering where you only know one person.",
                     ("sociability", "independence")),
    InterviewPrompt("curiosity", "When someone new joins a group you're part of, what do you do?",
                     ("curiosity", "sociability")),
    InterviewPrompt("ambition", "What do you do with a free day and no obligations?",
                     ("ambition", "independence")),
    InterviewPrompt("expression", "When something upsets you, how do people around you find out?",
                     ("emotional_expressiveness",)),
)
BOUNDARY_PROMPT = InterviewPrompt(
    "boundary", "Is there anything your agent should never do, no matter what happens in the world?", ()
)
VOICE_PROMPT = InterviewPrompt(
    "voice", "What's something you say a lot, and what's your sense of humour like?", ()
)

ALL_PROMPTS: tuple[InterviewPrompt, ...] = INTERVIEW_PROMPTS + (BOUNDARY_PROMPT, VOICE_PROMPT)

# trait -> (up-keywords, down-keywords). Deliberately simple, deliberately
# swappable — short stems (substring-matched) rather than exact phrases, so
# "confronted" and "confronting" both hit "confront". This is a stand-in
# for real extraction (an LLM call, once provider keys exist — see the
# module docstring); real transcripts use far more varied phrasing than any
# fixed list can fully cover, so treat a persona with many neutral (0.5,
# low-confidence) traits as a signal to broaden this list or re-run, not as
# ground truth about the person.
KEYWORD_SIGNALS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "conflict_directness": (
        ("confront", "spoke up", "spoke to them", "told them", "told him", "told her",
         "said something", "called them out", "brought it up", "addressed it", "direct",
         "straight to them", "asked them about it", "talked to them about it"),
        ("ignore", "let it go", "said nothing", "avoid", "didn't say anything", "stayed quiet",
         "kept quiet", "held it in", "bit my tongue", "never mentioned", "didn't bring it up"),
    ),
    "grudge_retention": (
        ("still bother", "still think about", "never forgot", "still annoys", "still bugs",
         "hold onto", "haven't forgiven", "hard to let go", "still upset about", "still mad"),
        ("forgot about it", "moved on", "doesn't matter anymore", "let it go", "over it",
         "water under the bridge", "not a big deal anymore", "no big deal"),
    ),
    "forgiveness": (
        ("forgave", "forgive", "gave them another chance", "moved past it", "reconcil",
         "made up", "patched things up", "worked it out", "let it go", "let bygones"),
        ("never spoke again", "cut them off", "couldn't forgive", "ended the friendship",
         "never forgave", "cut ties", "walked away from", "didn't talk to them again"),
    ),
    "honesty": (
        ("honest", "told the truth", "the truth", "said what i thought", "straightforward",
         "upfront", "blunt", "didn't hide it", "was direct about it"),
        ("lied", "lie", "didn't tell them", "kept it to myself", "sugarcoat", "white lie",
         "wasn't honest", "held back", "didn't mention it"),
    ),
    "loyalty": (
        ("stood by", "defended", "kept it secret", "backed them", "sided with",
         "kept the confidence", "had their back", "stuck up for", "protected them", "covered for"),
        ("told the other person", "didn't back them", "stayed neutral", "told them anyway",
         "betrayed", "sided against", "let them down", "didn't stick up for"),
    ),
    "risk_tolerance": (
        ("took the risk", "went for it", "took a chance", "bet on", "took the leap",
         "risked it", "jumped in", "gambled", "quit my job", "took a gamble", "just did it"),
        ("played it safe", "didn't risk", "backed out", "too risky", "declined",
         "stayed safe", "didn't take the chance", "cautious", "safer option"),
    ),
    "generosity": (
        ("gave", "helped out", "paid for", "shared", "without being asked", "offered",
         "donated", "lent them", "covered it", "picked up the tab", "gave them"),
        ("kept it", "didn't help", "said no", "couldn't spare it", "kept it for myself",
         "didn't offer", "couldn't afford to help"),
    ),
    "ambition": (
        ("started a project", "built", "worked on", "pursued", "set a goal", "kept going",
         "pushed through", "grinded", "hustled", "chased it", "made progress"),
        ("rested", "relaxed", "did nothing", "watched tv", "took it easy", "gave up",
         "chilled", "lazy day", "napped", "did nothing productive"),
    ),
    "sociability": (
        ("met new people", "talked to everyone", "reached out", "socialized", "socialised",
         "introduced myself", "made friends", "mingled", "chatted with", "struck up a conversation"),
        ("stayed with", "left early", "kept to myself", "avoided people", "didn't reach out",
         "stayed home", "didn't talk to anyone", "kept a low profile"),
    ),
    "curiosity": (
        ("asked questions", "explored", "included them", "wanted to know more", "curious",
         "wondered", "looked into it", "asked about", "asked around"),
        ("ignored them", "didn't bother", "carried on as normal", "watched first",
         "didn't ask", "not interested", "didn't look into it"),
    ),
    "independence": (
        ("did it my way", "on my own", "didn't need help", "my own path", "kept going alone",
         "by myself", "figured it out myself", "handled it myself", "on my own terms"),
        ("asked for help", "went along with", "followed", "deferred to", "needed help",
         "relied on", "let them decide", "went with what they wanted"),
    ),
    "emotional_expressiveness": (
        ("everyone knew", "couldn't hide it", "showed it", "got upset visibly", "was obvious",
         "cried", "broke down", "wore it on my sleeve", "couldn't hold it in", "let it show"),
        ("kept it inside", "didn't show", "no one noticed", "hid it", "stayed calm",
         "bottled it up", "didn't let it show", "poker face", "kept a straight face"),
    ),
}


def extract_signal(text: str) -> dict[str, tuple[float, int]]:
    """text -> {trait: (delta, hit_count)} for every trait with a keyword hit."""
    lowered = text.lower()
    signal: dict[str, tuple[float, int]] = {}
    for trait, (up_words, down_words) in KEYWORD_SIGNALS.items():
        up_hits = sum(1 for w in up_words if w in lowered)
        down_hits = sum(1 for w in down_words if w in lowered)
        total_hits = up_hits + down_hits
        if total_hits == 0:
            continue
        delta = (up_hits - down_hits) / total_hits
        signal[trait] = (delta, total_hits)
    return signal


def _humour_from_text(text: str) -> str:
    lowered = text.lower()
    for style in ("dry", "sarcastic", "absurd", "warm"):
        if style in lowered:
            return style
    return "none"


@dataclass
class InterviewResult:
    trait_scores: dict[str, float]
    confidences: dict[str, float]
    voice_kwargs: dict[str, object]
    free_text: dict[str, str]
    boundary_text: str | None


def score_interview(answers: dict[str, str]) -> InterviewResult:
    """answers: prompt id -> free-text response, covering all of ALL_PROMPTS."""
    accum: dict[str, list[tuple[float, int]]] = {name: [] for name in TRAIT_NAMES}

    for prompt in INTERVIEW_PROMPTS:
        text = answers.get(prompt.id, "")
        if not text:
            continue
        for trait, (delta, hits) in extract_signal(text).items():
            accum[trait].append((delta, hits))

    trait_scores: dict[str, float] = {}
    confidences: dict[str, float] = {}
    for trait in TRAIT_NAMES:
        signals = accum[trait]
        if not signals:
            # 0.5 here is "no opinion" for a from-scratch capture, not weak
            # evidence — confidence 0.0 (not BASE_CONFIDENCE) says so
            # explicitly, so merge_capture_into_persona (service.py) treats
            # a miss as "no new information" rather than a real reading
            # that should pull an existing estimate toward neutral.
            trait_scores[trait] = 0.5
            confidences[trait] = 0.0
            continue
        total_hits = sum(hits for _, hits in signals)
        weighted_delta = sum(delta * hits for delta, hits in signals) / total_hits
        trait_scores[trait] = clamp01(0.5 + TRAIT_SCALE * weighted_delta * (1 + 0.1 * total_hits))
        confidences[trait] = clamp01(BASE_CONFIDENCE + CONFIDENCE_PER_HIT * total_hits)

    voice_text = answers.get(VOICE_PROMPT.id, "")
    words = voice_text.split()
    verbosity = clamp01(len(words) / 40.0)
    profanity_words = {"damn", "hell", "shit", "fuck", "crap"}
    profanity_baseline = clamp01(
        sum(1 for w in words if w.strip(".,!?").lower() in profanity_words) / max(1, len(words)) * 10
    )

    return InterviewResult(
        trait_scores=trait_scores,
        confidences=confidences,
        voice_kwargs={
            "verbosity": verbosity,
            "formality": 0.5,
            "humour_style": _humour_from_text(voice_text),
            "profanity_baseline": profanity_baseline,
        },
        free_text=answers,
        boundary_text=answers.get(BOUNDARY_PROMPT.id),
    )


@dataclass
class InterviewSession:
    """Turn-by-turn interview state, for an interactive driver (e.g. a CLI).

    Not used by `score_interview` (which scores a complete transcript at
    once) — this is the incremental version that decides, turn by turn,
    whether every trait has reached MIN_CONFIDENCE or the time budget has
    run out, per spec.md §2.3's stop condition.
    """

    answers: dict[str, str] = field(default_factory=dict)
    started_at: float = field(default_factory=time.monotonic)

    def remaining_prompts(self) -> list[InterviewPrompt]:
        return [p for p in ALL_PROMPTS if p.id not in self.answers]

    def record(self, prompt_id: str, answer: str) -> None:
        self.answers[prompt_id] = answer

    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_at

    def is_complete(self) -> bool:
        if self.elapsed_seconds() >= MAX_SESSION_SECONDS:
            return True
        if self.remaining_prompts():
            return False
        result = score_interview(self.answers)
        return all(conf >= MIN_CONFIDENCE for conf in result.confidences.values())

    def finish(self) -> InterviewResult:
        return score_interview(self.answers)
