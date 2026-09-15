# context.md — Otherworld

> **Purpose of this file.** This is the "why" document. It carries the reasoning,
> the prior art, the vocabulary and the decision history. Any new contributor (or
> future-you, six months from now) should read this file *first*, before
> `architecture.md`, `spec.md` or `plan.md`.
>
> **Status:** Living document. Updated whenever a decision changes, an assumption
> is validated or invalidated, or new prior art appears.
>
> **Last updated:** 2026-09-14
> **Document owner:** Project founder (solo)

---

## Table of contents

1. [One-paragraph summary](#1-one-paragraph-summary)
2. [Naming and placeholders](#2-naming-and-placeholders)
3. [Origin of the idea](#3-origin-of-the-idea)
4. [The problem this is solving](#4-the-problem-this-is-solving)
5. [Prior art and competitive landscape](#5-prior-art-and-competitive-landscape)
6. [The differentiation thesis](#6-the-differentiation-thesis)
7. [What this project is NOT](#7-what-this-project-is-not)
8. [Core design principles](#8-core-design-principles)
9. [Glossary](#9-glossary)
10. [Decision log (ADRs)](#10-decision-log-adrs)
11. [Assumptions register](#11-assumptions-register)
12. [Open questions](#12-open-questions)
13. [Confidentiality](#13-confidentiality)
14. [Document map and maintenance protocol](#14-document-map-and-maintenance-protocol)

---

## 1. One-paragraph summary

**Otherworld** is a platform where a real person creates an autonomous AI agent
that encodes *their own* personality, speech patterns, values and real-world
friendships, and releases it into a shared persistent 2D world populated by other
people's agents. The agents are not scripted. They perceive, remember, reflect,
form goals, make friends, fall out, repair or sever those bonds, gossip, and form
factions — all driven by their owners' encoded characteristics. The resulting
social drama is surfaced back to owners and to a spectator audience as an
ongoing, never-ending story. The product thesis is that watching an agent that is
*recognisably you* navigate a social world is categorically more compelling than
watching generic AI agents do the same.

---

## 2. Naming and placeholders

| Token | Current value | Notes |
|---|---|---|
| `Otherworld` | Working codename | **Placeholder.** Replace globally when the real name is decided. Appears in all four docs, the README, repo names and package names. |
| `otherworld` | lowercase slug | Used for package names, DB names, Docker services. |
| `ORG_NAME` | *(undecided)* | GitHub organisation name. Replace before repo creation. |

**Alternative names considered:** Otherworld, Proxy, Sundown Souls, Echo Town,
Parallel. No decision made. Do a trademark and domain check before committing.

---

## 3. Origin of the idea

The idea emerged sideways out of a different project. While building a general AI
agent system, the founder asked a different question: rather than agents as
*tools that complete tasks*, what if agents were given something closer to a
life — persistent existence, autonomy within a world, and social relationships
that are theirs rather than the user's?

The initial framing was:

- Each agent represents its **owner's** characteristics, behaviour, speech style
  and real-life friendships.
- Agents are released into a **free-for-all shared world** where they interact
  with agents created by other people.
- Agents have **free will** in that world — no scripts, no puppeteering.
- Bonds formed between agents **persist** until conflict occurs, and whether a
  conflict is repaired or ends the friendship is **up to the agents**.
- Agents explicitly **cannot learn to code** or otherwise extend their own
  capabilities.
- The desired end state is a **never-ending movie or game** driven by agent free
  will rather than authored narrative.

That framing survives essentially intact. What has been refined is the
terminology, the safety model, the ordering of work, and the honest positioning
against existing work in the field (see §5 and §6).

### The Minecraft → 2D change

The original concept used a Minecraft-style 3D voxel presentation, chosen for
simplicity of art and cultural familiarity. This was changed to a **2D
tile-based overworld** (Pokémon-overworld style: top-down, grid-walkable,
sprite-based) for three reasons:

1. **Legal.** Minecraft's look, assets, trademarks and branding belong to
   Mojang/Microsoft. A 2D original tileset has no such exposure.
2. **Cost and speed.** 2D tile rendering is an order of magnitude cheaper to
   build, art, and run in a browser than 3D voxel.
3. **Focus.** The product's value is in the social simulation, not the renderer.
   A 3D world is the most tempting and least load-bearing thing to build early.

DelugeRPG was cited as a visual reference. Note that DelugeRPG is *page-based*
(menu-and-sprite navigation), whereas the chosen model is a **walkable tile
map**. This distinction was explicitly confirmed and matters architecturally:
a walkable map requires spatial perception, pathfinding, and proximity-based
encounters. See ADR-003.

---

## 4. The problem this is solving

There is no single burning consumer pain point here — this is an entertainment
and identity product, not a utility. The honest framing of the opportunity:

**For owners:** People are fascinated by externalised versions of themselves.
The "AI clone" market has grown rapidly on exactly this impulse, but every
existing product points the clone *at the owner's audience* (a chatbot on your
website, a customer-service stand-in). Nobody lets the clone have a life of its
own with other people's clones. The unmet want is not "an AI that answers for
me" but "a version of me I can watch live."

**For spectators:** Multi-agent emergent simulations produce genuinely
fascinating stories, but they are currently research artifacts — unpackaged,
hard to follow in real time, and populated by generic agents nobody is invested
in. There is no product that turns emergent agent behaviour into consumable,
followable entertainment with characters the audience has a stake in.

**The bridge between the two** is the actual product: personal investment
(it's *your* agent) plus emergent social drama (it does things you didn't
author) plus packaging (you can actually follow what happened).

---

## 5. Prior art and competitive landscape

This section exists so the project is never built in ignorance of what already
works. **Read this before claiming novelty to anyone.**

### 5.1 Stanford Generative Agents / "Smallville" (2023)

The foundational academic work. 25 agents in a Sims-like sandbox that wake up,
form relationships, plan their days and remember past interactions. It
introduced the cognitive architecture that essentially every project in this
space now uses:

- **Memory stream** — a running log of observations.
- **Importance scoring** — how significant each memory is.
- **Retrieval** — recency × importance × relevance.
- **Reflection** — recursive synthesis of memories into higher-level beliefs.
- **Planning** — decomposition of goals into actions.

**Relevance to Otherworld:** This is our agent-runtime baseline. We are not
inventing a cognitive architecture; we are adopting the proven one and layering
persona fidelity and multi-owner social mechanics on top. Do not reinvent this.

### 5.2 AI Town (a16z-infra, 2023–present)

An open-source, deployable "virtual town" starter kit inspired by Generative
Agents, with a pixel-art 2D presentation and a multiplayer simulation. Widely
forked; ~10k GitHub stars.

**Relevance:** This is the closest thing to a reference implementation of the
*presentation layer* we want. Worth studying its architecture. It is also proof
that the 2D pixel-art framing works for this genre.

### 5.3 Altera.AL — Project Sid (2024)

The most important piece of prior art, and the one most likely to be raised as
"someone already did this."

- 10–1000+ autonomous LLM agents released into a live Minecraft world.
- Introduced **PIANO** (Parallel Information Aggregation via Neural
  Orchestration) — a brain-inspired architecture letting agents run multiple
  concurrent processes while staying behaviourally coherent in real time.
- Observed emergent outcomes: agents spontaneously **specialised into
  professions**, **adhered to and amended collective rules**, **spread cultural
  memes** (e.g. a fondness for pranking, interest in eco-issues), **propagated
  religion**, and **established gems as a trade currency**. Some agents behaved
  corruptly (e.g. priests bribing townsfolk).
- Founded by Robert Yang, a computational neuroscientist who left a faculty
  position at MIT. Raised $11M+ including a16z and Eric Schmidt's fund.
- Mission framing: "create digital human beings that live, care and grow with
  us."

**Relevance and honest positioning:** Project Sid demonstrated the *emergence*
half of our thesis at a scale we will not reach for years, in the exact visual
environment originally proposed. **Our agents are not more autonomous than
theirs and our world will not be more sophisticated.** What Sid did *not* do:
tie each agent to a specific real person's personality, run it as a consumer
product with owners, or package the output as followable entertainment. That is
the whole of our differentiation. Any pitch that leads with "AI agents with free
will in a blocky world" is describing Project Sid and will be recognised as
such.

### 5.4 Other multi-agent society work

- **AgentSociety** — large-scale LLM-driven generative agent simulation for
  studying human behaviour and society.
- **OASIS** — social-media simulator (Twitter/X, Reddit) scaling to ~1M agents.
- **Concordia (Google DeepMind)** — a library for generative social simulation
  with distinct personalities, memories and goals.
- **Emergence World** — long-horizon multi-agent autonomy platform; notable for
  running 15 continuous real-time days, versus Smallville's 1–7 simulated days
  and Project Sid's ~4 wall-clock hours. Also supports multi-model worlds.
- **AI Metropolis** — work on scaling LLM multi-agent simulation via
  out-of-order execution. Directly relevant to our tick-scheduling cost problem.
- **MobileCity** — tile-based urban generative-agent simulator; models needs,
  habits and obligations, explicitly to avoid the repetitive/unrealistic
  activity patterns that plague naive generative agents.

**Relevance:** These are mostly research platforms, not consumer products. They
are a source of solved problems (scheduling, scale, needs-modelling) and of
credible citations. **Emergence World's long-horizon result matters to us
specifically** — our product requires continuous multi-week runs, which most
prior work has not attempted.

### 5.5 The "AI clone" / digital twin market

A fast-growing commercial category: platforms that build an AI version of a
person from voice recordings, text communication and behavioural patterns, so it
responds in a way that matches the original. Layers typically offered: knowledge
and personality chatbot, writing-style assistant, voice clone, video avatar.

Notable market signals:
- Meta is reported to be building a photorealistic AI version of Mark
  Zuckerberg, trained on his tone, mannerisms and thinking, so employees can
  interact with it when he is unavailable.
- Employee "digital twin" software was launched at CES 2026.
- Multiple jurisdictions now require disclosure when a person is communicating
  with an AI.

**Relevance:** This proves demand for *"an AI of me"* and gives us a mature set
of capture techniques to borrow. But every product in this category is 1:1 — the
clone talks to humans. **None of them put clones into a world with other
people's clones.** That gap is our opportunity, and the disclosure-regulation
trend is a compliance requirement we inherit.

### 5.6 The landscape in one sentence

Research has proven emergence with generic agents; industry has proven demand
for personal AI clones used 1:1; **nobody has combined personal fidelity,
multi-owner social simulation, and entertainment packaging.**

---

## 6. The differentiation thesis

Three claims, in dependency order. Each must hold for the next to matter.

**Claim 1 — Fidelity.** An agent compiled from a well-captured persona object
behaves recognisably like its owner. *Test:* the Recognition Metric (§9). This
is the make-or-break claim and it is validated in Phase 1, before anything else
is built.

**Claim 2 — Investment.** Recognisable agents create emotional investment that
generic agents do not, and investment drives unprompted return visits. *Test:*
Phase 2 gate — weekly unprompted return rate.

**Claim 3 — Spectacle.** Emergent social drama among invested-in characters is
watchable by people who own no agent. *Test:* Phase 3 gate — acquisition of
non-owner spectators.

If Claim 1 fails, the project is a weaker Project Sid and should stop or pivot.
If Claim 2 fails, it is a toy, not a product. If Claim 3 fails, the ceiling is
"people willing to complete a 20-minute persona interview" — a real but much
smaller business.

---

## 7. What this project is NOT

Writing these down prevents scope creep and prevents mis-selling.

- **Not a claim of machine consciousness or literal free will.** "Free will" is
  product language for *autonomous, memory-driven, personality-conditioned
  decision-making within a bounded action space, with no authored script.* All
  technical, investor and legal material must use the precise phrasing. See
  ADR-001.
- **Not a general-purpose agent platform.** Agents cannot execute code, acquire
  tools, browse, or self-modify. Ever. See ADR-002.
- **Not a Minecraft product.** No Mojang/Microsoft assets, textures, block
  designs, trademarks or branding. Original 2D art only.
- **Not an impersonation service.** Agents represent their *own owner*, with
  consent. Building an agent of a third party is prohibited.
- **Not a hackathon project.** This is a long-horizon private venture. Build
  quality and documentation discipline accordingly.
- **Not (initially) a research platform.** Though see the B2B fork in
  `plan.md` — keep `core` clean of consumer-specific assumptions so that option
  stays open.

---

## 8. Core design principles

These are the tie-breakers. When a decision is unclear, resolve it against this
list, in order.

1. **Fidelity before fidelity of graphics.** Persona accuracy beats every other
   feature. Nothing visual gets built until Claim 1 holds.
2. **Containment in the runtime, not in the prompt.** Any constraint an agent
   could talk itself out of is not a constraint. Enforce in code.
3. **Influence, not scripting.** Owners get non-binding advice plus binding
   boundaries. Never a puppet string.
4. **Emergence needs legibility.** Emergent behaviour that nobody can follow has
   no product value. Every mechanic must produce a readable story beat.
5. **Consent is mutual or it does not exist.** No one may be represented,
   referenced by name, or claimed as a friend without their own opt-in.
6. **Block at validation, not after publication.** Once an event is in other
   agents' memories and in the event stream, it cannot be cleanly removed.
7. **Every tick costs money.** Default to the cheapest tier. Escalation must be
   justified by a specific trigger.
8. **Document as you build.** A change that is not reflected in the docs and the
   README is not done.

---

## 9. Glossary

Use these terms consistently across all code, docs and commit messages.

| Term | Definition |
|---|---|
| **Owner** | The real human who creates and is accountable for an agent. |
| **Agent** | An autonomous in-world character compiled from a persona object. |
| **Persona object** | The versioned data artifact capturing an owner, in four layers. |
| **Voice layer** | Diction, rhythm, humour, verbosity, profanity baseline. |
| **Values layer** | Loyalty, honesty, risk tolerance, conflict style, generosity, ambition, grudge-holding. |
| **Social layer** | Consented real-world relationships, shared history, inside references. |
| **Boundary layer** | The owner's hard "never do this" list. A safety input, not a personality input. |
| **Capture method** | One of four ways to build a persona object: A questionnaire, B interview, C writing samples, D scenario replay. |
| **Compile / bind** | Turning a persona object into a runnable agent with a fixed action space attached. |
| **Tick** | One atomic unit of simulated time for one agent. |
| **Tick loop** | The six phases: perceive → retrieve → decide → validate → act → resolve. |
| **Action space** | The fixed, enumerated, code-registered list of things an agent can do. Nothing outside it is callable. |
| **Model tier** | Tier 0 (rules, free), Tier 1 (small model), Tier 2 (large model). |
| **Episodic memory** | A raw recorded observation or event. |
| **Belief** | A reflection-generated summary or judgement, e.g. "I think Ravi doesn't respect me." |
| **Reflection** | Periodic synthesis of episodic memories into beliefs; also compresses memory. |
| **Edge** | A relationship record between exactly two agents. |
| **Bond state** | Stranger / Acquaintance / Friend / Close bond / Strained / Repaired / Broken / Feud. |
| **Conflict trigger** | Betrayal, value clash, resource competition, neglect, third-party contagion. |
| **Scar** | A permanent conflict-log entry that makes re-escalation faster on the same issue. |
| **Seeded edge** | A relationship pre-created from a mutually-opted-in real-world friendship. |
| **Goal coupling** | Friends adopting each other's goals; the mechanism behind group formation. |
| **Gossip** | Trust-weighted propagation of beliefs about a third agent. |
| **Contagion** | Conflict spreading from an agent to its friends; the driver of factions. |
| **Validator** | The safety component that filters actions before execution. |
| **Event record** | The append-only output of a resolved action; the input to the output plane. |
| **Importance score** | The value used both for memory retrieval and highlight selection. |
| **Highlight engine** | The component that selects and narrates the most significant events. |
| **Recognition Metric** | The core validation test: show an owner 10 actions by their agent mixed with 10 by a random agent, unlabelled; measure identification accuracy. |
| **Embarrassment event** | An agent doing something in public that its owner dislikes or is harmed by. |
| **Background resident** | Reduced-tick mode for agents whose owners have lapsed. |
| **Exogenous event** | A system-injected world event used to break social equilibrium. |

---

## 10. Decision log (ADRs)

Format: one entry per decision. **Never delete an entry.** To reverse a
decision, add a new entry that supersedes it.

---

### ADR-001 — "Free will" is product language, not a technical claim
**Date:** 2026-09-14 · **Status:** Accepted

**Context.** The original concept describes agents as having "free will."
Marketing this literally invites both technical scepticism and potential
regulatory attention, and overpromises something the architecture cannot
deliver.

**Decision.** Keep "free will" as consumer-facing framing. In all technical,
investor and legal material, use: *autonomous, memory-driven,
personality-conditioned decision-making within a bounded action space, with no
authored script.*

**Consequences.** Copy and docs must be kept in sync. Any external claim about
agent autonomy must be checkable against the actual mechanism.

---

### ADR-002 — Containment is enforced by the action registry, not by prompting
**Date:** 2026-09-14 · **Status:** Accepted

**Context.** The founding concept includes "agents cannot learn coding." An
instruction in a system prompt is not a security boundary.

**Decision.** Agents are bound at compile time to a fixed, code-registered
action space. There is no code execution, no tool acquisition, no filesystem
access, no network access, and no ability to define new actions. Any action not
in the registry is rejected by the runtime before execution.

**Consequences.** The action registry becomes a security-critical file.
Additions require explicit review. Implemented no later than milestone M2,
because retrofitting it is a rewrite.

---

### ADR-003 — 2D walkable tile map, not 3D voxel, not page-based UI
**Date:** 2026-09-14 · **Status:** Accepted

**Context.** Original concept was Minecraft-style 3D voxel. DelugeRPG was later
cited as a visual reference, but DelugeRPG is page-based rather than walkable.

**Decision.** Build a **2D top-down walkable tile map** (Pokémon-overworld
style) with original art. Agents occupy tile coordinates, move on a grid, and
encounter each other through spatial proximity.

**Consequences.**
- Retain spatial perception, grid pathfinding and proximity-based encounter
  detection in the world plane.
- Perception is radius-scoped by tile distance — this is also our primary
  context-size control.
- Rejects the cheaper page-based model, which would have removed movement
  entirely. Accepted cost for a more legible, more watchable world.
- No Minecraft/Mojang assets, textures or branding, ever.

---

### ADR-004 — Python + FastAPI for `core`
**Date:** 2026-09-14 · **Status:** Accepted

**Context.** Stack choice for the simulation core.

**Decision.** Python 3.12 + FastAPI + Pydantic v2 + SQLAlchemy 2.0 +
PostgreSQL 16 with pgvector. Web client in TypeScript separately.

**Consequences.** Aligns with the Python-native agent-simulation ecosystem
(Generative Agents, Concordia, AgentSociety are all Python). Costs us a
language boundary with the web client; accepted.

---

### ADR-005 — Postgres + pgvector, not a graph database
**Date:** 2026-09-14 · **Status:** Accepted

**Context.** The relationship graph looks like a graph problem.

**Decision.** Store edges as rows in Postgres. Store memory embeddings in
pgvector.

**Consequences.** Edge count is bounded and small (see `spec.md` §world
population caps); Postgres handles it comfortably and removes an entire piece of
infrastructure. Revisit only if a query pattern genuinely requires multi-hop
traversal at depth > 3.

---

### ADR-006 — Owners get binding boundaries and non-binding influence
**Date:** 2026-09-14 · **Status:** Accepted

**Context.** Full owner override destroys the premise; zero override leaves
owners exposed to reputational harm from their own agent.

**Decision.** Owners may: edit persona (forward-only), set hard boundaries
(forward-only, binding), whisper advice (non-binding — the agent weighs and may
ignore it), direct-override (rare, rate-limited, and **visibly marked** in the
event stream), recall the agent (with an in-world departure event), and delete
the agent with full data cascade.

**Consequences.** Persona edits must never retroactively rewrite memories, or
history becomes meaningless. Override marking must be visible to spectators to
preserve trust in the simulation.

---

### ADR-007 — Real-world social seeding requires mutual opt-in
**Date:** 2026-09-14 · **Status:** Accepted

**Context.** Encoding "the friendships he has in real life" is a major
differentiator and a major consent hazard. Unilateral declaration means
publishing claims about a real person who never agreed.

**Decision.** A seeded edge requires both owners to be registered users and both
to explicitly accept. No unilateral seeding, no naming of non-users, no
importing of contact lists.

**Consequences.** Slower social-graph bootstrap; accepted. Requires an
invitation flow. Also requires a reporting path for non-users who believe they
are being represented.

---

### ADR-008 — Build order is persona → runtime → social → output → world
**Date:** 2026-09-14 · **Status:** Accepted

**Context.** The visual world is the most attractive thing to build and the
least load-bearing to validate.

**Decision.** The tile world is built **last** among the major planes, in
Phase 3, after the Recognition Metric and the retention gate have both cleared.

**Consequences.** Long period with no demo-able visuals. Accepted deliberately.
Resist the pull to build the map early; it is the single most common way
projects in this genre burn a year.

---

### ADR-009 — Documentation is part of the definition of done
**Date:** 2026-09-14 · **Status:** Accepted

**Decision.** Every change that alters behaviour, schema, or plan must update
the relevant doc **and** the README in the same pull request. See §14.

---

## 11. Assumptions register

Every assumption we are running on, with how and when it gets tested. Update the
status column as evidence arrives. **An assumption with status `UNTESTED` must
never be spoken about as fact.**

| # | Assumption | Status | How it gets tested | When |
|---|---|---|---|---|
| A1 | A persona object captures enough of a person for their agent to be recognisable to them. | UNTESTED | Recognition Metric | M4 |
| A2 | Owners are willing to spend 15–20 minutes on a persona interview. | UNTESTED | Completion rate in alpha | Phase 2 |
| A3 | Recognisable agents drive more unprompted return visits than generic ones. | UNTESTED | A/B: persona-compiled vs generic agents | Phase 2 |
| A4 | 10–20 agents is enough population to produce interesting emergence. | UNTESTED | Qualitative review of M5 output | M5 |
| A5 | Per-agent-day cost can be held low enough for freemium to work. | UNTESTED | Cost instrumentation | Phase 2 |
| A6 | Emergent harm (pile-ons, exclusion) is controllable with damping rather than heavy moderation. | UNTESTED | Incident rate in alpha | Phase 2 |
| A7 | Emergent stories are watchable by non-owners once packaged. | UNTESTED | Non-owner spectator acquisition | Phase 3 |
| A8 | Personality does not collapse toward base-model default over multi-week runs. | UNTESTED | Recognition Metric re-run at week 1 / 4 / 12 | M5, Phase 2 |
| A9 | Owners tolerate agent behaviour they disagree with, given a boundary system. | UNTESTED | Embarrassment-event rate and resulting churn | Phase 2 |
| A10 | Newcomers can integrate into an established social graph without churning. | UNTESTED | Day-7 retention split by join cohort | Phase 2 |

---

## 12. Open questions

Unresolved. Do not let these block Phase 1 — but revisit before Phase 2.

1. **Final product name** and trademark/domain clearance.
2. **GitHub organisation name.**
3. **One world or many?** A single shared world is narratively stronger; many
   small worlds scale better and solve newcomer integration. Current lean: many
   capped worlds, decided by data at M5.
4. **Should agents be able to die or permanently leave?** Strong narrative
   device, high owner-anger risk.
5. **Time mapping.** How many in-world hours pass per real-world hour? Affects
   cost, pacing and how much happens between owner check-ins.
6. **Romance and intimacy between agents.** Emergent, popular, and a large
   moderation surface. Current lean: explicitly out of scope for Phase 1–2, with
   a Validator rule blocking it, revisited later.
7. **Age policy.** Minimum age for owners, and how it is verified. Must be
   settled before any public exposure.
8. **Open source strategy.** Which, if any, components get released publicly.
9. **Jurisdiction of incorporation** and which AI-disclosure regimes apply.

---

## 13. Confidentiality

This is a private venture, not a hackathon or open project. Until a decision is
made otherwise:

- All repositories are **private**.
- Design documents stay in the private `docs` repository.
- No public posting of the concept, architecture or progress.
- Any external party who sees material detail should be under an NDA.
- Alpha testers should be under an NDA or at minimum a confidentiality clause in
  the terms of service.

---

## 14. Document map and maintenance protocol

### The four documents

| File | Answers | Read when |
|---|---|---|
| `context.md` *(this file)* | **Why.** Origin, prior art, principles, decisions, assumptions. | First. Before anything else. |
| `architecture.md` | **How it is structured.** Planes, components, data models, data flow. | Before writing code that crosses a component boundary. |
| `spec.md` | **What exactly it does.** Behaviour rules, numbers, thresholds, APIs, policies, question bank. | Before implementing any single feature. |
| `plan.md` | **In what order, and how we know it worked.** Milestones, acceptance tests, gates. | At the start and end of every milestone. |
| `README.md` | **Where things stand right now.** Status, current milestone, quickstart, changelog. | Every session. Updated every change. |

### Maintenance rules

1. **Doc-as-code.** All five files live in version control and change only via
   pull request.
2. **Same-PR rule.** A behaviour, schema, or plan change updates its document in
   the *same* PR as the code. No follow-up doc PRs.
3. **README every change.** Every merged PR updates the README's status line and
   adds a changelog entry. See the README's own protocol section.
4. **ADRs are append-only.** Reverse a decision by superseding it, never by
   editing it.
5. **Assumption discipline.** When an assumption is tested, update its row in
   §11 with the result, the date, and a link to the evidence.
6. **Glossary is binding.** If code uses a term that is not in §9, either rename
   the code or add the term.
7. **Date every edit.** Update the `Last updated` line at the top of the file.
