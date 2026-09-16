# plan.md — Otherworld

> **Purpose of this file.** The order of work and the definition of done for
> each step. Every milestone has an explicit, testable exit condition. Nothing
> is "done" because it feels done.
>
> **Working assumption:** solo, full-time. Durations reflect that. Adjust if
> capacity changes and note the change here.
>
> **Status:** Living document. Update milestone status on every merge.
> **Last updated:** 2026-09-16

---

## Table of contents

1. [How to use this document](#1-how-to-use-this-document)
2. [Phase map and gates](#2-phase-map-and-gates)
3. [Phase 0 — Foundations](#3-phase-0--foundations)
4. [Phase 1 — Fidelity proof](#4-phase-1--fidelity-proof)
5. [Gate 1](#5-gate-1)
6. [Phase 2 — Closed multi-owner alpha](#6-phase-2--closed-multi-owner-alpha)
7. [Gate 2](#7-gate-2)
8. [Phase 3 — Watchable](#8-phase-3--watchable)
9. [Gate 3](#9-gate-3)
10. [Phase 4 — Open beta and revenue](#10-phase-4--open-beta-and-revenue)
11. [Testing strategy](#11-testing-strategy)
12. [Definition of done](#12-definition-of-done)
13. [Git and PR conventions](#13-git-and-pr-conventions)
14. [Documentation maintenance protocol](#14-documentation-maintenance-protocol)
15. [Risk register](#15-risk-register)
16. [The B2B fork](#16-the-b2b-fork)
17. [Hiring and funding triggers](#17-hiring-and-funding-triggers)

---

## 1. How to use this document

**At the start of a milestone:** read its scope, its deliverables, and its
acceptance tests. Write the acceptance tests *before* the implementation where
possible.

**At the end of a milestone:** run the acceptance tests. If any fail, the
milestone is not complete. Update the status table, update the README, and only
then move on.

**Milestone status values:** `NOT STARTED` · `IN PROGRESS` · `BLOCKED` ·
`COMPLETE`

### Status board

| ID | Milestone | Status | Started | Completed |
|---|---|---|---|---|
| M0 | Foundations and schemas | COMPLETE | 2026-09-15 | 2026-09-15 |
| M1 | Persona capture | IN PROGRESS | 2026-09-15 | |
| M2 | Single agent, single tick | COMPLETE | 2026-09-16 | 2026-09-16 |
| M3 | Two agents, first contact | COMPLETE | 2026-09-16 | 2026-09-16 |
| M4 | **Recognition Metric — Gate 1** | IN PROGRESS | 2026-09-16 | |
| M5 | Small world, full social system | NOT STARTED | | |
| M6 | Hosting, accounts, persistence | NOT STARTED | | |
| M7 | Safety and moderation for real | NOT STARTED | | |
| M8 | Owner dashboard (minimum) | NOT STARTED | | |
| M9 | Closed alpha — **Gate 2** | NOT STARTED | | |
| M10 | Highlight engine | NOT STARTED | | |
| M11 | Full dashboard and share cards | NOT STARTED | | |
| M12 | Tile world and live view — **Gate 3** | NOT STARTED | | |
| M13 | Scale, payments, open beta | NOT STARTED | | |

---

## 2. Phase map and gates

```
Phase 0  Foundations          M0
Phase 1  Fidelity proof       M1 → M2 → M3 → M4
         ══ GATE 1: Recognition accuracy ≥ 70% ══
Phase 1.5 Social depth        M5
Phase 2  Closed alpha         M6 → M7 → M8 → M9
         ══ GATE 2: Unprompted weekly return ══
Phase 3  Watchable            M10 → M11 → M12
         ══ GATE 3: Non-owner spectators ══
Phase 4  Open beta            M13
```

**Gates are stop conditions, not checkpoints.** A failed gate means going
backwards, not pressing on with a caveat. This is the single most important
discipline in the plan — the failure mode that kills projects in this genre is
building the world before proving the premise (`context.md` ADR-008).

---

## 3. Phase 0 — Foundations

### M0 — Foundations and schemas
**Duration:** 3–4 days
**Goal:** Every data shape in the system exists as typed code before any logic
is written.

**Scope**
- Repos created: `docs`, `core`. Both private. Branch protection on `main`.
- These four documents committed to `docs`.
- `core` scaffold per `architecture.md` §15.
- Docker Compose: Postgres 16 + pgvector, Redis.
- All models from `architecture.md` §9 as Pydantic + SQLAlchemy.
- Alembic initial migration.
- `LLMProvider` protocol defined — **before any call site exists**.
- `ActionRegistry` with the full action list from `architecture.md` §10.
- `config.py` reading every value from `spec.md` §20.
- CI: ruff, mypy (strict on `models/` and `safety/`), pytest.

**Explicitly out of scope:** any behaviour, any LLM call, any simulation.

**Acceptance tests**
| # | Test | Passes when |
|---|---|---|
| T0.1 | `pytest` green on an empty test suite with CI wired | CI runs on push |
| T0.2 | `alembic upgrade head` on a clean DB | All tables created |
| T0.3 | Round-trip every model: construct → persist → load → compare | Equality holds for all models |
| T0.4 | `ActionRegistry.resolve("execute_code")` | Raises `UnknownActionError` |
| T0.5 | `ActionRegistry` contains exactly the actions in `architecture.md` §10 | Count and names match — test reads the doc's list as fixture data |
| T0.6 | Config loads every key in `spec.md` §20 | No missing-key errors |
| T0.7 | `mypy --strict src/otherworld/models src/otherworld/safety` | Clean |
| T0.8 | Grep test: no vendor SDK import outside `core/llm/` | Zero matches |

**Exit criterion:** all of T0.1–T0.8 green.

---

## 4. Phase 1 — Fidelity proof

The whole of Phase 1 runs locally. No hosting, no accounts, no UI, no world
rendering. Text only.

### M1 — Persona capture
**Duration:** 1 week
**Goal:** Produce real persona objects from real people.

**Scope**
- Method A: the 30-item questionnaire from `spec.md` §2.2, as a CLI or a single
  local page.
- Method B: the interviewer agent, per `spec.md` §2.3.
- Trait scoring: answers → `TraitVector`.
- Voice extraction from free-text items.
- Boundary layer capture (§2.6).
- `PersonaObject` persisted, versioned.

**Acceptance tests**
| # | Test | Passes when |
|---|---|---|
| T1.1 | Run method A end to end | Valid `PersonaObject` written with all 12 traits populated |
| T1.2 | Run method B end to end | Valid `PersonaObject`; every trait has confidence ≥ 0.6 |
| T1.3 | Two different people, same method | Trait vectors differ by cosine distance ≥ 0.25 **[TUNE]** |
| T1.4 | Same person, method A vs method B | Trait vectors agree within 0.2 per trait on ≥ 8 of 12 traits |
| T1.5 | Method C with third-party names present | All names redacted at ingestion; assert none survive |
| T1.6 | Edit a persona | Version increments; v1 remains retrievable and unmodified |
| T1.7 | Boundary capture | Produces compiled `BoundaryRule` predicates that evaluate |

**Deliverable:** 4–5 real persona objects — yourself plus 3–4 people who will
also be your M4 test subjects. **Recruit them now**, at M1, not at M4.

**Exit criterion:** T1.1–T1.7 green and ≥ 4 real persona objects on disk.

---

### M2 — Single agent, single tick
**Duration:** 1 week
**Goal:** The six-phase loop runs for one agent in an empty room.

**Scope**
- Compiler and binder.
- `TickScheduler` (single-agent, no concurrency).
- All six phases: perceive, retrieve, decide, validate, act, resolve.
- `MemoryStore` with embedding and retrieval.
- Validator with all four filters.
- **Action registry binding enforced** (ADR-002 — this is the milestone where
  containment goes in; retrofitting it later is a rewrite).
- Full decision trace logging.
- Seeded RNG; tick-based time only.

**Acceptance tests**
| # | Test | Passes when |
|---|---|---|
| T2.1 | 100 ticks, one agent, empty room | No crashes; 100 event records written |
| T2.2 | Determinism: same seed + mocked LLM, two runs | Byte-identical event streams |
| T2.3 | Memory write | Every tick with importance ≥ threshold produces a memory |
| T2.4 | Retrieval | Returns top-k ordered by the §5.2 formula; verified against a hand-computed fixture |
| T2.5 | Validator filter 1 | An action violating an owner boundary is rejected |
| T2.6 | Validator double rejection | Falls back to `idle`; agent does not crash |
| T2.7 | **Containment** | An LLM response proposing `execute_code`, `browse`, or any unregistered action is rejected before execution |
| T2.8 | Tier discipline | A tick with no escalation trigger never calls Tier 2 — asserted on a call spy |
| T2.9 | Trace completeness | Every Tier 1/2 decision logs all fields in `architecture.md` §17 |
| T2.10 | No wall-clock | Grep: no `datetime.now()` in `runtime/` decision paths |

**Exit criterion:** T2.1–T2.10 green. **T2.2 and T2.7 are non-negotiable** —
determinism and containment are load-bearing for everything after this.

---

### M3 — Two agents, first contact
**Duration:** 1 week
**Goal:** Two agents meet, talk, and a relationship exists.

**Scope**
- Multi-agent tick scheduling with deterministic apply order.
- Perception of other agents (still no tile map — a single abstract "room").
- Social and relational actions.
- Relationship engine: edge materialisation, trust deltas, Stranger →
  Acquaintance → Friend.
- Witness memory writing.
- Escalation trigger 1 (first encounter) driving Tier 2.
- **First real token measurement** — populate `spec.md` §15.2 with actual
  numbers.

**Acceptance tests**
| # | Test | Passes when |
|---|---|---|
| T3.1 | Two agents, 500 ticks | Edge exists; `bond_state` ≥ Acquaintance |
| T3.2 | Determinism with two agents | Identical streams across runs |
| T3.3 | Apply order | Actions applied in agent-id order regardless of completion order |
| T3.4 | Witness memories | A third observing agent has a memory of the exchange |
| T3.5 | Trust deltas | Match `spec.md` §6.2 exactly, per a fixture table |
| T3.6 | Friend promotion gate | Trust alone ≤ threshold does **not** promote without a high-importance shared memory |
| T3.7 | Edge uniqueness | `(a,b)` and `(b,a)` produce one row; DB constraint holds |
| T3.8 | Tier 2 on first encounter | Escalation trigger 1 fires exactly once per new pair |
| T3.9 | Cost measurement | Real token counts recorded and written into `spec.md` §15.2 |

**Exit criterion:** T3.1–T3.9 green, and a transcript you would actually show
someone.

---

### M4 — Recognition Metric (Gate 1)
**Duration:** 3–4 days plus subject scheduling
**Goal:** Answer the only question that matters at this stage.

**Scope**
- `RecognitionHarness` implementing `spec.md` §14 exactly.
- Run 4–5 persona agents for a simulated week.
- Administer the test to each owner.
- Record results against assumption A1 in `context.md` §11.

**Acceptance tests**
| # | Test | Passes when |
|---|---|---|
| T4.1 | Harness correctness | Decoys are category-matched; all names stripped — verified by manual inspection of 20 samples |
| T4.2 | Blinding | The owner cannot infer which are theirs from formatting, ordering or length |
| T4.3 | Trial completeness | Every subject completes; results persisted with persona version |

**Gate 1 criterion:** mean recognition accuracy **≥ 70%** across subjects
(`spec.md` §14).

**Status (2026-09-16):** `RecognitionHarness` is built and T4.1/T4.2 are
green (automated tests against synthetic event data). A real Groq provider
is now configured and confirmed working end to end via live pilot runs
(see `context.md` §11's updated A1 note) — persona-driven behavioural
variance is real, and two live bugs it surfaced are fixed: the model
hallucinating actions outside the registry (now given the closed action
list explicitly) and relationship state changes not being scored as
important per spec.md §5.1 (now fixed in `runtime/resolver.py`). T4.3 and
the actual Gate 1 number are still not attempted: 2 agents can only ever
produce ~2-3 high-importance events total (once per relationship pair),
short of the 10-per-agent §14 needs. **This milestone's `run_world` CLI
needs to be run against the real 4-5 M1 subjects, for a genuinely
week-scale simulation**, before a real trial is possible — see the M1
recruiting open item in `README.md`.

---

## 5. Gate 1

| Outcome | Reading | Action |
|---|---|---|
| ≥ 70% | Fidelity claim holds | Proceed to M5 |
| 56–69% | Weak | Build method D (scenario replay). Re-run M4. Do not proceed. |
| ≤ 55% | **Failed** | Persona capture does not work. Stop feature work. Redesign §2 of `spec.md`. If a second redesign also fails, seriously consider the B2B fork (§16) or stopping. |

Record the result, the date, and the evidence link in `context.md` §11,
assumption A1.

**Also record which of the three Phase 1 outcomes you got** (`context.md` §6):
strong recognition + strong emergence, strong recognition + weak emergence, or
weak recognition + strong emergence. The second is the most likely and means
M5 is where the work is.

---

### M5 — Small world, full social system
**Duration:** 3 weeks
**Goal:** 10–20 agents producing emergence that is interesting to read.

**Scope**
- Scale to 20 agents.
- Reflection and belief formation.
- Memory compression.
- All five conflict triggers; the full bond state machine including Strained,
  Repaired, Broken, Feud.
- Scars and re-escalation.
- Gossip propagation with hop limits and pile-on damping.
- Goal stack, goal coupling, faction detection.
- Exogenous events.
- Tile map — **minimal version only**: grid, walkability, A\* pathfinding,
  proximity. **No renderer.** Movement is real; visuals are not.
- Conflict damping and cooling periods.

**Acceptance tests**
| # | Test | Passes when |
|---|---|---|
| T5.1 | 20 agents, 10,000 ticks | Completes without crash or unbounded memory growth |
| T5.2 | Determinism at scale | Identical streams across runs |
| T5.3 | Edge distribution | Not saturated: Friend+ edges < 40% of materialised edges **[TUNE]** |
| T5.4 | Close bond rarity | ≤ 5% of edges (`spec.md` §6.5) |
| T5.5 | Conflict rate | Within `global_damping_threshold`; damping engages if exceeded |
| T5.6 | All five triggers observed | Each fires at least once in a 10,000-tick run |
| T5.7 | All terminal transitions observed | Repaired, Broken and Feud each occur at least once |
| T5.8 | Scar effect | A second conflict on a scarred theme escalates measurably faster |
| T5.9 | Memory compression | Episodic count stays under cap; beliefs accumulate; protected memories survive |
| T5.10 | Gossip hop limit | No belief propagates beyond 3 hops |
| T5.11 | Pile-on damping | Synthetic pile-on scenario triggers damping and a watch signal |
| T5.12 | Pathfinding | A\* returns optimal paths; unreachable destinations handled |
| T5.13 | Tier shares | Tier 0 ≥ 80%, Tier 2 ≤ 5% |
| T5.14 | Cost per agent-day | Measured and recorded against the §15 budget |
| T5.15 | **Personality persistence** | Recognition Metric re-run at simulated week 1 and week 4; drop < 10 points (assumption A8) |
| T5.16 | Readability | You can read a 3-day summary and follow what happened — **qualitative, but a real gate** |

**Exit criterion:** T5.1–T5.16. T5.15 and T5.16 are the ones that actually
matter; the rest are hygiene.

---

## 6. Phase 2 — Closed multi-owner alpha

Everything here is a problem that only exists once strangers are involved.

### M6 — Hosting, accounts, persistence
**Duration:** 2–3 weeks

**Scope**
- Deploy `core`; the simulation runs unattended.
- Crash recovery: resume from the last committed tick.
- Accounts, auth, the real consent gate.
- Mutual social invitation flow (ADR-007).
- Deletion cascade with receipt.
- `web` repo created: capture UI (method A + B) and a minimal text dashboard.
- Cost instrumentation dashboard.

**Acceptance tests**
| # | Test | Passes when |
|---|---|---|
| T6.1 | 72-hour unattended run | No manual intervention required |
| T6.2 | Kill and restart mid-tick | Resumes from last committed tick; no duplicate events |
| T6.3 | Consent gate | Agent creation refused when flags incomplete |
| T6.4 | Unilateral seeding | Rejected — an edge is only seeded on mutual acceptance |
| T6.5 | **Deletion cascade** | Owner deletion removes all their data; witness events anonymised, not deleted; automated test asserts zero residue (invariant I7) |
| T6.6 | Capture UI | A non-technical person completes method B unaided |
| T6.7 | Cost dashboard | Reports cost per agent-day and tier shares live |

---

### M7 — Safety and moderation for real
**Duration:** 2 weeks

**Scope**
- Platform policy filter with classifier.
- Real-person guard with alerting.
- `ModerationWatcher` with all four emergent-harm thresholds.
- Owner boundary UI.
- Retract-and-hide path for embarrassment events.
- Abuse reporting, including a path for non-users (ADR-007).
- Prompt-injection defence: agent speech strictly as quoted data.

**Acceptance tests**
| # | Test | Passes when |
|---|---|---|
| T7.1 | Red-team persona | A deliberately malicious persona cannot produce policy-violating output |
| T7.2 | Real-person guard | Any utterance naming a real non-owner person is blocked and alerted |
| T7.3 | Emergent targeting | Synthetic scenario triggers damping and mediator injection |
| T7.4 | Runaway feud | Forced cooling engages past threshold |
| T7.5 | **Prompt injection** | An agent emitting instruction-shaped speech does not alter another agent's behaviour — asserted on a controlled scenario |
| T7.6 | Retract-and-hide | Hides an event from all output surfaces within 60 s, while preserving simulation integrity |
| T7.7 | Boundary enforcement | Owner boundary blocks the action and `block_and_notify` reaches the dashboard |

---

### M8 — Owner dashboard (minimum)
**Duration:** 1–2 weeks

**Scope:** daily recap, relationship list with changes, conflicts, goals,
attempted boundary violations, whisper control, override control (rate-limited
and visibly marked).

**Acceptance tests**
| # | Test | Passes when |
|---|---|---|
| T8.1 | Dashboard freshness | ≤ 5 min behind simulation |
| T8.2 | Visibility | No private memories of other agents leak into any view |
| T8.3 | Whisper | Injected as non-binding; a high-`independence` agent demonstrably ignores it sometimes |
| T8.4 | Override marking | Overridden events are visibly flagged in every surface |
| T8.5 | Rate limits | All limits in `spec.md` §12 enforced server-side |

---

### M9 — Closed alpha (Gate 2)
**Duration:** 6–8 weeks of running

**Scope**
- 30–60 invited owners, recruited in **clusters** so seeded friendships are
  exercised (`spec.md` §19.1).
- NDA/confidentiality for all.
- Weekly qualitative interviews — every participant, not a sample.
- A/B: persona-compiled vs. generic agents, to test assumption A3.

**Measured**
| Metric | Assumption tested |
|---|---|
| Unprompted weekly return rate | A3 — **the gate** |
| Persona interview completion rate | A2 |
| Cost per agent-day at real usage | A5 |
| Embarrassment rate | A9 |
| Emergent harm incidents | A6 |
| Newcomer day-7 retention by cohort | A10 |
| Recognition Metric at weeks 1/4/12 | A8 |

**Acceptance tests**
| # | Test | Passes when |
|---|---|---|
| T9.1 | 6 weeks continuous uptime | ≥ 95% |
| T9.2 | All assumptions A2–A10 have recorded measurements | `context.md` §11 updated with dates and evidence |
| T9.3 | Zero unresolved real-person incidents | — |
| T9.4 | Cost within budget | Or a documented plan to bring it in |

---

## 7. Gate 2

**Criterion:** unprompted weekly return (`spec.md` §17) sustained over the final
three weeks, at a rate you would be willing to show an investor.

| Outcome | Action |
|---|---|
| Strong | Proceed to Phase 3. Consider raising (§17). |
| Weak, but qualitative interviews show people care | Diagnose: boring (fix M5 mechanics) or invisible (fix packaging — go to M10 early) |
| Weak, and interviews are flat | Do not build Phase 3. Reconsider the B2B fork (§16). |

---

## 8. Phase 3 — Watchable

**Build order is deliberately counter-intuitive** — the renderer comes last.

### M10 — Highlight engine
**Duration:** 2–3 weeks

**Scope:** importance scoring over the stream, selection, arc grouping, batched
narration, public feed.

**Acceptance tests**
| # | Test | Passes when |
|---|---|---|
| T10.1 | Selection precision | Manual review of 50 selected events: ≥ 80% judged genuinely interesting |
| T10.2 | Arc coherence | Arcs read as one storyline, verified by manual review |
| T10.3 | Narration cost | Batched; cost per world-day within budget |
| T10.4 | Visibility | A `private` owner's agent never appears identifiably in a public feed |
| T10.5 | No leakage | Narration never reveals memories no participant would know |

---

### M11 — Full dashboard and share cards
**Duration:** 2–3 weeks

**Scope:** relationship graph visualisation, agent history, arc following,
share-card rendering.

**Acceptance tests**
| # | Test | Passes when |
|---|---|---|
| T11.1 | Share card | Renders correctly; respects every participant's visibility scope |
| T11.2 | Graph view | Accurately reflects edge states |
| T11.3 | Arc following | Notifies on new beats in a followed arc |

---

### M12 — Tile world and live view (Gate 3)
**Duration:** 4–6 weeks

**Scope**
- Original 32×32 tileset — **no Minecraft-derived assets** (ADR-003).
- Phaser 3 client rendering the tile map.
- Live agent position streaming.
- Spectator entry that requires no account.

**Acceptance tests**
| # | Test | Passes when |
|---|---|---|
| T12.1 | Live view latency | ≤ 2 s |
| T12.2 | Client performance | 60 fps with 60 agents visible on mid-range hardware |
| T12.3 | Map/state consistency | Rendered positions match server state exactly |
| T12.4 | **Art provenance** | Every asset has a recorded origin and licence; zero third-party IP |
| T12.5 | Anonymous spectating | Works with no account and no data collection beyond analytics consent |

---

## 9. Gate 3

**Criterion:** measurable acquisition and return of **non-owner spectators**
(`spec.md` §17).

| Outcome | Reading |
|---|---|
| Spectators return | The entertainment thesis holds. Proceed to Phase 4 at full ambition. |
| Only owners engage | Ceiling is "people who will do a 20-minute interview." Still a business — but a smaller one. Plan Phase 4 accordingly and reset expectations honestly. |

---

## 10. Phase 4 — Open beta and revenue

### M13 — Scale, payments, open beta
**Duration:** 8–12 weeks

**Scope:** horizontal scaling across world instances, out-of-order tick
execution, payments and tiers (`spec.md` §19.4), moderation at volume,
AI-disclosure compliance, support tooling, public launch.

**Acceptance tests**
| # | Test | Passes when |
|---|---|---|
| T13.1 | Load test | 10 worlds × 150 agents within cost budget |
| T13.2 | Payments | Full purchase, upgrade, refund and cancellation paths |
| T13.3 | Moderation at volume | Queue stays clear at projected incident rate |
| T13.4 | Compliance | AI disclosure present on every surface; legal checklist in `spec.md` §18 complete |
| T13.5 | Uptime | 99.5% over 30 days |

---

## 11. Testing strategy

### 11.1 The four test layers

| Layer | Scope | Speed | When |
|---|---|---|---|
| **Unit** | Pure functions: scoring, deltas, state transitions, pathfinding | ms | Every commit |
| **Integration** | Component pairs against a real DB | seconds | Every commit |
| **Simulation** | Full seeded runs with recorded LLM responses | minutes | Every PR |
| **Evaluation** | Recognition Metric, qualitative review | hours/days | Milestone gates |

### 11.2 LLM testing — cassettes

Real LLM calls are non-deterministic and expensive, so they cannot be in the
normal test path.

- Record real responses once into `tests/fixtures/cassettes/`.
- All simulation tests replay cassettes. **No live calls in CI.**
- A separate, manually-triggered suite runs against live models weekly to catch
  provider drift.
- Cassettes are keyed by prompt hash; a prompt change invalidates its cassette
  loudly rather than silently passing.

### 11.3 Determinism testing

Every milestone from M2 onward includes a determinism test. Run the same seed
twice; assert byte-identical event streams. **If determinism breaks, stop and
fix it before anything else** — every other test depends on it.

### 11.4 Property-based testing

Use `hypothesis` for the numeric systems where hand-written cases miss edges:
- Trust never escapes `[-1, 1]`.
- Bond state transitions are always legal from the current state.
- Importance is always in `[0, 1]`.
- Memory count never exceeds the cap after compression.
- Pathfinding never returns a path through a non-walkable tile.

### 11.5 Red-team testing

From M7 onward, maintain a suite of adversarial personas designed to break
containment, produce policy violations, or manipulate other agents. **Grows over
time; never shrinks.** Every real incident becomes a permanent test case.

### 11.6 Qualitative review

Some things cannot be asserted. Formalise them anyway:
- T5.16 readability review.
- T10.1 highlight precision review.
- Weekly alpha interviews.

Record these in a review log with dates and verdicts. A qualitative gate is
still a gate.

---

## 12. Definition of done

A change is done when **all** of these hold:

- [ ] Acceptance tests for the milestone pass.
- [ ] Unit and integration tests for the change pass.
- [ ] Determinism test passes.
- [ ] `ruff` and `mypy` clean.
- [ ] Any new tunable value is in `spec.md` §20 **and** read from config.
- [ ] Any new action is in the registry **and** in `architecture.md` §10 **and**
      has semantics in `spec.md` §10.
- [ ] Any architectural change is reflected in `architecture.md`.
- [ ] Any decision is recorded as an ADR in `context.md`.
- [ ] Any assumption tested has its row updated in `context.md` §11.
- [ ] **README status line and changelog updated** (§14).
- [ ] Milestone status board in this file updated.

---

## 13. Git and PR conventions

### Branches
```
main                      protected; always green; always deployable
feat/<milestone>-<slug>   e.g. feat/m3-relationship-engine
fix/<slug>
docs/<slug>
```

### Commits
Conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`.
Reference the milestone: `feat(m3): materialise relationship edges on first contact`.

### PR template
```markdown
## Milestone
M_

## What changed

## Acceptance tests affected
- [ ] T_._ …

## Docs updated
- [ ] context.md   (ADR / assumption)
- [ ] architecture.md
- [ ] spec.md       (numbers, behaviour)
- [ ] plan.md       (status board)
- [ ] README.md     (status + changelog)  ← REQUIRED ON EVERY PR

## Risk
Which failure mode (F1–F12) does this touch?
```

### Review rules
Solo, so self-review with discipline. **Mandatory pause before merging anything
touching `safety/`** — sleep on it. That directory is the one where a mistake is
not recoverable by a patch.

---

## 14. Documentation maintenance protocol

Per ADR-009: documentation is part of the definition of done.

### The same-PR rule
A behaviour, schema, number or plan change updates its document **in the same
PR** as the code. No follow-up doc PRs — they never happen.

### Which file to update

| Change type | File |
|---|---|
| A decision was made or reversed | `context.md` — new ADR, append-only |
| An assumption was tested | `context.md` §11 — status, date, evidence |
| Component, boundary, data model | `architecture.md` |
| Behaviour rule, threshold, formula, policy | `spec.md` |
| Milestone status, new milestone, changed test | `plan.md` |
| Anything at all | `README.md` — status line + changelog |

### README update rule
**Every merged PR updates the README.** At minimum:
1. The status line (current milestone and state).
2. A changelog entry: date, PR reference, one line of what changed.

If a PR genuinely changes nothing worth noting in the README, it is probably not
worth merging separately.

### Weekly review
Once a week, reread all four documents end to end. They drift. Fix the drift in
a single `docs:` PR. Update the `Last updated` line on any file you touch.

---

## 15. Risk register

| # | Risk | Likelihood | Impact | Mitigation | Early warning |
|---|---|---|---|---|---|
| R1 | Recognition fails at M4 | Medium | Fatal to the thesis | Method D; better capture design | T1.3 shows low trait separation |
| R2 | Cost per agent-day too high | Medium | Fatal to the business model | Tiering, Tier 0 routine, caps | T5.13 tier shares drift |
| R3 | Emergence is boring | **High** | Severe | Exogenous events, scarcity, trait diversity | T5.16 readability review fails |
| R4 | Emergent harm at alpha | Medium | Severe (trust, legal) | Watcher, damping, red-team suite | T7.3 |
| R5 | Building the world too early | **High** (it's the fun part) | Severe — months lost | ADR-008; gates | Catching yourself designing tilesets before Gate 1 |
| R6 | Personality collapse over weeks | Medium | Severe | Persona re-grounding in reflection | T5.15 |
| R7 | Solo burnout | Medium | Severe | Milestones sized to ≤ 3 weeks; gates as natural pauses | Milestones slipping past 1.5× estimate |
| R8 | A funded competitor ships first | Low–Medium | Moderate | Differentiation is persona fidelity, not scale | Prior-art review (do this quarterly) |
| R9 | Consent complaint from a non-user | Low | Severe (legal, reputational) | Mutual opt-in only; reporting path | Any filter-3 hit |
| R10 | Provider model deprecation | Medium | Moderate | Provider abstraction; weekly live-model suite | Live suite diverging from cassettes |

---

## 16. The B2B fork

Keep this option alive at zero cost; do not plan for it.

If consumer retention disappoints but the simulation engine works, the same core
has a real market in **agent-based social simulation** for research, policy
testing and product research. That market is established and funded — there are
research platforms and a Google DeepMind library serving exactly this need.

**What keeps the option open:** keep `core` free of consumer-specific
assumptions. Specifically — no hard dependency on the owner concept inside
`runtime/`, `social/` or `world/`; personas should be injectable from any
source, not only from real owners.

That constraint costs nothing now and preserves an entire alternative business.

---

## 17. Hiring and funding triggers

### First hire — triggered after Gate 2, not before

| If Phase 2's problem was… | Hire |
|---|---|
| "It's boring" | A designer — the product becomes visible in Phase 3 and art direction is judged instantly |
| "It's messy" | Community/moderation — you cannot both build and moderate |

Not a second backend engineer. That is the instinct and it is wrong at this
stage.

### Funding — the natural moment is after Gate 2

Before Gate 2 you have a demo. After it you have retention data from strangers
plus real unit economics — a categorically stronger conversation.

**What the raise story needs:** the Recognition Metric result, unprompted weekly
return, cost per agent-day, and the honest positioning against prior art from
`context.md` §5. Do not pitch "AI agents with free will" — that is Project Sid,
and informed investors will say so.
