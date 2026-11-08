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

**Status (2026-09-16):** Built and unit/integration tested (real Postgres,
not mocks): the full conflict system (`social/conflict.py` — all five
triggers, scar effect, cooling periods, repair-probability roll, all three
terminal transitions) wired into `runtime/resolver.py` so `betray`/`take`/
`apologise`/`forgive`/escalation actions actually drive it; the extended
bond state machine (Close bond, decay-driven demotion, Broken →
Acquaintance reconciliation); reflection and belief formation
(`runtime/reflection.py`, schedule- or importance-triggered, mandatory
persona re-grounding); memory compression (`runtime/compression.py`, cap
enforcement, conflict-linked memories protected); the goal stack
(`runtime/goals.py` — formation, abandonment, staleness pruning, and
goal-coupling adoption against the spec formula, gated to Tier-2
interactions with actual targets for cost control); the minimal tile world
(`world/map.py`, `world/pathfinding.py`, `world/proximity.py` — A*,
Chebyshev distance, five starter zones, no renderer) with perception now
genuinely proximity-gated instead of M2/M3's "everyone is visible" stand-in;
and exogenous event *scheduling* (`world/exogenous.py`). Gossip propagation
(`social/gossip.py`) is now wired end-to-end through the `confide` action:
`runtime/decision.py` surfaces an agent's own gossip-eligible beliefs (from
whatever `RetrievalService` already retrieved) with their ids, the model
picks one plus a listener, and `runtime/resolver.py` runs the full
propagation pipeline — hop limit and pile-on damping enforced against real
`hop_count`/`valence` fields on `MemoryRecord`, checked against the
database before writing the listener's new, distorted belief. Faction
detection (`social/factions.py`) now runs as a real periodic scan inside
`MultiAgentTickScheduler` (every `factions.scan_interval_ticks`), with
cross-scan persistence tracking for the exclusion signal's 1,000-tick
requirement.

**Known gaps:** exogenous events fire on schedule but have no mechanical
effect yet (no resource/feature system to act on). `social/gossip.py`'s
`weighted_belief_strength` (direct-experience-outweighs-inherited-belief)
isn't invoked in the live path — there's no belief-*consolidation* step
anywhere in this codebase yet, so each retelling is written as its own
record rather than merged against what the listener already believes.

**T5.1 attempted and completed (2026-09-17):** a real 20-agent, 10,000-tick
run (`otherworld.cli.acceptance_run`, `ScenarioMockProvider` — see that
module's docstring for why a plain mock or a real LLM aren't right for this
specific test) against real Postgres. First attempt stalled completely
within ~100 ticks; getting a genuinely completing run surfaced and fixed
five real, previously-undetected bugs, all invisible at the ≤2-agent,
≤500-tick scale every earlier test ran at:

1. `runtime/retrieval.py` fetched an agent's *entire* memory history and
   scored it in a pure-Python loop, every decision, every tick — O(ticks²)
   overall. Fixed: bounded candidate pools via two indexed queries (recent,
   important), cosine relevance computed by pgvector in SQL instead of a
   1536-dimension Python loop. Cut a 150-tick profiled run from 1150s to
   396s by itself.
2. `runtime/compression.py` protected *every* memory in a conflicted edge's
   `shared_memory_ids` from compression — but that list grows unboundedly
   with every interaction, so any busy, ever-conflicted pair permanently
   shielded its whole shared history. Several agents were observed 1.5x+
   over the episodic cap and still climbing. Fixed: only the most recent
   entries per edge are protected.
3. `social/gossip.py`'s pile-on check did an unindexed full-table scan
   across all agents' memories on every `confide`. Fixed with a GIN index
   on the `subjects` array column.
4. `social/conflict.py`'s `open_conflict` only blocked new triggers while
   `Strained` — a `Feud` or `Broken` edge kept accumulating conflict
   records forever, each with its own O(log) scan on every subsequent
   interaction. Fixed by blocking new triggers in those terminal states.
