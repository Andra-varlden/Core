"""T1.1, T1.2, T1.6 — About/plan.md M1 acceptance tests: persistence and versioning."""

import uuid

import pytest

from otherworld.models.persona import PersonaObjectORM, persona_from_orm
from otherworld.persona.capture.interview import score_interview
from otherworld.persona.capture.questionnaire import score_questionnaire
from otherworld.persona.capture.scenario import score_scenario_replay
from otherworld.persona.service import (
    apply_scenario_replay,
    build_persona_from_interview,
    build_persona_from_questionnaire,
    edit_persona,
    get_latest_persona,
    get_persona_version,
    merge_capture_into_persona,
    save_persona,
)
from tests.unit.test_interview import ALPHA_INTERVIEW_ANSWERS
from tests.unit.test_questionnaire import ALPHA_ANSWERS, ALPHA_FREE_TEXT


@pytest.mark.asyncio
async def test_method_a_persists_and_round_trips(db_session):
    owner_id = uuid.uuid4()
    result = score_questionnaire(ALPHA_ANSWERS, ALPHA_FREE_TEXT)
    persona = build_persona_from_questionnaire(
        owner_id, ALPHA_ANSWERS, result, enabled_boundaries={"no_theft"}
    )

    await save_persona(db_session, persona)

    row = await db_session.get(PersonaObjectORM, persona.id)
    reloaded = persona_from_orm(row)
    assert reloaded == persona
    assert reloaded.version == 1
    assert reloaded.source_methods == ["A"]
    assert any(b.description == "no theft" for b in reloaded.boundaries)


@pytest.mark.asyncio
async def test_method_b_persists_with_high_confidence(db_session):
    owner_id = uuid.uuid4()
    result = score_interview(ALPHA_INTERVIEW_ANSWERS)
    persona = build_persona_from_interview(owner_id, result)

    await save_persona(db_session, persona)

    row = await db_session.get(PersonaObjectORM, persona.id)
    reloaded = persona_from_orm(row)
    assert reloaded == persona
    assert reloaded.source_methods == ["B"]
    assert all(conf >= 0.6 for conf in reloaded.field_confidence.values())


@pytest.mark.asyncio
async def test_editing_a_persona_creates_a_new_version_and_preserves_v1(db_session):
    owner_id = uuid.uuid4()
    result = score_questionnaire(ALPHA_ANSWERS, ALPHA_FREE_TEXT)
    v1 = build_persona_from_questionnaire(owner_id, ALPHA_ANSWERS, result)
    await save_persona(db_session, v1)

    updated_values = v1.values.model_copy(update={"honesty": 0.95})
    v2 = await edit_persona(db_session, v1, values=updated_values)

    assert v2.version == 2
    assert v2.id != v1.id

    reloaded_v1 = await get_persona_version(db_session, owner_id, 1)
    reloaded_v2 = await get_persona_version(db_session, owner_id, 2)

    assert reloaded_v1 == v1
    assert reloaded_v1.values.honesty == v1.values.honesty  # v1 untouched (invariant I5)
    assert reloaded_v2.values.honesty == 0.95
    assert reloaded_v2.version == 2


@pytest.mark.asyncio
async def test_second_capture_merges_into_a_new_version_not_a_duplicate_v1(db_session):
    """Regression test: About/architecture.md §3 says a later capture method
    should refine the existing persona (new version), not create a second,
    disconnected version-1 row for the same owner — the bug a real capture
    session surfaced.
    """
    owner_id = uuid.uuid4()
    a_result = score_questionnaire(ALPHA_ANSWERS, ALPHA_FREE_TEXT)
    v1 = build_persona_from_questionnaire(owner_id, ALPHA_ANSWERS, a_result, enabled_boundaries={"no_theft"})
    await save_persona(db_session, v1)

    latest = await get_latest_persona(db_session, owner_id)
    assert latest is not None
    assert latest.version == 1

    b_result = score_interview(ALPHA_INTERVIEW_ANSWERS)
    updates = merge_capture_into_persona(
        latest,
        b_result.trait_scores,
        b_result.confidences,
        b_result.voice_kwargs,
        b_result.boundary_text,
        None,
        "B",
    )
    v2 = await edit_persona(db_session, latest, **updates)

    assert v2.version == 2
    assert v2.source_methods == ["A", "B"]

    # exactly one row per version for this owner — no duplicate v1.
    reloaded_v1 = await get_persona_version(db_session, owner_id, 1)
    reloaded_v2 = await get_persona_version(db_session, owner_id, 2)
    assert reloaded_v1.version == 1
    assert reloaded_v2.version == 2

    # merged trait values sit between the two captures (confidence-weighted average).
    for trait in ("honesty", "sociability", "ambition"):
        a_value = getattr(v1.values, trait)
        b_value = b_result.trait_scores[trait]
        merged_value = getattr(v2.values, trait)
        lo, hi = sorted((a_value, b_value))
        assert lo - 1e-9 <= merged_value <= hi + 1e-9

    # boundaries carried forward, not duplicated.
    assert sum(1 for b in v2.boundaries if b.description == "no theft") == 1


@pytest.mark.asyncio
async def test_method_d_refines_decision_weights_of_an_existing_persona(db_session):
    """spec.md §2.5: Method D produces decision_weight_overrides, not
    TraitVector values — `values` itself must stay untouched, only
    `decision_weight_overrides` (and field_confidence) change."""
    owner_id = uuid.uuid4()
    a_result = score_questionnaire(ALPHA_ANSWERS, ALPHA_FREE_TEXT)
    v1 = build_persona_from_questionnaire(owner_id, ALPHA_ANSWERS, a_result)
    await save_persona(db_session, v1)

    d_result = score_scenario_replay({"D1": "a", "D2": "a"})
    v2 = await get_latest_persona(db_session, owner_id)
    assert v2 is not None
    v2 = apply_scenario_replay(v2, d_result)
    await save_persona(db_session, v2)

    assert v2.version == 2
    assert v2.source_methods == ["A", "D"]
    assert v2.values == v1.values  # Method D never touches the trait vector
    assert v2.decision_weight_overrides["sociability"] == d_result.decision_weight_overrides["sociability"]

    reloaded = await get_persona_version(db_session, owner_id, 2)
    assert reloaded == v2


@pytest.mark.asyncio
async def test_method_d_blends_with_its_own_prior_override_not_overwrites(db_session):
    owner_id = uuid.uuid4()
    a_result = score_questionnaire(ALPHA_ANSWERS, ALPHA_FREE_TEXT)
    v1 = build_persona_from_questionnaire(owner_id, ALPHA_ANSWERS, a_result)
    await save_persona(db_session, v1)

    first_pass = apply_scenario_replay(v1, score_scenario_replay({"D1": "a"}))  # sociability -> high
    second_pass = apply_scenario_replay(first_pass, score_scenario_replay({"D1": "c"}))  # sociability -> low

    # Blended, not simply replaced: strictly between the two extremes.
    high = score_scenario_replay({"D1": "a"}).decision_weight_overrides["sociability"]
    low = score_scenario_replay({"D1": "c"}).decision_weight_overrides["sociability"]
    blended = second_pass.decision_weight_overrides["sociability"]
    assert low < blended < high
    assert second_pass.version == 3
