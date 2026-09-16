"""T1.1, T1.3 — About/plan.md M1 acceptance tests, method A."""

from otherworld.models.persona import TraitVector
from otherworld.persona.capture.questionnaire import score_questionnaire
from otherworld.persona.scoring import TRAIT_NAMES, cosine_distance

ALPHA_ANSWERS = {
    "A1": "a", "A2": "a", "A3": "a", "A4": "a", "A5": "d", "A6": "c",
    "A7": "a", "A8": "c", "A9": "c", "A10": "a", "A11": "a", "A12": "b",
    "A13": "a", "A14": "d", "A15": "a", "A16": "a", "A17": "a", "A18": "a",
    "A19": "a", "A20": "a", "A21": "a", "A22": "b", "A23": "c", "A24": "b",
}
_OPPOSITE = {"a": "d", "b": "c", "c": "b", "d": "a"}
BETA_ANSWERS = {k: _OPPOSITE[v] for k, v in ALPHA_ANSWERS.items()}

ALPHA_FREE_TEXT = {
    "A25": "I told them exactly how it happened and we sorted it out quickly.",
    "A27": "fair enough",
    "A29": "Never let my agent lie about who it is.",
}


def test_method_a_end_to_end_populates_all_traits():
    result = score_questionnaire(ALPHA_ANSWERS, ALPHA_FREE_TEXT)
    trait_vector = TraitVector(**result.trait_scores)
    for trait in TRAIT_NAMES:
        value = getattr(trait_vector, trait)
        assert 0.0 <= value <= 1.0

    assert result.boundary_text == "Never let my agent lie about who it is."


def test_method_a_two_different_people_diverge():
    alpha = TraitVector(**score_questionnaire(ALPHA_ANSWERS).trait_scores)
    beta = TraitVector(**score_questionnaire(BETA_ANSWERS).trait_scores)
    assert cosine_distance(alpha, beta) >= 0.25