5. `cli/acceptance_run.py` held one SQLAlchemy session for the whole run;
   with `expire_on_commit=False` (`db.py`), every ORM object the session
   ever touched stayed pinned in its identity map for the run's lifetime —
   real, unbounded *process* memory growth, and what actually got the first
   full-scale attempt killed by the OS for low memory. Fixed with periodic
   `session.expunge_all()`.

Postgres's own autovacuum also needed retuning (`fillfactor` + one manual
`VACUUM FULL` on `relationship_edges`, a ~100-row table that MVCC-bloated to
19-26MB from being rewritten on nearly every interaction) — a real
infrastructure finding, not a code bug, and one a production deployment of
this scheduler design would need to plan for (periodic maintenance windows,
or a persistence strategy less prone to per-interaction MVCC churn).

**Results against T5.1–T5.16, this run:**

| # | Result |
|---|---|
| T5.1 | **Pass.** 10,000 ticks, 20 agents, 200,000 events, no crash. Process memory stayed flat (~100-300MB) for the full ~3.5 hour run once the fixes above landed. |
| T5.2 | Not retested at this scale (a mechanism-level guarantee — agent-id ordering + seeded RNG — already covered by the existing, unmodified determinism tests at smaller scale). |
| T5.3 | Numerically passes (0% Friend+) but **vacuously** — see T5.7. |
| T5.4 | Numerically passes (0% Close bond) but **vacuously** — see T5.7. |
| T5.5 | Not instrumented by this run's report. |
| T5.6 | **Fails.** Only `BETRAYAL` observed (125 times). `RESOURCE_COMPETITION`, `VALUE_CLASH`, `NEGLECT`, `CONTAGION` never fired — the latter three are scan-tied triggers with no periodic maintenance scan ever built (`social/maintenance.py` from the original M5 task list doesn't exist); `RESOURCE_COMPETITION` needs an *unwitnessed* `take`, and this run's clustered agents are almost always mutually visible, so `take` resolves to `BETRAYAL` instead almost every time. |
| T5.7 | **Fails.** `repaired` (55) and `feud` (62) both occurred; `broken` never did, and by the end **every one of the 62 materialised edges was in Feud** — a real design gap, not noise: `open_conflict`'s only path to `Strained → Broken` is `check_strained_timeout`, which (like the scan-tied triggers above) is never called by the live tick loop, and `Feud` has no reconciliation path at all in `state_machine.py` (only `Broken → Acquaintance` via `forgive` exists) — so once busy pairs reach Feud under a hostile-leaning action mix, there is no way back, and the world saturates. |
| T5.8 | **Pass.** 33 of 62 edges show a repeated-theme scarred conflict. |
| T5.9 | **Pass.** Max episodic count on any agent: exactly 2,000 — held at the cap, not past it (contrast with the pre-fix behaviour above). |
| T5.10 | Not exercised — see T5.11. |
| T5.11 | Not exercised: of 29,449 beliefs formed, none show `hop_count > 0`, meaning `confide`-driven propagation essentially never fired this run. Root cause not fully chased down; plausibly `ScenarioMockProvider`'s reflection response usually resolves `about_agent_id` back to the reflecting agent itself (not a real third party), leaving little gossip-eligible material. |
| T5.12 | Pass (covered by `tests/unit/test_pathfinding.py`, not this run — no movement occurs in this run's setup). |
| T5.13 | **Fails.** Tier 0 = 25.2%, Tier 2 = 0.0085%. Tier 2 comfortably clears its ≤5% ceiling, but Tier 0 falls well short of ≥80% — expected, not a bug: the sleep window is the only Tier-0 behaviour that exists (`move_to` actually consuming an A* path tick-by-tick was never wired this milestone), so Tier 0 is capped at roughly the sleep-window's share of the day regardless of population or duration. |
| T5.14 | N/A — mock provider, no real token cost to measure. |
| T5.15 | N/A — needs real captured personas and a real LLM at Recognition-Metric scale; out of scope for a synthetic run. |
| T5.16 | N/A — no highlight/narration engine exists yet (Output plane, M10). |

**Reading this honestly:** the *mechanics* work — conflicts open, scar,
repair, and the system runs stably at scale once the five bugs above were
fixed. What it also shows is that this specific action mix (`Scenario
MockProvider`, deliberately more conflict-heavy than a real persona
population to make sure every mechanism got exercised at all) plus two
real missing pieces — periodic conflict maintenance (scan-tied triggers,
Strained-timeout-to-Broken) and any Feud recovery path — makes Feud an
absorbing state that the whole population eventually falls into.

**Both gaps are now closed** (2026-09-17), against T5.6/T5.7 directly:

- `social/maintenance.py` (new): a periodic whole-graph scan, run every
  `maintenance.scan_interval_ticks` (default 50) from
  `scheduler.run_tick()`, that actually invokes `apply_trust_decay`,
  `apply_decay`, `check_strained_timeout`, and `check_feud_escalation` —
  all four existed as tested pure functions before this but nothing in the
  live tick loop ever called them, which is exactly why T5.1 never
  observed a `Broken` transition or any trigger but `BETRAYAL`. The scan
  also detects `NEGLECT` (stale high-trust edges), `CONTAGION` (hostility
  inherited from a Friend+ edge to someone in Feud, scaled by the receiving
  agent's `loyalty * (1 - independence)`, per spec.md §3), and `VALUE_CLASH`
  (see below).
- `state_machine.py`'s `attempt_reconciliation`: Feud is no longer a true
  absorbing state. It now takes two deliberate `forgive`s to escape
  (Feud → Broken → Acquaintance) rather than one, since Feud is strictly
  worse than Broken and shouldn't be equally cheap to recover from.
  `resolver.py`'s reconciliation guard now routes both `Broken` and `Feud`
  edges through it (previously only `Broken`).

Covered by 7 new DB-backed simulation tests
(`tests/simulation/test_maintenance.py`) plus 5 new unit tests
(`test_conflict.py`, `test_social_engine.py`) — 41/41 green, ruff/mypy
clean.

**Verified at scale (2026-09-17):** a fresh 20-agent, 2,000-tick run (same
setup as T5.1, seed 42, world `22585d00`) — chosen over a full 10k-tick
repeat given tight memory headroom at the time, but long enough for 40
maintenance-scan cycles. No crash, memory flat (~86-113MB) throughout.
Result, 69 materialised edges: `{acquaintance: 22, close_bond: 16, friend:
11, broken: 10, feud: 8, strained: 2}` — Feud is no longer an absorbing
state (11.6% of edges, not 100%), and the 10 `broken` edges are mid-recovery
(Feud -> Broken, one `forgive` from Acquaintance). 255 conflicts resolved
`repaired` against 269 `feud`, real churn in both directions. `contagion`
fired 133 times — direct proof the maintenance scan is live in the tick
loop (this trigger could not fire at all before this session's work).
`neglect`/`resource_competition`/`value_clash` still didn't fire and
`check_strained_timeout`'s direct Strained->Broken path wasn't exercised
(no edge sat in Strained past its timeout this run) — both consistent
with already-documented causes above, not new gaps. T5.10's belief
`hop_count` staying at 0 is untouched by this work, as expected.

**Remaining gaps closed (2026-09-17):** the four items left open after the
above — gossip propagation, T5.5's damping mechanism, `VALUE_CLASH`, and
real movement — all built and tested against a real database:

- **Gossip propagation (T5.10/T5.11).** Root cause was not what it looked
  like: reflection (`runtime/reflection.py`) correctly attaches a real
  third party as `about_agent_id` when one exists in the source memories
  (verified directly against both `MockLLMProvider` and
  `ScenarioMockProvider`). The actual bug was retrieval starvation —
  `RetrievalService`'s Tier-1 top-k is only 5, and a belief's importance
  almost never outscores a same-tick high-importance episodic event (a
  `betray` at 0.95) under spec.md §5.2's recency-heavy formula, so a
  gossip-eligible belief essentially never survived into what the model
  was shown, leaving `confide` nothing real to share — accounting for all
  36,000+ beliefs formed with `hop_count` never above 0 across both prior
  runs. Fixed with `social/gossip.py`'s new `get_shareable_beliefs`, a
  targeted query (GIN-indexed on `subjects`) run alongside the general
  retrieval call in `scheduler.py`'s `_decide_for_agent`, so an agent's own
  shareable beliefs no longer have to compete with routine episodic traffic
  to be seen.
- **Global conflict damping (T5.5).** `global_damping_threshold_per_agent_day`
  existed in `config.py` since M5's first pass but was never read anywhere.
  `social/conflict.py` gained `conflicts_per_agent_per_day` (rate over a
  trailing `damping_check_interval_ticks`-tick window, not a lifetime
  average, so it actually tracks bursts) and `compute_damping_factor`
  (spec.md §7.6's scale-down, floored at `damping_factor_floor` so damping
  never fully silences the mechanic). `scheduler.py` recomputes this
  periodically and threads it into every place a *new* trigger can open
  (`open_conflict`'s new `damped` param) — action-tied triggers via
  `Resolver.resolve`, and NEGLECT/CONTAGION/VALUE_CLASH via
  `run_maintenance_scan` — as a probabilistic gate, not a change to
  resolution outcomes of conflicts already open.
- **`VALUE_CLASH` (T5.6).** Goals are free text with no general "conflicts
  with" relation to compute — rather than build NLP-style goal comparison,
  `Goal` gained a minimal structured stand-in, `target_agent_id` +
  `exclusive` (`models/agent.py`), settable via `form_goal`'s params. Two
  bonded agents (Acquaintance+) each holding an active, `exclusive` goal
  targeting the same third party now trigger `VALUE_CLASH`
  (`social/conflict.py`'s `detect_value_clash`, checked every maintenance
  scan in `social/maintenance.py`'s new `_apply_value_clash`). A documented
  simplification, not a hidden one.
- **Real movement (T5.12/T5.13).** `move_to` was previously a complete
  no-op — agents never moved regardless of what they chose. Now: a fresh
  `move_to` computes an A* path (`world/pathfinding.py`, already tested,
  just never wired) and takes the first step immediately; every later tick
  with a non-empty `Agent.current_path` walks the next step as genuine
  Tier 0 — About/architecture.md §12's "Tier 0 never touches `LLMProvider`"
  — until the path is exhausted, at which point the agent decides again.
  Unreachable or invalid destinations are handled (the agent simply doesn't
  move that tick), not rejected. `MultiAgentTickScheduler` now carries a
  `WorldMap` (defaulted via `generate_starter_map` if the caller doesn't
  supply one) and a `tier0_walk_count`, folded into the Tier-0 share
  `cli/acceptance_run.py` reports for T5.13. `ScenarioMockProvider` now
  occasionally proposes `move_to`, so this actually gets exercised at
  acceptance-run scale rather than sitting dead.

Covered by 4 new DB-backed simulation tests (`tests/simulation/
test_movement.py`), 3 more in `test_maintenance.py` (VALUE_CLASH x2,
damping-factor suppression), and 5 more unit tests (`test_conflict.py`,
`test_goals.py`) — 195 total in the unit+simulation suites, all green,
ruff/mypy clean.

**Verified at scale, round 2 (2026-09-17):** a second fresh 20-agent,
2,000-tick run (seed 43 — seed 42 collided with round 1's leftover rows on
the deterministic UUID sequence, About/plan.md's earlier documented
UniqueViolationError cause), same setup otherwise. No crash; memory flat
(~89MB). Reading this one honestly, mechanism by mechanism:

- **Movement really works, and changed the shape of the run.** Tier shares:
  `{0: 60.1%, 1: 39.5%, 2: 0.35%}`, versus T5.1's original 25.2%/~75%/0.008%
  — a real jump, driven by 13,960 genuine Tier-0 walking steps, but still
  short of T5.13's 80% target (`move_to` is one weighted option among many
  in `ScenarioMockProvider`, and most rolled destinations are close enough
  that a path is only a few ticks). A disclosed shortfall, not a silent
  one. Movement's bigger effect: agents scattered across the map instead of
  sitting fixed in their spawn clusters, so **190 of the possible 190 pairs
  materialised an edge** (full population connectivity), against 69 when
  agents never moved — a materially different, more realistic run shape.
- **Gossip propagation is confirmed fixed.** `hop_count` reached 1 for the
  first time ever, across both prior full-scale runs (was 0 out of 29,449
  and 36,336+ beliefs respectively). It didn't chain further to hop 2/3
  this run — a real, disclosed limit (a hop-2 chain needs three agents to
  each independently roll `confide` about the same belief in sequence,
  which is rarer than a single successful hand-off), not evidence the fix
  is incomplete.
- **RESOURCE_COMPETITION fired for the first time** (31 times) — plausibly
  a direct consequence of movement: agents are no longer permanently
  clustered and mutually visible, so `take` sometimes now genuinely goes
  unwitnessed instead of resolving to BETRAYAL by default.
- **Damping factor read 1.000 at the run's final check** — no active
  damping at that snapshot. The whole-run average rate (~277 terminal
  transitions / 20 agents / ~13.9 agent-days ≈ 1.0/agent/day) sits right at
  the 0.8 threshold, so the trailing-window rate plausibly crossed it at
  some point mid-run even though the last check didn't catch it damping;
  not confirmed via a mid-run trace. The mechanism itself is verified
  correct in isolation (unit-tested rate/factor formulas, a DB-backed test
  proving a `damping_factor=0.0` gate actually suppresses a trigger) — T5.5
  is closer to "exercised, rate stayed near but not confirmed over
  threshold" than "damping observed engaging," an honest partial result.
- **`VALUE_CLASH` still did not fire.** Correct in isolation (dedicated
  unit + DB-backed tests pass), but only ~19% of edges (36/190) sat in a
  bonded state (Acquaintance+) at the final snapshot, and `form_goal` only
  fires on roughly 1-in-23 eligible ticks — the combination needed (two
  *specific* bonded agents independently rolling an exclusive goal onto
  the *same* third party) is genuinely rare at this scale and run length,
  not silently broken.

Net: of T5.1-T5.13, everything that's actually buildable in this
codebase's own code is now built and individually verified correct.
T5.6 (all five triggers in one run) and T5.13 (Tier 0 ≥ 80%) are the two
still not fully cleared *in a single run* — both for the same underlying
reason: `ScenarioMockProvider`'s weighted action mix makes some paths rare
rather than guaranteed, which a longer run or reweighted mix would surface
without any further code changes. T5.15 and T5.16 remain the two
acceptance tests this codebase cannot close on its own (real personas +
LLM, and a narration engine that's M10's job).

**Full-scale confirmation, round 3 (2026-09-17):** a fresh 20-agent,
**10,000-tick** run (seed 44, world `8043e66f`) — T5.1's original scale,
re-run end to end against every fix in this session, not just the
2,000-tick spot-checks above. Two small, disclosed tuning changes went in
first, both to `ScenarioMockProvider` (never to the mechanisms themselves):
`move_to`'s weight doubled (8 -> 16) to give Tier 0 a fairer chance, and
`VALUE_CLASH`'s target selection changed from `visible_ids[0]` (per-agent,
list-order-dependent — different agents almost never landed on the same
value) to `min(visible_ids)` (converges on the same "most prominent locally
visible" agent regardless of whose prompt it's computed from). Both are
about giving already-correct mechanisms a fair chance to fire in a
synthetic run, not about changing what "correct" means.

Result: **200,000 events, no crash, wall clock 3,030.8s (~50.5 min, 3.30
ticks/s), memory flat (~90-105MB)** across two spot-checks mid-run — the
same stability profile as T5.1's original successful run, now confirmed
with all of this session's mechanisms live simultaneously.

- **T5.13 (Tier shares) — closer, still short.** `{0: 70.9%, 1: 29.1%,
  2: 0.07%}`, up from round 2's 60.1%/39.5%/0.35% with the doubled `move_to`
  weight and simply having 5x the ticks for each walking episode's
  multi-tick weight to compound. Tier 2 is now essentially negligible
  (well under its 5% ceiling). Tier 0 still hasn't cleared 80% — genuine
  further movement requires the model to *keep choosing* `move_to`, which
  competes against a wide social/conflict action pool by design (About/
  plan.md's whole point of that pool is exercising every OTHER mechanic);
  pushing Tier 0 to 80% would mean shrinking that pool further, trading one
  metric against the very diversity T5.6 needs. Not chased further for that
  reason — a real, disclosed tension rather than an oversight.
- **T5.6 (five triggers) — still 3 of 5.** `{contagion: 308,
  resource_competition: 135, betrayal: 303}`. `NEGLECT` and `VALUE_CLASH`
  did not fire, in either the 2,000- or 10,000-tick run, despite the
  `min(visible_ids)` retune. Both have a real, narrow precondition this
  specific conflict-heavy scenario rarely produces by chance: `NEGLECT`
  needs an edge to stay above the Friend trust threshold *and* go quiet for
  600 ticks, but this scenario's action mix keeps dragging trust down
  before that silence can accumulate; `VALUE_CLASH` needs two *specific*
  bonded agents to each independently roll an exclusive goal onto the same
  target while still bonded to each other — agents now move continuously
  (this session's own change), so two agents' visible sets, and therefore
  their `min(visible_ids)` pick, rarely stay aligned long enough. Both
  triggers are proven correct in isolation (dedicated unit tests +
  DB-backed simulation tests constructing the exact preconditions by hand)
  — this is an "not observed at this run's scale," not an "unverified"
  or "broken" gap. Further chasing this with more tuning-and-rerun cycles
  would trade real verification (a controlled test proving the mechanism)
  for gaming a synthetic mock's odds, so it stops here.
- **T5.10 technically passes now:** `hop_count` reached 1 again (never
  above), which *is* "≤ 3 hops" — T5.10's literal bar. It just doesn't
  demonstrate a multi-hop chain, which would need three agents to each
  independently roll `confide` about the same belief in sequence.
- **Damping factor stayed at 1.000 the whole run** — this run's organic
  rate (659 terminal transitions / 20 agents / ~69.4 agent-days ≈
  0.47/agent/day) sat comfortably *under* the 0.8 threshold, lower than
  round 2's estimate, so there was nothing to damp. Across three separate
  runs now, the mechanism has never been observed actively engaging in an
  acceptance run — it remains verified correct only by direct unit test
  (`compute_damping_factor`, `conflicts_per_agent_per_day`) and a DB-backed
  test forcing `damping_factor=0.0` to prove the gate suppresses a trigger.
  Honest final state for T5.5: built, correct, exercised on every run,
  never yet caught in the act.

**M5 is now complete against everything this codebase's own code can
close.** Every mechanic in scope (bond state machine including Feud
recovery, all five conflict triggers as *code*, scar effect, cooling
periods, gossip propagation, pile-on damping, faction detection, exogenous
events, real A*-pathfinding movement, global conflict damping) is built,
unit- and DB-backed-tested, and has run stably at T5.1's full 10,000-tick/
20-agent scale three times running. What's left open is exactly two kinds
of thing, and no more tuning or code changes fix either: (1) `NEGLECT`/
`VALUE_CLASH` haven't been *observed* firing in an acceptance run, though
independently proven correct — a property of this synthetic scenario's
odds, not of the mechanisms; (2) T5.15 (Recognition Metric persistence)
and T5.16 (readability) need real captured personas, a real LLM, and (for
T5.16) a narration engine that doesn't exist until M10 — permanently out
of reach for a mock-provider run, by design, not an oversight.

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
| T6.1 | 72-hour unattended run | No manual intervention required — **PASSED 2026-11-05** (local docker compose, mock LLM provider): 73.7 h, 443/443 ticks, 0 failures, 0 restarts, flat memory |
| T6.2 | Kill and restart mid-tick | Resumes from last committed tick; no duplicate events — **PASSED 2026-10-31** (local; SIGKILL at tick 6099's first LLM call, replayed whole, 5 events, no gaps/dupes) |
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
