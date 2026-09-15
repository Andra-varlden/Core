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
| **Milestone** | M1 — Persona capture |
| **Status** | NOT STARTED (M0 complete) |
| **Gate ahead** | Gate 1 — Recognition accuracy ≥ 70% (at M4) |
| **Last updated** | 2026-09-15 |

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
python -m otherworld.eval.recognition   # Recognition Metric harness
python -m otherworld.cli.run_world --seed 42 --ticks 1000
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
| M1 | Persona capture | NOT STARTED |
| M2 | Single agent, single tick | NOT STARTED |
| M3 | Two agents, first contact | NOT STARTED |
| M4 | **Recognition Metric — Gate 1** | NOT STARTED |
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
| 2026-09-15 | — | M0 | Docs moved into `About/`. `core` scaffolded: Pydantic + SQLAlchemy models for every shape in `architecture.md` §9, the action registry (28 actions, matches §10 exactly), the `LLMProvider` protocol + deterministic mock provider, config reading every `spec.md` §20 key, Alembic migration, Docker Compose (Postgres 16 + pgvector, Redis), CI workflow. T0.1–T0.8 all green: 19/19 tests pass, ruff clean, mypy --strict clean on `models/` and `safety/`. |
| 2026-09-14 | — | M0 | Initial documentation set created: `context.md`, `architecture.md`, `spec.md`, `plan.md`, `README.md`. Decisions ADR-001 through ADR-009 recorded. |

---

## ▸ Open items (not yet blocking, but needed before Phase 2)

- [ ] Decide the real product name; replace the `Otherworld` placeholder globally.
- [ ] Decide the GitHub organisation name; replace `ORG_NAME` globally.
- [ ] Create `docs` and `core` repos, private, with branch protection on `main`.
- [ ] Recruit the 4–5 M4 Recognition Metric subjects **now** — they are also the
      M1 persona capture subjects.
- [ ] Populate the rate table in `About/spec.md` §15.3 from current provider pricing.
- [ ] Trademark and domain check on the chosen name.

---

## ▸ Glossary

Terms are defined once, in `About/context.md` §9, and used consistently everywhere. If
code uses a term that is not in the glossary, either rename the code or add the
term.
