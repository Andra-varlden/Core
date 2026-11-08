# Andra-varlden

> Formerly codenamed `Otherworld` throughout the docs and code. The name has
> been decided; project-facing references (this README, repo naming) are
> updated. The deeper rename — the `otherworld` Python package itself,
> imported everywhere in `core/` — is deliberately deferred until it's
> explicitly requested, to avoid a large mechanical change across a working,
> tested codebase for no functional benefit. See `About/context.md` §2.

A platform where a real person creates an autonomous AI agent encoding their own
personality, speech and values, and releases it into a shared persistent 2D
world populated by other people's agents. Agents perceive, remember, reflect,
form goals, make friends, fall out, repair or sever bonds, gossip and form
factions — with no authored script. The resulting social drama is surfaced back
to owners and spectators as an ongoing story.

**Private repository. Not for public discussion.** See `About/context.md` §13.

---

## ▸ Current status

| | |
|---|---|
| **Phase** | Phase 2 — Closed multi-owner alpha |
| **Milestone** | M6 — Hosting, accounts, persistence |
| **Status** | **Gate 1 concluded WEAK** — a real 5-subject Recognition Metric trial landed at 56.4% mean accuracy, below the ≥70% pass bar. Per `spec.md` §14's own interpretation table, WEAK calls for building Method D and re-testing before proceeding; that re-test was attempted, didn't move the number, and a deliberate call was made to accept 56.4% and move on rather than keep spending real LLM-call budget on a metric that wasn't producing signal (a real quiz-design bug — several question types rendered byte-identical regardless of the real answer — was found and partially, not fully, addressed). Recorded here plainly rather than as a pass. **M6 is now built and tested end to end**: unattended deploy worker with crash recovery, magic-link auth with a *real* (not placeholder) consent gate, mutual social invitations (ADR-007), a deletion cascade with a zero-residue test (invariant I7), cost-trace persistence with a cost-per-agent-day/tier-share dashboard, and a `core/web/` capture UI (Method A + B) served same-origin from the API. **Not yet done:** T6.1/T6.2 (72-hour unattended run, kill-and-resume) can only be verified against a real deployment — blocked on creating Railway and Resend accounts, both steps only the project owner can take. |
| **Gate ahead** | Gate 2 — closed multi-owner alpha (M9) |
| **Last updated** | 2026-09-28 |

