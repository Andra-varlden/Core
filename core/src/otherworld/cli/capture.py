"""Interactive persona capture. See About/plan.md M1.

    python -m otherworld.cli.capture --method A --handle jpf --email jpf@example.com
    python -m otherworld.cli.capture --method B --handle jpf --email jpf@example.com
    python -m otherworld.cli.capture --method D --handle jpf --email jpf@example.com

Run once per real person (About/plan.md M1 deliverable: 4-5 real persona
objects — the founder plus the M4 Recognition Metric subjects, recruited
now per the README's open items).

Method D (scenario replay, spec.md §2.5) refines an *existing* persona
rather than building a fresh one — run Method A or B first. Built ahead of
spec.md's own "Phase 2+" placement note for it, specifically because a
real M4 Recognition Metric trial came back "weak" (56-69%), which is the
one case spec.md's own interpretation table (§14) calls for adding it.
"""

from __future__ import annotations

import argparse
import asyncio

from otherworld.db import async_session_factory
from otherworld.models.persona import PersonaObject
from otherworld.owner.service import get_or_create_owner
from otherworld.persona.boundaries import DEFAULT_BOUNDARY_TOGGLES
from otherworld.persona.capture.interview import ALL_PROMPTS, score_interview
from otherworld.persona.capture.questionnaire import FREE_TEXT_ITEM_IDS, TRAIT_ITEMS, score_questionnaire
from otherworld.persona.capture.scenario import SCENARIOS, score_scenario_replay
from otherworld.persona.service import (
    apply_scenario_replay,
    build_persona_from_interview,
    build_persona_from_questionnaire,
    edit_persona,
    get_latest_persona,
    merge_capture_into_persona,
    phrases_from_free_text,
    questionnaire_field_confidence,
    save_persona,
)

OPTIONAL_BOUNDARY_KEYS = [k for k in DEFAULT_BOUNDARY_TOGGLES if k not in ("no_romance", "no_violence")]

_FREE_TEXT_PROMPTS = {
    "A25": "Describe a disagreement you had and how it ended, in your own words.",
    "A26": "Describe a friend of yours without naming them.",
    "A27": "What's something you say a lot?",
    "A28": "Describe your ideal day, hour by hour.",
    "A29": "What would you never do, no matter what? (this becomes a hard boundary)",
    "A30": "What do people misunderstand about you?",
}


def _ask_option(prompt: str, options: dict[str, str]) -> str:
    print(f"\n{prompt}")
    for letter, text in options.items():
        print(f"  ({letter}) {text}")
    while True:
        choice = input("> ").strip().lower()
        if choice in options:
            return choice
        print(f"Please answer one of: {', '.join(options)}")


def _ask_free_text(prompt: str) -> str:
    print(f"\n{prompt}")
    return input("> ").strip()


def _ask_boundary_toggles() -> set[str]:
    print("\nOptional boundaries - your agent will never do these, no matter what happens in the world.")
    print("(no romance/intimacy and no violence are always off, platform-wide)")
    enabled = set()
    for key in OPTIONAL_BOUNDARY_KEYS:
        description, _ = DEFAULT_BOUNDARY_TOGGLES[key]
        answer = input(f"Block '{description}'? [y/N] > ").strip().lower()
        if answer == "y":
            enabled.add(key)
    return enabled


def run_questionnaire() -> tuple[dict[str, str], dict[str, str]]:
    answers: dict[str, str] = {}
    for item in TRAIT_ITEMS:
        answers[item.id] = _ask_option(item.prompt, item.options)

    answers["A21"] = _ask_option(
        "Your humour is mostly:", {"a": "dry", "b": "warm", "c": "absurd", "d": "sarcastic", "e": "not funny"}
    )
    answers["A22"] = _ask_option(
        "In a conversation you typically:",
        {"a": "talk most", "b": "talk about equally", "c": "listen more", "d": "listen almost entirely"},
    )
    answers["A23"] = _ask_option(
        "You swear:", {"a": "constantly", "b": "when it fits", "c": "rarely", "d": "never"}
    )
    answers["A24"] = _ask_option(
        "Your messages are usually:",
        {"a": "long", "b": "a few sentences", "c": "one line", "d": "a word or two"},
    )

    free_text = {item_id: _ask_free_text(_FREE_TEXT_PROMPTS[item_id]) for item_id in FREE_TEXT_ITEM_IDS}
    return answers, free_text


