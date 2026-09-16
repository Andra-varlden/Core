# Otherworld

> **Working codename.** `Otherworld` is a placeholder — replace globally when the
> real name is decided. See `About/context.md` §2.

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
| **Phase** | Phase 1 — Fidelity proof |
| **Milestone** | M4 — Recognition Metric, Gate 1 |
| **Status** | M0, M2, M3 COMPLETE. M1 and M4 both IN PROGRESS — the provider blocker is resolved (Groq configured, confirmed working live); the only remaining blocker for a real Gate 1 trial is recruiting the other 3-4 M1 subjects, since 2 agents can't generate enough eligible data on their own |
| **Gate ahead** | Gate 1 — Recognition accuracy ≥ 70% (at M4) |
| **Last updated** | 2026-09-16 |

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

| Repo | Visibility | Contents |
|---|---|---|
| `docs` | Private | These four documents + ADRs *(this repo)* |
| `core` | Private | The simulation — Python 3.12 + FastAPI |
| `web` | Private | Capture UI, dashboard, tile renderer *(created at M6)* |

Further splits (`world-engine`, `moderation`, `infra`) only once boundaries have
stabilised. See `About/architecture.md` §15.

---

## ▸ Quickstart (`core`)

> Applies once M0 is complete.

```bash
# prerequisites: Python 3.12, Docker, Docker Compose

git clone git@github.com:ORG_NAME/core.git
cd core

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
| M1 | Persona capture | IN PROGRESS |
| M2 | Single agent, single tick | COMPLETE |
| M3 | Two agents, first contact | COMPLETE |
| M4 | **Recognition Metric — Gate 1** | IN PROGRESS |
| M5 | Small world, full social system | NOT STARTED |
| M6 | Hosting, accounts, persistence | NOT STARTED |
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
| 2026-09-16 | — | M4 | Real LLM provider (Groq) integrated: `llm/providers/groq.py`, `llm/factory.py` (picks real vs mock based on config), `config.groq_api_key` (wired through `.env`, not raw `os.environ`). Confirmed live and working — persona-driven behavioural variance is real. Four more real bugs a live pilot surfaced and fixed: (1) `run_world` never persisted agents' advanced `last_tick`, so re-running a world would have restarted everyone at tick 0; (2) the free-tier rate limit (8000 TPM) needed more retry budget than the SDK default; (3) the model would hallucinate actions outside the registry (e.g. `register_agent`) when never told what the valid set actually is — now listed explicitly in the prompt; (4) `openai/gpt-oss-*` are reasoning models that were burning the entire token budget on hidden reasoning before any answer appeared, truncating the response to empty — fixed with `reasoning_effort` tuned per tier. Also fixed: relationship state changes (Stranger→Acquaintance, Acquaintance→Friend) weren't scored as important per `spec.md` §5.1's own table — `runtime/resolver.py` now takes the max of action/first-encounter/state-change importance, confirmed live with real 0.75-scored events. **Refined finding:** 2 agents can only ever produce ~2-3 such high-importance events total (once per pair) — nowhere near the 10-per-agent §14 needs, which is exactly why the plan always called for 4-5 agents. Recruiting is now the sole remaining blocker. Also built: `RecognitionHarness` (`eval/recognition.py`) — category-matched decoy sampling, name-stripped descriptions, blinded shuffled presentation, scoring, persistence (T4.1/T4.2 green, 9/9 tests) — and `otherworld.cli.run_world` / `otherworld.cli.recognition` (the bridge from M1 captures to a real trial). |
| 2026-09-16 | — | M3 | Two-agent first contact built: the relationship engine (lazy edge materialisation, trust deltas matching `spec.md` §6.2 exactly, Stranger→Acquaintance→Friend promotion gated on both trust *and* a high-importance shared memory), witness memory writing, and the multi-agent scheduler — decisions computed concurrently but always applied in agent-id order, with a sequential first-encounter pre-pass so escalation trigger 1 fires exactly once per new pair rather than once per side. T3.1–T3.8 all green (70/70 tests); T3.9 (real per-vendor token counts) is honestly still blocked on a live provider key — `spec.md` §15.2 now says so explicitly instead of guessing numbers. |
| 2026-09-16 | — | M2 | Tick loop built end to end: Compiler + Binder, the six-phase loop (perceive→retrieve→decide→validate→act→resolve), the Validator's four ordered filters (owner boundary, platform policy, real-person guard, world legality/containment), tick-based clock with no wall-clock dependency, seeded-RNG determinism (including id generation), decision tracing, and the tick scheduler with re-prompt-once-then-idle fallback. T2.1–T2.10 all green (56/56 tests), including the two non-negotiables: T2.2 determinism and T2.7 containment. Fixed a real bug the first run surfaced: the mock embedding provider produced 384-dim vectors against a 1536-dim pgvector column. |
| 2026-09-15 | — | M1 | Persona capture built: Method A (30-item questionnaire), Method B (conversational interview, deterministic keyword extraction), Method C (writing-sample ingestion with name redaction), boundary compilation, versioned persistence (invariant I5), and an interactive CLI (`otherworld.cli.capture`) for real capture sessions. T1.1–T1.7 all green: 33/33 tests pass, ruff clean, mypy --strict clean. Test suite now runs against a dedicated `otherworld_test` database, separate from dev, after a fixture bug briefly wiped the dev schema. Two real bugs surfaced and fixed by an actual capture session: cross-method versioning created duplicate v1 rows instead of refining into v2, and a "no evidence" confidence value was diluting existing trait readings on merge. |
| 2026-09-15 | — | M0 | Docs moved into `About/`. `core` scaffolded: Pydantic + SQLAlchemy models for every shape in `architecture.md` §9, the action registry (28 actions, matches §10 exactly), the `LLMProvider` protocol + deterministic mock provider, config reading every `spec.md` §20 key, Alembic migration, Docker Compose (Postgres 16 + pgvector, Redis), CI workflow. T0.1–T0.8 all green: 19/19 tests pass, ruff clean, mypy --strict clean on `models/` and `safety/`. |
| 2026-09-14 | — | M0 | Initial documentation set created: `context.md`, `architecture.md`, `spec.md`, `plan.md`, `README.md`. Decisions ADR-001 through ADR-009 recorded. |

---

## ▸ Open items

**Blocking Gate 1 right now:**
- [x] ~~Configure a real Tier 1/2 LLM provider key.~~ **Done 2026-09-16** —
      Groq (`otherworld.llm.providers.groq`), confirmed working end to end
      via live pilot runs. Real persona-driven behavioural variance
      observed. See `About/context.md` §11 for the full story, including two
      real bugs the live testing surfaced and fixed (action hallucination,
      relationship-state-change importance scoring).
- [ ] **Recruit the other 3-4 M4 Recognition Metric subjects** — they are
      also the M1 persona capture subjects. Now the sole remaining blocker:
      2 agents can only ever produce ~2-3 high-importance events total
      (once per relationship pair), far short of the 10-per-agent §14 needs.
      4-5 agents means 4-5+ pairwise relationships, each contributing its
      own eligible events.
- [ ] Once recruited, run `otherworld.cli.run_world` for all of them
      together, for something closer to spec.md's "simulated week" than the
      handful of pilot ticks tested so far, before attempting a real trial
      with `otherworld.cli.recognition`.

**Not yet blocking, but needed before Phase 2:**
- [ ] Decide the real product name; replace the `Otherworld` placeholder globally.
- [ ] Decide the GitHub organisation name; replace `ORG_NAME` globally.
- [ ] Create `docs` and `core` repos, private, with branch protection on `main`.
- [ ] Populate the rate table in `About/spec.md` §15.3 from current provider pricing.
- [ ] Trademark and domain check on the chosen name.

---

## ▸ Glossary

Terms are defined once, in `About/context.md` §9, and used consistently everywhere. If
code uses a term that is not in the glossary, either rename the code or add the
term.
