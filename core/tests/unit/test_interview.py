"""T1.2, T1.4 — About/plan.md M1 acceptance tests, method B and cross-method agreement."""

from otherworld.models.persona import TraitVector
from otherworld.persona.capture.interview import MIN_CONFIDENCE, score_interview
from otherworld.persona.capture.questionnaire import score_questionnaire
from otherworld.persona.scoring import traits_agree_within
from tests.unit.test_questionnaire import ALPHA_ANSWERS, ALPHA_FREE_TEXT

ALPHA_INTERVIEW_ANSWERS = {
    "conflict": (
        "I confronted them directly and told them how I felt. "
        "It doesn't bother me anymore, I moved on."
    ),
    "criticism": (
        "I was honest and straightforward with them, I said what i thought. "
        "Everyone knew I was upset because I showed it."
    ),
    "falling_out": (
        "We eventually reconciled and I forgave them, we moved past it. "
        "It doesn't matter anymore, I've moved on."
    ),
    "confidence": (
        "I kept the confidence and stood by my friend, kept it secret. "
        "Later I was honest and told the truth about it."
    ),
    "risk": (
        "I took the risk and went for it, I bet on myself and set a goal "
        "to make it happen."
    ),
    "generosity": "I gave without being asked and offered to help, I backed them the whole way.",
    "social": "I met new people and introduced myself to everyone, I did it my way on my own.",
    "curiosity": "I asked questions and included them, I wanted to know more and introduced myself.",
    "ambition": "I started a project and worked on it entirely on my own, kept going without help.",
    "expression": "Everyone knew immediately, I couldn't hide it and it was obvious.",
    "boundary": "Never let my agent get into a romantic relationship.",
    "voice": "I always say 'fair enough' and I'm pretty dry and sarcastic.",
}


def test_method_b_end_to_end_reaches_min_confidence_on_every_trait():
    result = score_interview(ALPHA_INTERVIEW_ANSWERS)
    trait_vector = TraitVector(**result.trait_scores)
    for trait in TraitVector.model_fields:
        assert 0.0 <= getattr(trait_vector, trait) <= 1.0
        conf = result.confidences[trait]
        assert conf >= MIN_CONFIDENCE, f"{trait} confidence too low: {conf}"

    assert result.boundary_text == "Never let my agent get into a romantic relationship."


def test_method_a_and_b_agree_on_the_same_person():
    a_result = score_questionnaire(ALPHA_ANSWERS, ALPHA_FREE_TEXT)
    b_result = score_interview(ALPHA_INTERVIEW_ANSWERS)

    a_vector = TraitVector(**a_result.trait_scores)
    b_vector = TraitVector(**b_result.trait_scores)

    agreeing = traits_agree_within(a_vector, b_vector, tolerance=0.2)
    assert agreeing >= 8, f"only {agreeing}/12 traits agreed within 0.2"