def run_interview() -> dict[str, str]:
    return {prompt.id: _ask_free_text(prompt.prompt) for prompt in ALL_PROMPTS}


def _ask_scenario(prompt: str, options: dict[str, tuple[str, str]]) -> str:
    print(f"\n{prompt}")
    for letter, (action, framing) in options.items():
        print(f"  ({letter}) {action} — {framing}")
    while True:
        choice = input("> ").strip().lower()
        if choice in options:
            return choice
        print(f"Please answer one of: {', '.join(options)}")


def run_scenario_replay() -> dict[str, str]:
    return {scenario.id: _ask_scenario(scenario.prompt, scenario.options) for scenario in SCENARIOS}


def _print_summary(persona: PersonaObject) -> None:
    print(f"\nPersonaObject {persona.id} (v{persona.version}, method {persona.source_methods})")
    for trait, value in persona.values.model_dump().items():
        conf = persona.field_confidence.get(trait, 0.5)
        print(f"  {trait:26s} {value:.2f}  (confidence {conf:.2f})")
    if persona.decision_weight_overrides:
        print("  decision_weight_overrides (Method D — override the trait values above):")
        for trait, value in persona.decision_weight_overrides.items():
            conf = persona.field_confidence.get(f"decision_weight.{trait}", 0.0)
            print(f"    {trait:24s} {value:.2f}  (confidence {conf:.2f})")
    print(f"  voice: {persona.voice.model_dump()}")
    print("  boundaries:")
    for rule in persona.boundaries:
        print(f"    - {rule.description} [{rule.severity}]")


async def _main(method: str, handle: str, email: str) -> None:
    async with async_session_factory() as session:
        owner = await get_or_create_owner(session, handle, email)
        existing = await get_latest_persona(session, owner.id)
        if existing is not None:
            print(f"\nFound an existing persona (v{existing.version}, {existing.source_methods}) "
                  f"for {handle} — this capture will refine it into a new version, not replace it.")

        persona: PersonaObject
        if method == "D":
            if existing is None:
                raise SystemExit(
                    f"'{handle}' has no captured persona yet — Method D refines an existing one "
                    "(spec.md §2.5); run --method A or --method B first."
                )
            answers_d = run_scenario_replay()
            d_result = score_scenario_replay(answers_d)
            persona = apply_scenario_replay(existing, d_result)
            await save_persona(session, persona)
        elif method == "A":
            answers_a, free_text = run_questionnaire()
            enabled_boundaries = _ask_boundary_toggles()
            a_result = score_questionnaire(answers_a, free_text)
            if existing is None:
                persona = build_persona_from_questionnaire(owner.id, answers_a, a_result, enabled_boundaries)
            else:
                voice_updates = {
                    **a_result.voice_kwargs,
                    "characteristic_phrases": phrases_from_free_text(a_result.free_text),
                    "diction_notes": a_result.free_text.get("A25", ""),
                }
                updates = merge_capture_into_persona(
                    existing,
                    a_result.trait_scores,
                    questionnaire_field_confidence(answers_a),
                    voice_updates,
                    a_result.boundary_text,
                    enabled_boundaries,
                    "A",
                )
                persona = await edit_persona(session, existing, **updates)
        else:
            answers_b = run_interview()
            enabled_boundaries = _ask_boundary_toggles()
            b_result = score_interview(answers_b)
            if existing is None:
                persona = build_persona_from_interview(owner.id, b_result, enabled_boundaries)
            else:
                voice_updates = {
                    **b_result.voice_kwargs,
                    "diction_notes": b_result.free_text.get(ALL_PROMPTS[0].id, ""),
                }
                updates = merge_capture_into_persona(
                    existing,
                    b_result.trait_scores,
                    b_result.confidences,
                    voice_updates,
                    b_result.boundary_text,
                    enabled_boundaries,
                    "B",
                )
                persona = await edit_persona(session, existing, **updates)

        if existing is None:
            await save_persona(session, persona)
        await session.commit()

    _print_summary(persona)


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture a persona (About/spec.md §2).")
    parser.add_argument("--method", choices=["A", "B", "D"], required=True)
    parser.add_argument("--handle", required=True)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    asyncio.run(_main(args.method, args.handle, args.email))


if __name__ == "__main__":
    main()