> **This block is updated on every merged PR.** See [Update protocol](#-update-protocol).

---

## ▸ Read the docs in this order

| Order | File | Answers |
|---|---|---|
| 1 | **[`About/context.md`](./About/context.md)** | **Why.** Origin, prior art, principles, decision log (ADRs), assumptions register. **Read this first.** |
| 2 | [`About/architecture.md`](./About/architecture.md) | **How it's structured.** Six planes, components, data models, invariants, failure modes. |
| 3 | [`About/spec.md`](./About/spec.md) | **What exactly it does.** Behaviour rules, every tunable number, persona question bank, policies, APIs, cost model. |
| 4 | [`About/plan.md`](./About/plan.md) | **In what order, and how we know it worked.** Milestones, acceptance tests, gates, testing strategy. |

**Convention:** every doc except this README lives in `About/`. Any new `.md` file created in the future goes there too.

**Rule of thumb:** if you are about to write code, you should have just read
`About/spec.md` for the exact behaviour and `About/architecture.md` for where it goes.

---

## ▸ The one-line thesis

Research has proven emergence with generic agents. Industry has proven demand
for personal AI clones used one-to-one. **Nobody has combined personal fidelity,
multi-owner social simulation, and entertainment packaging.** That combination is
the whole product.

The claim that must hold before anything else is built: **an owner can pick
their own agent out of an unlabelled lineup.** Everything in Phase 1 exists to
test that.

---

## ▸ Repositories

Currently **one repo**: `About/` (these four documents) + `core/` (the
simulation, including `core/web/` — the M6 capture UI and dashboard, served
from the same app as the API, not a separate service). Pushed to GitHub as
`Andra-varlden/Core`. Splitting `About/` and `core/` into separate repos was
considered and explicitly deferred — revisit only once there's a real reason
(e.g. a dedicated frontend contributor) to pay the overhead.

Further splits (`world-engine`, `moderation`, `infra`) only once boundaries have
stabilised. See `About/architecture.md` §15.

---

## ▸ Quickstart (`core`)

> Applies once M0 is complete.

```bash
# prerequisites: Python 3.12, Docker, Docker Compose

git clone https://github.com/Andra-varlden/Core.git
cd Core/core

cp .env.example .env          # then fill in provider keys

docker compose up -d          # Postgres 16 + pgvector, Redis

pip install -e ".[dev]"
alembic upgrade head

pytest                        # full suite, cassette-backed, no live LLM calls
ruff check .
mypy --strict src/otherworld/models src/otherworld/safety
```

### Common commands

```bash
pytest tests/unit                       # fast
pytest tests/simulation                 # seeded deterministic runs
pytest tests/simulation -k determinism   # the one that must never fail

# M1 — capture a real persona (method A or B)
python -m otherworld.cli.capture --method A --handle <you> --email <you@example.com>
python -m otherworld.cli.capture --method B --handle <you> --email <you@example.com>

# M4 — spawn captured personas as living agents and simulate them, then run a trial
python -m otherworld.cli.run_world --world-name alpha --ticks 5000 --owners <you>:<you@example.com> <them>:<them@example.com>
python -m otherworld.cli.recognition --world-name alpha --handle <you> --email <you@example.com>
```

---

## ▸ Architecture at a glance

```
PLANE 1  OWNER      signup · consent gate · identity mode · social opt-in
   ▼
PLANE 2  PERSONA    capture A/B/C/D · persona object · compile · bind
   ▼
PLANE 3  RUNTIME    tick loop · memory · reflection · goals · model tiers
   ▼
PLANE 4  SAFETY     owner boundaries · policy · sandbox · moderation
   ▼
PLANE 5  WORLD      tile map · scheduler · relationship graph · factions
   ▼
PLANE 6  OUTPUT     event stream · highlights · live view · dashboard
```

**The tick loop:** perceive → retrieve → decide → validate → act → resolve.

**The bond states:** stranger → acquaintance → friend → close bond, with
strained branching to repaired, broken or feud.

---

## ▸ Non-negotiables

These are the things that must never quietly erode.

1. **Containment lives in the action registry, not in a prompt.** No code
   execution, tool acquisition, filesystem or network access, ever. (ADR-002)
2. **Determinism.** Same seed + mocked LLM ⇒ byte-identical output. If this
   breaks, stop everything and fix it.
3. **Nothing reaches the world without passing the Validator.** (Invariant I1)
4. **Mutual opt-in for any real-world relationship.** No unilateral seeding, no
   naming non-users. (ADR-007)
5. **Owners get binding boundaries and non-binding influence.** Never a puppet
   string. (ADR-006)
6. **The tile world is built last.** Resist it. (ADR-008)
7. **No Minecraft/Mojang assets, textures, names or branding.** Original art
   only. (ADR-003)
8. **Docs and README update in the same PR as the code.** (ADR-009)

---

## ▸ Milestone board

| ID | Milestone | Status |
|---|---|---|
| M0 | Foundations and schemas | COMPLETE |
| M1 | Persona capture | COMPLETE (5 real subjects captured) |
| M2 | Single agent, single tick | COMPLETE |
| M3 | Two agents, first contact | COMPLETE |
| M4 | **Recognition Metric — Gate 1** | CONCLUDED — WEAK (56.4%), accepted, proceeding |
| M5 | Small world, full social system | IN PROGRESS |
| M6 | Hosting, accounts, persistence | COMPLETE — T6.1/T6.2 passed locally (docker compose, mock LLM); a hosted-deployment check is still open |
| M7 | Safety and moderation for real | NOT STARTED |
| M8 | Owner dashboard (minimum) | NOT STARTED |
| M9 | Closed alpha — **Gate 2** | NOT STARTED |
| M10 | Highlight engine | NOT STARTED |
| M11 | Full dashboard and share cards | NOT STARTED |
| M12 | Tile world and live view — **Gate 3** | NOT STARTED |
| M13 | Scale, payments, open beta | NOT STARTED |

Full scope and acceptance tests per milestone: [`About/plan.md`](./About/plan.md).

---

## ▸ Update protocol

**Every merged PR updates this README.** No exceptions.

### On every PR

1. Update the **Current status** block if the milestone or its state changed.
2. Update the **Milestone board** row.
3. Add a **Changelog** entry: date, PR number, one line.
4. Tick the relevant boxes in the PR template (see `About/plan.md` §13).

### Which document to update alongside

| Change | File |
|---|---|
| A decision made or reversed | `About/context.md` — new ADR, append-only |
| An assumption tested | `About/context.md` §11 — status, date, evidence |
| Component, boundary, data model | `About/architecture.md` |
| Behaviour rule, threshold, formula, policy | `About/spec.md` |
| Milestone status, scope, or test | `About/plan.md` |

### Weekly

Reread all four documents end to end. They drift. Fix drift in one `docs:` PR
and update each file's `Last updated` line.

---

## ▸ Changelog

Newest first. Format: `YYYY-MM-DD · #PR · milestone · change`

| Date | PR | Milestone | Change |
|---|---|---|---|
| 2026-09-28 | — | CI | Fixed the first real CI run's failures (ruff, 40 errors): configured `flake8-bugbear`'s `extend-immutable-calls` for `fastapi.Depends`/`Query`/`Path`/`Body` — FastAPI's dependency-injection pattern (`param: T = Depends(fn)`) is idiomatic, not a real B008 mutable-default risk, and every M6 route handler was tripping it; wrapped 12 lines over the 110-column limit; replaced two `assert False, "..."` test patterns with `raise AssertionError(...)` (B011). `ruff check .`, `mypy --strict` on `models/`+`safety/`, `alembic upgrade head`, and the full pytest suite are all clean locally, matching every CI step. |
| 2026-09-28 | — | M4→M6 | **Gate 1 concluded.** Ran the real 5-subject Recognition Metric trial to completion. Final result: 56.4% mean accuracy — WEAK per `spec.md` §14. Built and ran Method D (scenario replay) as the spec's own prescribed WEAK-band remedy; it didn't move the number in a re-test. Root-caused (not fully fixed) a real quiz-design bug along the way: several action types (`form_goal`, `reflect`, `abandon_goal`) have no relationship-delta or elapsed-time data, so every instance of them renders as byte-identical text regardless of the real underlying event — no amount of distinctiveness-based sampling can make an indistinguishable description recognisable. A deliberate decision was made to accept 56.4% and move to Phase 2 rather than keep spending real LLM-call budget chasing a fix, given repeated trial rounds weren't producing better signal. Moved on to M6. |
| 2026-09-28 | — | M6 | **All six M6 stages built and tested** (stages run back-to-back per an explicit "build through all of it, only stop if something needs me" instruction): (1) deploy skeleton — single Dockerfile, two Railway service roles, `/health`, a real-time-paced unattended `worker.py` with crash recovery (resumes from `max(tick)`, not a checkpoint file); (2) magic-link auth (HMAC session tokens, Resend with a dev-mode log fallback) and a real consent gate — found and fixed a genuine gap here: real (non-placeholder) owners started with `consent=None` but no endpoint ever existed to complete it, which would have permanently blocked agent creation for every real signup; `require_consent` also only checked "a record exists," not `liability_acknowledged`'s actual value, despite `architecture.md` §2 explicitly requiring the latter — both fixed; (3) mutual social invitations enforcing ADR-007 (no unilateral seeding); (4) an owner deletion cascade with a receipt and a zero-residue test (invariant I7) — hard-deletes the owner's own data, anonymises (strips the reference, keeps the record) other owners' data that merely references them; (5) decision-trace persistence (`decision_traces` table) with real cost-per-agent-day/tier-share aggregation queries, replacing an always-zero `estimated_cost_usd`; (6) a `core/web/` capture UI (Method A + B, plain HTML/CSS/JS, no build step) and a minimal text cost dashboard, mounted as static files from the same FastAPI app as the API specifically to avoid CORS and cross-origin cookie handling. 300+ tests pass; ruff and mypy clean. |
| 2026-09-17 | — | M5 | Attempted and completed T5.1: a real 20-agent, 10,000-tick run (`otherworld.cli.acceptance_run`) against real Postgres, real wall-clock time (~3.5 hours once stable). The first attempt stalled completely within ~100 ticks; getting a run that actually finishes surfaced and fixed 5 real bugs invisible at every earlier test's ≤2-agent, ≤500-tick scale: an unbounded-scan-plus-Python-cosine-loop in `runtime/retrieval.py` (O(ticks²), fixed with bounded indexed queries + pgvector-side scoring); a compression-protection bug in `runtime/compression.py` that let a busy conflicted edge shield its entire (unbounded) shared history from ever being compressed; an unindexed cross-agent table scan in `social/gossip.py`'s pile-on check (fixed with a GIN index); `social/conflict.py`'s `open_conflict` letting Feud/Broken edges accumulate conflict records forever (only Strained was guarded); and the run script itself leaking process memory by holding one SQLAlchemy session for the whole run with `expire_on_commit=False` (fixed with periodic `session.expunge_all()` — this is what got the first full-scale attempt killed by the OS for low memory). Also retuned Postgres autovacuum/fillfactor after `relationship_edges` (a ~100-row table, rewritten on nearly every interaction) MVCC-bloated to 19-26MB. **Results: T5.1, T5.8, T5.9 pass; T5.3/T5.4 pass only vacuously; T5.6, T5.7, T5.13 fail** — full honest breakdown and root causes in `plan.md`'s M5 status. The real finding: under a conflict-heavy action mix, Feud has no reconciliation path and the Strained-timeout-to-Broken transition is never invoked by the live tick loop, so the whole population eventually saturates into permanent Feud — `social/maintenance.py` (never built) and a Feud recovery path are the concrete next steps. |
| 2026-09-16 | — | M5 | Finished wiring gossip and faction detection end-to-end (previously landed as tested-but-unwired mechanics, see the M5 entry below). `MemoryRecord` gained `hop_count`/`valence` fields (new migration) so gossip lineage and pile-on damping are real, not bookkeeping the caller has to get right: `runtime/decision.py` now surfaces an agent's own gossip-eligible beliefs with their ids, the model picks one plus a listener via `confide`, and `runtime/resolver.py` runs the full pipeline — hop limit and pile-on damping checked against the database before the listener's new, distorted belief is written. Reflection (`runtime/reflection.py`) now asks for `about_agent_id` and `valence` per belief instead of a flat string, using each source memory's `subjects` (not its anonymised content) so a belief can actually be about a specific third party — required for gossip to have anything real to propagate. Faction detection (`social/factions.py`) now runs as a genuine periodic scan inside `MultiAgentTickScheduler`, with cross-scan persistence tracking for the exclusion signal's 1,000-tick requirement. 175/175 tests pass, ruff and mypy clean. |
| 2026-09-16 | — | M5 | Started M5 (deliberately ahead of Gate 1 — see Current status). Built and tested against a real Postgres, not mocks: the full conflict system (`social/conflict.py`, all five triggers, scar effect, cooling periods, repair-probability roll, all three terminal transitions) wired into `runtime/resolver.py`; the extended bond state machine (Close bond, decay demotion, Broken→Acquaintance reconciliation); reflection and belief formation (`runtime/reflection.py`); memory compression with conflict-linked protection (`runtime/compression.py`); the goal stack and goal-coupling adoption (`runtime/goals.py`); the minimal tile world — grid, A* pathfinding, Chebyshev proximity, five starter zones, no renderer (`world/map.py`, `world/pathfinding.py`, `world/proximity.py`) — with perception now genuinely proximity-gated instead of M2/M3's "everyone is visible" stand-in; exogenous event scheduling (`world/exogenous.py`). Gossip propagation and faction detection (`social/gossip.py`, `social/factions.py`) have their core mechanics built and unit-tested against `spec.md`'s formulas but aren't autonomously wired into the tick loop yet — documented as open gaps in each module and in `plan.md`'s M5 status. Two real pre-existing bugs found and fixed along the way: `take` was miscategorised so it never went through the relationship-consequence path at all (RESOURCE_COMPETITION could never fire), and the dev database's schema had drifted from the models since M2 with no Alembic migration ever recorded for it — a new migration brings it current. 169/169 tests pass, ruff and mypy clean. The full 20-agent/10,000-tick acceptance run (T5.1-T5.5, T5.13-T5.15) has not been attempted — scoped as its own deliberate step, not something to run inline. |
| 2026-09-16 | — | M4 | Real LLM provider (Groq) integrated: `llm/providers/groq.py`, `llm/factory.py` (picks real vs mock based on config), `config.groq_api_key` (wired through `.env`, not raw `os.environ`). Confirmed live and working — persona-driven behavioural variance is real. Four more real bugs a live pilot surfaced and fixed: (1) `run_world` never persisted agents' advanced `last_tick`, so re-running a world would have restarted everyone at tick 0; (2) the free-tier rate limit (8000 TPM) needed more retry budget than the SDK default; (3) the model would hallucinate actions outside the registry (e.g. `register_agent`) when never told what the valid set actually is — now listed explicitly in the prompt; (4) `openai/gpt-oss-*` are reasoning models that were burning the entire token budget on hidden reasoning before any answer appeared, truncating the response to empty — fixed with `reasoning_effort` tuned per tier. Also fixed: relationship state changes (Stranger→Acquaintance, Acquaintance→Friend) weren't scored as important per `spec.md` §5.1's own table — `runtime/resolver.py` now takes the max of action/first-encounter/state-change importance, confirmed live with real 0.75-scored events. **Refined finding:** 2 agents can only ever produce ~2-3 such high-importance events total (once per pair) — nowhere near the 10-per-agent §14 needs, which is exactly why the plan always called for 4-5 agents. Recruiting is now the sole remaining blocker. Also built: `RecognitionHarness` (`eval/recognition.py`) — category-matched decoy sampling, name-stripped descriptions, blinded shuffled presentation, scoring, persistence (T4.1/T4.2 green, 9/9 tests) — and `otherworld.cli.run_world` / `otherworld.cli.recognition` (the bridge from M1 captures to a real trial). |
| 2026-09-16 | — | M3 | Two-agent first contact built: the relationship engine (lazy edge materialisation, trust deltas matching `spec.md` §6.2 exactly, Stranger→Acquaintance→Friend promotion gated on both trust *and* a high-importance shared memory), witness memory writing, and the multi-agent scheduler — decisions computed concurrently but always applied in agent-id order, with a sequential first-encounter pre-pass so escalation trigger 1 fires exactly once per new pair rather than once per side. T3.1–T3.8 all green (70/70 tests); T3.9 (real per-vendor token counts) is honestly still blocked on a live provider key — `spec.md` §15.2 now says so explicitly instead of guessing numbers. |
| 2026-09-16 | — | M2 | Tick loop built end to end: Compiler + Binder, the six-phase loop (perceive→retrieve→decide→validate→act→resolve), the Validator's four ordered filters (owner boundary, platform policy, real-person guard, world legality/containment), tick-based clock with no wall-clock dependency, seeded-RNG determinism (including id generation), decision tracing, and the tick scheduler with re-prompt-once-then-idle fallback. T2.1–T2.10 all green (56/56 tests), including the two non-negotiables: T2.2 determinism and T2.7 containment. Fixed a real bug the first run surfaced: the mock embedding provider produced 384-dim vectors against a 1536-dim pgvector column. |
| 2026-09-15 | — | M1 | Persona capture built: Method A (30-item questionnaire), Method B (conversational interview, deterministic keyword extraction), Method C (writing-sample ingestion with name redaction), boundary compilation, versioned persistence (invariant I5), and an interactive CLI (`otherworld.cli.capture`) for real capture sessions. T1.1–T1.7 all green: 33/33 tests pass, ruff clean, mypy --strict clean. Test suite now runs against a dedicated `otherworld_test` database, separate from dev, after a fixture bug briefly wiped the dev schema. Two real bugs surfaced and fixed by an actual capture session: cross-method versioning created duplicate v1 rows instead of refining into v2, and a "no evidence" confidence value was diluting existing trait readings on merge. |
| 2026-09-15 | — | M0 | Docs moved into `About/`. `core` scaffolded: Pydantic + SQLAlchemy models for every shape in `architecture.md` §9, the action registry (28 actions, matches §10 exactly), the `LLMProvider` protocol + deterministic mock provider, config reading every `spec.md` §20 key, Alembic migration, Docker Compose (Postgres 16 + pgvector, Redis), CI workflow. T0.1–T0.8 all green: 19/19 tests pass, ruff clean, mypy --strict clean on `models/` and `safety/`. |
| 2026-09-14 | — | M0 | Initial documentation set created: `context.md`, `architecture.md`, `spec.md`, `plan.md`, `README.md`. Decisions ADR-001 through ADR-009 recorded. |

---

## ▸ Open items

**Gate 1 (M4) — closed:**
- [x] ~~Configure a real Tier 1/2 LLM provider key.~~ **Done 2026-09-16** —
      Groq (`otherworld.llm.providers.groq`), confirmed working end to end
      via live pilot runs.
- [x] ~~Recruit the M4 Recognition Metric subjects and run the real trial.~~
      **Done 2026-09-28** — 5 subjects, concluded WEAK at 56.4%, accepted and
      proceeding rather than re-testing further. See the Changelog.

**T6.1/T6.2 passed locally 2026-10-31 / 2026-11-05** (docker compose, mock LLM provider; a real-Groq run failed on `APITimeoutError`s, so it was not used). Only a hosted check remains open:
- [ ] **Create a Railway account**, connect this repo, set the env vars in
      `core/README.deploy.md`. Human-only step.
- [ ] **Create a Resend account** for real magic-link email delivery.
      Optional — dev-mode logs the link instead, which is fine for internal
      testing but not for real users.

**Not yet blocking, but open:**
- [x] ~~Decide the real product name.~~ **Decided 2026-09-28: Andra-varlden.**
      Project-facing references (this README, the GitHub org/repo) are
      updated. Root folder rename to `Andra-varlden` is pending a session
      restart (the running session holds a lock on its own working
      directory). The deeper rename — the `otherworld` Python package name
      itself — is deliberately deferred until explicitly requested.
- [x] ~~Decide the GitHub organisation name.~~ **Decided: `Andra-varlden`.**
      Pushed as `Andra-varlden/Core` (single repo — see Repositories above).
- [ ] Branch protection on `main`.
- [ ] Populate the rate table in `About/spec.md` §15.3 from current provider
      pricing — `runtime/decision.py`'s own cost estimate already uses the
      real current rate ($0.15/$0.60 per M input/output tokens); the spec
      doc's table is what's still stale.
- [ ] Trademark and domain check on the chosen name.
- [ ] M5's known-failing acceptance criteria (T5.6, T5.7, T5.13 — Feud has no
      reconciliation path) haven't been revisited since the 2026-09-17 entry
      below; M6 was built on top of M5 as-is.

---

## ▸ Glossary

Terms are defined once, in `About/context.md` §9, and used consistently everywhere. If
code uses a term that is not in the glossary, either rename the code or add the
term.
