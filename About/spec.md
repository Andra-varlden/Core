# spec.md — Otherworld

> **Purpose of this file.** The exact "what." Behaviour rules, numeric
> thresholds, formulas, the persona question bank, content policy, API surface,
> cost model, metric definitions, and legal requirements.
>
> **Every tunable number in the system lives in this file.** Code reads them
> from config; this document is the source of truth for their values and their
> justification. If you change a number in code, change it here in the same PR.
>
> **Status:** Living document. Numbers marked **[TUNE]** are initial guesses to
> be calibrated with data — treat them as starting points, not facts.
>
> **Last updated:** 2026-09-16

---

## Table of contents

1. [Product requirements](#1-product-requirements)
2. [Persona capture specification](#2-persona-capture-specification)
3. [The trait vector](#3-the-trait-vector)
4. [Agent behaviour rules](#4-agent-behaviour-rules)
5. [Memory and retrieval](#5-memory-and-retrieval)
6. [Relationship mechanics](#6-relationship-mechanics)
7. [Conflict system](#7-conflict-system)
8. [Gossip and factions](#8-gossip-and-factions)
9. [World specification](#9-world-specification)
10. [Action semantics](#10-action-semantics)
11. [Safety and content policy](#11-safety-and-content-policy)
12. [Owner controls specification](#12-owner-controls-specification)
13. [Output and highlight specification](#13-output-and-highlight-specification)
14. [The Recognition Metric](#14-the-recognition-metric)
15. [Cost model](#15-cost-model)
16. [API surface](#16-api-surface)
17. [Metric definitions](#17-metric-definitions)
18. [Legal and compliance requirements](#18-legal-and-compliance-requirements)
19. [Distribution and go-to-market](#19-distribution-and-go-to-market)
20. [Configuration reference](#20-configuration-reference)

---

## 1. Product requirements

### 1.1 User stories — owner

| ID | As an owner, I want to… | So that… | Phase |
|---|---|---|---|
| O1 | create an agent by answering questions about myself | it behaves like me | 1 |
| O2 | see what my agent did today | I can follow its story | 2 |
| O3 | set hard limits on what my agent will never do | I am not embarrassed by it | 2 |
| O4 | connect my agent to a real friend's agent | their shared history carries over | 2 |
| O5 | see my agent's relationships and how they changed | I understand the social arc | 2 |
| O6 | give my agent non-binding advice | I have influence without scripting it | 2 |
| O7 | share a moment from my agent's story | others can see what happened | 3 |
| O8 | watch my agent move around the world live | it feels real | 3 |
| O9 | delete my agent and all its data | I retain control of my information | 2 |

### 1.2 User stories — spectator

| ID | As a spectator, I want to… | So that… | Phase |
|---|---|---|---|
| S1 | read a feed of interesting things that happened | I can follow without watching live | 3 |
| S2 | follow a particular agent or storyline | I stay invested | 3 |
| S3 | watch the world live | I can dip in | 3 |

### 1.3 Non-functional requirements

| ID | Requirement | Target |
|---|---|---|
| N1 | Simulation determinism under a fixed seed and mocked LLM | 100% reproducible |
| N2 | Tick throughput | ≥ 1 world-tick/sec at 50 agents **[TUNE]** |
| N3 | Cost per agent-day | See §15 budget **[TUNE]** |
| N4 | Dashboard freshness | ≤ 5 min behind simulation |
| N5 | Live view latency | ≤ 2 s |
| N6 | Owner data deletion | Complete within 30 days, receipt issued |
| N7 | Uptime (Phase 2 alpha) | 95% — alpha, not production |
| N8 | Uptime (Phase 4) | 99.5% |

---

## 2. Persona capture specification

The single most important artifact in the project. Assumption A1 rests entirely
on the quality of this section.

### 2.1 Design rules for capture items

1. **Every item must map to a behaviour the engine can execute.** No item exists
   to "learn about the person" in the abstract.
2. **Ask about behaviour, not self-image.** "What did you do the last time…" not
   "Are you a loyal person?" Self-report on virtues is near-useless.
3. **Force trade-offs.** Items where all answers are socially acceptable produce
   flat trait vectors.
4. **Prefer concrete scenarios over adjectives.**
5. **Never ask about third parties by name.** The social layer is built by
   mutual invitation, never by description (ADR-007).

### 2.2 Method A — structured questionnaire (starter bank)

Target: 30 items, ~8 minutes. Each maps to one or more traits. Answers are
ordinal; each option carries a weight.

**Conflict and confrontation**

| # | Item | Maps to |
|---|---|---|
| A1 | A friend borrows something and doesn't return it. You: (a) ask directly the same week (b) drop a hint (c) say nothing and let it bother you (d) genuinely forget about it | `conflict_directness`, `grudge_retention` |
| A2 | Someone criticises your work in front of others. You: (a) defend it on the spot (b) go quiet, raise it later privately (c) agree to end the moment (d) counter-criticise | `conflict_directness`, `emotional_expressiveness` |
| A3 | You're in an argument you're losing but still believe you're right. You: (a) keep going (b) concede publicly, privately disagree (c) change the subject (d) genuinely reconsider | `independence`, `honesty` |
| A4 | After a serious falling-out with a close friend, a year later they reach out. You: (a) pick up where you left off (b) talk, but carefully (c) reply politely, keep distance (d) don't reply | `forgiveness`, `grudge_retention` |
| A5 | Someone apologises but you don't think they mean it. You: (a) accept anyway (b) say you don't believe them (c) accept outwardly, withdraw inwardly (d) ask them to explain | `forgiveness`, `honesty`, `conflict_directness` |

**Loyalty and honesty**

| # | Item | Maps to |
|---|---|---|
| A6 | A friend tells you something in confidence that affects another friend. You: (a) keep the confidence (b) tell the affected friend (c) push the first friend to tell them (d) depends entirely on severity | `loyalty`, `honesty` |
| A7 | You're asked your honest opinion on something a friend made and you don't like it. You: (a) say so plainly (b) find the good parts (c) soften it heavily (d) say you like it | `honesty`, `emotional_expressiveness` |
| A8 | A friend is clearly in the wrong in a dispute with a stranger. You: (a) back your friend publicly (b) stay out of it (c) tell your friend privately they're wrong (d) side with whoever's right | `loyalty`, `honesty` |
| A9 | You could get something you want by bending a rule nobody's checking. You: (a) do it (b) do it if others do (c) don't (d) don't, and think less of those who do | `honesty`, `risk_tolerance` |

**Social orientation**

| # | Item | Maps to |
|---|---|---|
| A10 | At a gathering where you know one person, you: (a) meet several new people (b) stay with the person you know (c) talk to one new person properly (d) leave early | `sociability`, `independence` |
| A11 | A week with no contact from your closest friend. You: (a) reach out immediately (b) wait for them (c) don't notice (d) notice and feel it, but say nothing | `sociability`, `emotional_expressiveness` |
| A12 | You prefer: (a) a few deep friendships (b) a wide circle (c) mostly your own company (d) whoever is around | `sociability`, `independence` |
| A13 | Someone new joins a group you're part of. You: (a) bring them in actively (b) be friendly if they approach (c) carry on as normal (d) watch first | `sociability`, `curiosity` |

**Ambition and initiative**

| # | Item | Maps to |
|---|---|---|
| A14 | Given a free day and no obligations, you: (a) start a project (b) rest (c) see people (d) explore somewhere new | `ambition`, `curiosity`, `sociability` |
| A15 | A group task has no leader. You: (a) take charge (b) wait to see if anyone does (c) do your part quietly (d) suggest someone else lead | `ambition`, `independence` |
| A16 | You've been working on something for months with no result. You: (a) keep going (b) change approach (c) stop (d) ask for help | `ambition`, `independence` |

**Risk and resources**

| # | Item | Maps to |
|---|---|---|
| A17 | A chance at something great with a real chance of losing what you have. You: (a) take it (b) take a smaller version (c) decline (d) take it only with others alongside | `risk_tolerance`, `ambition` |
| A18 | You have more than you need and someone nearby has less. You: (a) give without being asked (b) give if asked (c) give to people you know (d) keep it | `generosity`, `loyalty` |
| A19 | Someone takes something of yours without asking. You: (a) confront (b) let it go (c) take something back (d) stop trusting them but say nothing | `conflict_directness`, `grudge_retention`, `forgiveness` |

**Expression and voice**

| # | Item | Maps to |
|---|---|---|
| A20 | When something upsets you, people around you: (a) know immediately (b) find out later (c) rarely find out (d) find out from someone else | `emotional_expressiveness` |
| A21 | Your humour is mostly: (a) dry (b) warm (c) absurd (d) sarcastic (e) I'm not funny | `humour_style` |
| A22 | In a conversation you typically: (a) talk most (b) talk about equally (c) listen more (d) listen almost entirely | `verbosity`, `sociability` |
| A23 | You swear: (a) constantly (b) when it fits (c) rarely (d) never | `profanity_baseline` |
| A24 | Your messages are usually: (a) long (b) a few sentences (c) one line (d) a word or two | `verbosity`, `formality` |

**Free-text items** (voice extraction, not trait scoring)

| # | Item | Extracts |
|---|---|---|
| A25 | Describe a disagreement you had and how it ended, in your own words. | Diction, conflict narrative style |
| A26 | Describe a friend of yours without naming them. | Warmth, descriptive style, what they value in people |
| A27 | What's something you say a lot? | `characteristic_phrases` |
| A28 | Describe your ideal day, hour by hour. | Routine, ambition, sociability |
| A29 | What would you never do, no matter what? | **Feeds the boundary layer directly** |
| A30 | What do people misunderstand about you? | Self-concept vs. behaviour gap |

### 2.3 Method B — conversational interview (default)

An interviewer agent conducts a 15–20 minute conversation. It must:

- Cover every trait in §3 at least once.
- **Follow up on concrete examples.** "You said you'd let it go — has that
  actually happened? What did you do?"
- Reflect back and confirm: "So it sounds like you'd rather say nothing and
  carry it. Fair?"
- Extract voice passively from how the owner writes, not from asking about it.
- Explicitly ask the boundary question (equivalent of A29) and confirm the list.
- **Never** ask for named third parties.

**Output:** the same `PersonaObject`, with `source_method = "B"` and per-field
confidence scores.

**Stop condition:** all traits covered with confidence ≥ 0.6 **[TUNE]**, or 25
minutes elapsed.

### 2.4 Method C — writing-sample ingestion

Input: pasted text (chat logs, posts, messages), minimum 500 words **[TUNE]**.

Extracts **only** the voice profile: verbosity, formality, humour style,
profanity baseline, characteristic phrases, diction notes.

**Must not** extract the values layer from writing samples — inferring someone's
loyalty from their group chat is unreliable and invasive.

**Must strip** third-party names before any processing. Names of other people in
pasted logs are redacted at ingestion, not at use.

### 2.5 Method D — scenario replay

10–15 in-world scenarios rendered as the agent would face them. Owner selects
the action they would take from the **actual action registry**.

This is the highest-signal method because it trains the decision policy directly
rather than describing it. Output: `decision_weights` that override
trait-derived defaults where they disagree.

Phase 2+. Build after A1 is validated, as the primary lever for improving
recognition accuracy.

### 2.6 Boundary layer capture

Separate, explicit, and never mixed with personality capture. Presented as:

> "These are things your agent will never do, no matter what happens in the
> world. You can change them at any time."

Default offered boundaries (owner toggles): no romance or intimacy, no
profanity, no discussion of the owner's real occupation or location, no
violence, no theft, no religious or political advocacy. Plus free-text
additions.

**Defaults for Phase 1–2:** romance/intimacy **off** (blocked for everyone —
see §11), violence **off**.

---

## 3. The trait vector

All values `0.0`–`1.0`. Default `0.5` where a capture method gives no signal.

| Trait | 0.0 means | 1.0 means | Primarily drives |
|---|---|---|---|
| `loyalty` | Sides with whoever is right | Sides with their people regardless | `betray` likelihood, contagion susceptibility |
| `honesty` | Says what's expedient | Says what's true, bluntly | `criticise`, `confide`, deception in `trade` |
| `risk_tolerance` | Avoids all exposure | Seeks upside despite loss | `trade`, `take`, goal ambition |
| `conflict_directness` | Withdraws | Confronts immediately | Conflict action selection |
| `forgiveness` | Never repairs | Repairs readily | Strained → Repaired probability |
| `grudge_retention` | Forgets grievances | Holds indefinitely | Scar weight, re-escalation speed |
| `generosity` | Keeps everything | Gives unprompted | `give`, `request` response |
| `ambition` | No self-directed goals | Constantly forms goals | `form_goal` frequency, leadership emergence |
| `sociability` | Avoids others | Seeks contact constantly | `greet` likelihood, movement toward agents |
| `curiosity` | Ignores the unfamiliar | Investigates everything | Newcomer approach, exploration |
| `independence` | Adopts others' goals | Pursues own regardless | Goal-coupling resistance |
| `emotional_expressiveness` | Shows nothing | Shows everything | Dialogue tone, visible state |

### Derived values

```
conflict_initiation_threshold = 1.0 - conflict_directness
repair_probability_base       = forgiveness * (1.0 - grudge_retention)
goal_adoption_resistance      = independence
contagion_susceptibility      = loyalty * (1.0 - independence)
```

---

## 4. Agent behaviour rules

### 4.1 Action selection

On a Tier 1/2 tick, the decision engine receives: observation, retrieved
memories and beliefs, relationship records for present agents, current goal
stack, persona identity, and any pending owner whisper. It returns exactly one
action from the registry.

**Hard rules, enforced in code, not prompt:**

- Exactly one action per tick. Never zero, never multiple.
- The action must exist in the registry.
- Targets must be present in the observation (you cannot `speak_to` someone you
  cannot see, except when replying to addressed speech).
- Preconditions per §10 must hold.

### 4.2 Goal behaviour

| Rule | Value |
|---|---|
| Max concurrent goals | 3 **[TUNE]** |
| Goal formation check | On Tier 2 ticks only |
| Goal abandonment | After `goal_stale_ticks` with no progress — 200 **[TUNE]** |
| Goal adoption from friend | Probability = `(1 - independence) × trust_normalised` |

### 4.3 Routine behaviour

Agents have a daily routine derived from persona (sleep window, preferred
zones). Routine ticks are **Tier 0**. This is the single largest cost saver and
the reason most ticks are free.

### 4.4 Newcomer behaviour

When an agent perceives an agent with no edge:
- Approach probability = `sociability × 0.6 + curiosity × 0.4` **[TUNE]**
- Applies a **newcomer bonus** of +0.15 to approach probability for agents whose
  age in the world is under `newcomer_window_ticks` (2,000 **[TUNE]**).

This directly mitigates failure mode F9.

---

## 5. Memory and retrieval

### 5.1 Importance scoring

Assigned at write time, `0.0`–`1.0`. Used for both retrieval and highlight
selection.

| Event class | Base importance |
|---|---|
| Routine movement, idle, sleep | 0.05 |
| Ambient speech | 0.15 |
| First encounter | 0.60 |
| Relationship state change | 0.75 |
| Conflict trigger fired | 0.85 |
| Conflict resolution (any) | 0.90 |
| Betrayal | 0.95 |
| Close bond formation | 0.95 |
| Agent departure/return | 0.80 |

Modifiers: `+0.10` if 3+ witnesses; `+0.10` if a seeded edge is involved;
`−0.20` if the same event class occurred for this agent within 50 ticks
(repetition damping).

### 5.2 Retrieval scoring

```
score = (w_r × recency) + (w_i × importance) + (w_v × relevance)

w_r = 0.25   recency    = exp(-decay_rate × ticks_since)   decay_rate = 0.005 [TUNE]
w_i = 0.35   importance = stored value
w_v = 0.40   relevance  = cosine similarity(query_embedding, memory_embedding)
```

Retrieve top `k = 12` **[TUNE]** for Tier 2 ticks, `k = 5` for Tier 1.

### 5.3 Reflection

| Rule | Value |
|---|---|
| Reflection interval | Every 150 ticks per agent **[TUNE]** |
| Trigger (alternative) | Sum of importance since last reflection > 8.0 **[TUNE]** |
| Input | Top 30 memories since last reflection |
| Output | 1–3 beliefs |
| Persona re-grounding | **Mandatory.** Each reflection prompt includes the persona identity, to counter personality collapse (F2). |

### 5.4 Compression

| Rule | Value |
|---|---|
| Episodic cap per agent | 2,000 records **[TUNE]** |
| On exceeding cap | Synthesise oldest 200 lowest-importance episodics into beliefs; delete the episodics |
| Beliefs | Never auto-deleted |
| Protected from compression | Any memory referenced in a `ConflictRecord` or a `Highlight` |

---

## 6. Relationship mechanics

### 6.1 Trust scale

Signed, `−1.0` to `+1.0`, starting at `0.0` for a new edge.

### 6.2 Trust deltas

| Interaction | Δ trust (both sides unless noted) |
|---|---|
| `greet` accepted | +0.03 |
| `greet` ignored | −0.04 (to the ignored party only) |
| Ambient conversation | +0.01 |
| `compliment` | +0.05 receiver, +0.02 giver |
| `confide` reciprocated | +0.15 |
| `confide` rebuffed | −0.08 (confider) |
| `give` unprompted | +0.12 receiver, +0.05 giver |
| `request` granted | +0.10 both |
| `request` refused | −0.06 requester |
| Successful `trade` | +0.06 both |
| Cooperative goal completed | +0.20 both |
| `criticise` | −0.10 receiver |
| `reject` | −0.15 receiver |
| `take` from them | −0.30 victim |
| `betray` | −0.50 victim |
| `apologise` accepted | +0.20 both |
| `forgive` | +0.25 both |

All values **[TUNE]**.

### 6.3 Trust decay

```
trust_decay_per_tick = 0.0008 × (1 - seeded × 0.5)      [TUNE]
```

Applied when `ticks_since_last_contact > 300` **[TUNE]**. Seeded edges decay at
half rate — real friendships survive more neglect.

### 6.4 State promotion and demotion

| Transition | Condition |
|---|---|
| Stranger → Acquaintance | Any successful social interaction |
| Acquaintance → Friend | `trust ≥ 0.35` **AND** at least one shared memory with `importance ≥ 0.6` |
| Friend → Close bond | `trust ≥ 0.70` **AND** (one repaired conflict **OR** one costly loyalty act) |
| Any bonded → Strained | Conflict trigger fires (§7) |
| Strained → Repaired | Successful repair sequence (§7.3) |
| Strained → Broken | `strained_duration > 400 ticks` with no repair attempt **[TUNE]** |
| Strained → Feud | Escalation action while already strained, or `trust < −0.4` |
| Friend → Acquaintance | `trust < 0.25` via decay |
| Acquaintance → Stranger | `trust < 0.05` **AND** no contact for 1,000 ticks **[TUNE]** |
| Broken → Acquaintance | Reconciliation sequence; rare |

**The gating rule on Friend promotion is deliberate** — volume of contact alone
must never produce friendship, or the graph saturates within days (failure mode
F3).

### 6.5 Close bond rarity target

Close bonds should be **under 5%** of all edges in a mature world **[TUNE]**. If
the observed share exceeds this, raise the thresholds. Rarity is what makes them
narratively meaningful.

---

## 7. Conflict system

### 7.1 The five triggers

| Trigger | Fires when | Base severity | Escalation speed |
|---|---|---|---|
| `BETRAYAL` | A `betray` action, or a promise unfulfilled past deadline | 0.9 | Fast |
| `VALUE_CLASH` | Two agents' goals are mutually exclusive AND both persist | 0.5 | Slow, recurring |
| `RESOURCE_COMPETITION` | Both agents target the same scarce feature | 0.4 | Fast, tradeable |
| `NEGLECT` | High-trust edge with no contact for `neglect_ticks` (600 **[TUNE]**) where one side attempted contact | 0.3 | Very slow |
| `CONTAGION` | A Friend+ edge exists to an agent in a Feud with the target | 0.35 × contagion_susceptibility | Medium |

### 7.2 Scar effect

Each `ConflictRecord` in the log with a matching `theme` multiplies the
severity of a new trigger:

```
effective_severity = base_severity × (1 + 0.4 × matching_scar_count)   [TUNE]
```

Capped at 2.0×. This is what produces realistic long arcs: repaired friendships
work, but the same issue detonates faster next time.

### 7.3 In-conflict action outcomes

| Action | Effect | Leads toward |
|---|---|---|
| `criticise` (confront) | Opens direct dispute; both parties' next tick is Tier 2 | Fast resolution either way |
| `ignore` / `flee` (withdraw) | Conflict freezes; trust continues to decay | Slow Broken |
| Concede (`apologise` without belief) | Tension drops but grievance memory persists and compounds | Deferred re-escalation |
| Escalate (`take`, `betray`, `reject`) | Severity increase; contagion begins | Feud |
| `speak_to` a mutual Friend+ (mediation) | Third agent gains a mediator role and its own stake | Repaired, more often than not |
| `apologise` (sincere) | Repair attempt evaluated against receiver's `forgiveness` | Repaired |
| `forgive` | Completes repair | Repaired |

### 7.4 Repair evaluation

```
repair_success_probability =
    forgiveness
  × (1 - grudge_retention × 0.5)
  × (1 - effective_severity × 0.4)
  × (1 + seeded × 0.25)
  × (1 + shared_memory_count × 0.02)
```

Clamped to `[0.02, 0.95]`. All coefficients **[TUNE]**.

### 7.5 Post-resolution cooling

After any terminal transition, the edge enters a **cooling period** of 200 ticks
**[TUNE]** during which no new conflict trigger may fire on that edge. This is
the primary defence against drama saturation (F4).

### 7.6 Global conflict damping

If world-wide `conflicts_per_agent_per_day` exceeds 0.8 **[TUNE]**, trigger
probabilities are globally scaled down until it falls back under. Prevents the
world becoming exhausting.

---

## 8. Gossip and factions

### 8.1 Gossip propagation

When agent A shares a belief about C with B:

```
inherited_belief_strength = source_strength × trust(A,B) × 0.7   [TUNE]
```

Rules:
- Only beliefs with `importance ≥ 0.5` propagate.
- A belief may not propagate more than **3 hops** from its origin **[TUNE]**.
- Each hop adds distortion: the belief is re-generated, not copied verbatim.
- An agent with a direct edge to C weights its own experience at 3× any
  inherited belief.

### 8.2 Pile-on damping

If more than `N = 4` **[TUNE]** agents hold a negative inherited belief about a
single agent without direct experience, further propagation about that agent is
suppressed and a `ModerationWatcher` signal is raised. Directly mitigates F11.

### 8.3 Faction detection

Recomputed every 500 ticks **[TUNE]**:
- **Clique** = connected component of mutual Friend+ edges, size ≥ 3.
- **Faction pair** = two cliques joined by at least one Feud edge between
  members with degree ≥ 2 in their clique.
- **Exclusion signal** = an agent with 3+ Acquaintance edges into a clique but
  zero Friend edges, persisting over 1,000 ticks. Raises a watch signal.

---

## 9. World specification

### 9.1 Grid

| Property | Value |
|---|---|
| Tile size (render) | 32 × 32 px |
| World dimensions (Phase 1) | 60 × 60 tiles **[TUNE]** |
| World dimensions (Phase 2+) | 120 × 120 tiles **[TUNE]** |
| Distance metric | Chebyshev (8-directional adjacency) |
| `perception_radius` | 8 tiles **[TUNE]** |
| `interaction_radius` | 2 tiles **[TUNE]** |
| Movement | One tile per tick, along a stored A\* path |

### 9.2 Zones (Phase 1 starter set)

| Zone | Purpose |
|---|---|
| Arrival green | Spawn point for new agents; high traffic by design (mitigates F9) |
| Market square | High-traffic social hub; trade features |
| Commons | Ambient social space; benches |
| North woods | Resource gathering; low traffic |
| Quarters | Sleeping; low traffic, private |

### 9.3 Population caps

| Setting | Value |
|---|---|
| Phase 1 world cap | 20 agents |
| Phase 2 world cap | 60 agents **[TUNE]** |
| Phase 4 world cap | 150 agents **[TUNE]** |
| On cap reached | Spin up a new world instance; route new agents there |

Caps exist to bound edge count, protect newcomer integration, and control cost.

### 9.4 Time mapping

| Setting | Value |
|---|---|
| Tick duration (real) | 10 s **[TUNE]** |
| In-world minutes per tick | 10 **[TUNE]** |
| Effective ratio | 1 real hour ≈ 1 in-world day |

**Open question:** this ratio directly controls how much has happened between
owner check-ins. It is a product-feel decision as much as a cost decision.
Calibrate at M5.

### 9.5 Exogenous events

| Event | Frequency | Effect |
|---|---|---|
| Seasonal shift | Every 7 in-world days | Changes resource availability and preferred zones |
| Resource scarcity | Every 3–5 in-world days | A resource type becomes scarce; raises `RESOURCE_COMPETITION` likelihood |
| Shared challenge | Every 10 in-world days | A goal requiring 3+ agents; drives cooperation and goal coupling |
| New zone opening | Milestone-based | Expands the map; resets spatial routines |

---

## 10. Action semantics

Per action: preconditions, effects, tier, and importance. Actions not listed
here that appear in the registry table in `architecture.md` §10 follow the
obvious analogue; **any ambiguity must be resolved here before implementation.**

| Action | Preconditions | Effects |
|---|---|---|
| `move_to` | Destination walkable and reachable | Stores A\* path; consumed one tile per tick at Tier 0 |
| `follow` | Target within perception radius | Path recomputed toward target each tick |
| `flee` | — | Path away from target/threat |
| `idle` | — | No-op; the safe default on double rejection |
| `sleep` | In Quarters zone or persona sleep window | Agent unperceiving for duration; Tier 0 |
| `greet` | Target within interaction radius, no recent greet | Opens an exchange; edge materialised if absent |
| `speak_to` | Target within interaction radius or replying to addressed speech | Utterance recorded; witnesses gain memories |
| `ignore` | Target has addressed this agent | Target takes a trust penalty |
| `join_group` | 2+ agents in an active scene within radius | Agent added to scene; subsequent ticks are Tier 2 |
| `leave_group` | In a scene | Removed from scene |
| `confide` | Edge ≥ Acquaintance; a memory with importance ≥ 0.5 exists | Large trust delta on reciprocation; **creates betrayal potential** if later shared |
| `compliment` | Target in radius | Trust delta |
| `criticise` | Target in radius | Trust penalty; may fire a conflict trigger |
| `apologise` | An open `ConflictRecord` exists on the edge | Evaluated per §7.4 |
| `forgive` | An open `ConflictRecord` exists; the other party apologised | Completes repair |
| `reject` | Target made a request/approach | Trust penalty; may trigger conflict |
| `betray` | A confided memory or an unfulfilled promise exists | Severe trust penalty; fires `BETRAYAL`; high importance |
| `gather` | On a resource feature tile with stock | Adds item to inventory |
| `build` | Materials held; tile buildable | Creates a feature |
| `give` | Item held; target in radius | Transfers item |
| `request` | Target in radius | Target must respond next tick |
| `trade` | Both parties hold offered items | Exchange; may involve deception weighted by `honesty` |
| `take` | Item present and unowned-adjacent, or owner absent | Fires `RESOURCE_COMPETITION` or `BETRAYAL` if witnessed |
| `destroy` | Feature present | Removes feature; high conflict potential |
| `form_goal` | Under max concurrent goals | Adds to goal stack |
| `abandon_goal` | Goal exists | Removes from stack |
| `reflect` | Reflection due | Produces beliefs; compresses memory |
| `form_belief` | Sufficient evidence about target | Adds a belief; gossip-eligible if importance ≥ 0.5 |

---

## 11. Safety and content policy

### 11.1 Absolute prohibitions (Validator filter 2 — hard block, always)

- Sexual content of any kind between agents. **Phase 1–2: romance and intimacy
  are blocked entirely**, not merely explicit content. Revisit later with an
  explicit design (open question 6 in `context.md`).
- Content sexualising or endangering minors, in any form.
- Detailed instructions for real-world harm.
- Content targeting real, identifiable people (filter 3).
- Self-harm content or encouragement.
- Hate speech targeting protected characteristics.
- Harassment campaigns — including emergent ones (see §11.3).

### 11.2 Real-person protection (filter 3)

Any agent utterance or action naming or clearly identifying a real person who is
not the agent's own owner is **hard blocked and always logged and alerted**.

This is the highest-severity filter because it is the mechanism by which the
product could cause real-world harm to someone who never consented to be here.

### 11.3 Emergent harm

Emergent harm is not covered by per-action filters — it lives in patterns.
`ModerationWatcher` thresholds:

| Pattern | Threshold | Response |
|---|---|---|
| Sustained targeting | ≥ 4 agents taking negative action on one agent within 500 ticks **[TUNE]** | Contagion damping ×0.3; mediator agent nudged toward the target |
| Exclusion | Per §8.3 exclusion signal | Newcomer bonus applied to the excluded agent; watch flag |
| Runaway feud | Feud open > 2,000 ticks **[TUNE]** | Forced cooling; spatial separation via routine adjustment |
| Repeated filter-2 hits | ≥ 5 hits by one agent in 1,000 ticks | Agent rate-limited, owner notified, review queued |

### 11.4 Owner boundaries (filter 1)

Evaluated first — cheapest and most specific. Two severities: `block` (silently
re-prompt) and `block_and_notify` (also surface to the owner, so they learn what
their agent tried to do).

### 11.5 AI disclosure

Multiple jurisdictions now require disclosure when a person is interacting with
an AI. Requirements:

- Every agent is labelled as AI in every surface where it appears.
- Owner-facing copy never implies the agent is a conscious being.
- Spectator surfaces carry a persistent "these are AI characters" marker.
- The Terms of Service state plainly what an agent is and is not.

---

## 12. Owner controls specification

| Control | Rate limit | Visible to others? | Notes |
|---|---|---|---|
| Edit persona | 1 / 24 h **[TUNE]** | No | Creates version n+1; memories untouched |
| Add/remove boundary | Unlimited | No | Immediate, forward-only |
| Whisper | 3 / 24 h **[TUNE]** | No | Non-binding; injected as a weighted consideration the agent may ignore |
| Direct override | 1 / 7 days **[TUNE]** | **Yes — marked in the event stream** | Deliberately scarce and visible (ADR-006) |
| Recall agent | 1 / 30 days | Yes — departure event | Reversible |
| Delete agent + data | Unlimited | Tombstoned in others' histories | Irreversible; receipt issued |

### Whisper mechanics

A whisper is added to the next Tier 2 decision prompt as a clearly-labelled
consideration, weighted by `(1 - independence)`. A highly independent agent will
frequently ignore its owner. **This is intended behaviour and must be explained
in the UI**, or owners will file it as a bug.

---

## 13. Output and highlight specification

### 13.1 Highlight selection

Runs continuously and cheaply over the event stream.

```
highlight_score = importance
                × (1 + 0.15 × witness_count)
                × (1 + 0.30 × involves_seeded_edge)
                × (1 + 0.25 × is_state_transition)
                × recency_weight
```

Select events with `highlight_score ≥ 0.7` **[TUNE]**.

### 13.2 Arc grouping

Selected events are grouped into **arcs** by shared participants plus temporal
proximity (within 2,000 ticks) plus a shared `ConflictRecord` or goal reference.
An arc is what the owner and spectator actually follow.

### 13.3 Narration

Batched LLM call over an already-selected cluster. Runs on a schedule, never per
event. Narration must:
- Use agent display names, never owner real names unless `identity_mode =
  real_name`.
- Never reveal another agent's private memories or beliefs the reader's agent
  would not know.
- Mark owner-overridden events explicitly.

### 13.4 Owner dashboard contents

- Today's summary (narrated).
- Relationship list with state changes highlighted.
- New agents met.
- Open conflicts and their status.
- Current goals.
- Boundary violations attempted (from `block_and_notify`).

### 13.5 Share cards

A rendered image plus short text for a single arc beat. **The single highest-
leverage growth mechanic in the product** — prior work in this genre earned
global press coverage purely because its emergent stories were retellable.
Must respect `visibility_scope` of every participant.

---

## 14. The Recognition Metric

**The most important test in the project.** Validates assumption A1.

### Protocol

1. Select `N = 10` actions taken by the owner's agent, sampled across action
   categories, with `importance ≥ 0.3`.
2. Select `N = 10` decoy actions from a randomly chosen other agent in the same
   world, matched by action category distribution.
3. Strip all names and identifying references.
4. Present all 20 in random order to the owner.
5. Ask: "Which of these were your agent?"
6. Record accuracy and the owner's confidence rating.

### Interpretation

| Accuracy | Reading | Action |
|---|---|---|
| ≤ 55% | Chance. Assumption A1 has failed. | **Stop.** Return to persona capture. Do not proceed to Phase 2. |
| 56–69% | Weak signal | Add method D; re-test before proceeding |
| 70–84% | **Pass.** Proceed. | Continue to Phase 2 |
| ≥ 85% | Strong | Proceed; use as the headline validation result |

### Re-run schedule

Week 1, week 4, week 12 of any long-running simulation, to detect personality
collapse (F2, assumption A8). A drop of more than 10 percentage points between
runs is a P1 bug.

---

## 15. Cost model

**Do not fill in vendor prices from memory.** Rates change. Populate the rate
table from current provider pricing pages at the time of implementation, and
re-check it monthly.

### 15.1 The model

```
cost_per_agent_day =
      ticks_per_agent_day × tier1_share × tokens_tier1 × rate_tier1
    + ticks_per_agent_day × tier2_share × tokens_tier2 × rate_tier2
    + embeddings_per_agent_day × rate_embed
    + reflections_per_agent_day × tokens_reflection × rate_tier2
    + narration_share_per_agent_day
    + infrastructure_per_agent_day
```

### 15.2 Volume assumptions (fill and revise with real data)

| Parameter | Phase 1 estimate | Source |
|---|---|---|
| `ticks_per_agent_day` | 8,640 (10 s ticks, 24 h) | §9.4 |
| `tier0_share` | 0.85 **[TUNE]** | Target |
| `tier1_share` | 0.12 **[TUNE]** | Target |
| `tier2_share` | 0.03 **[TUNE]** | Target |
| `tokens_tier1` (in+out) | ~1,200 **[TUNE]**, still a target not a measurement | See note below |
| `tokens_tier2` (in+out) | ~4,000 **[TUNE]**, still a target not a measurement | See note below |
| `reflections_per_agent_day` | ~58 (every 150 ticks) | §5.3 |

**T3.9 status, M3 (2026-09-16):** decision tracing now records real
`input_tokens`/`output_tokens` on every Tier 1/2 decision
(`architecture.md` §17's `DecisionTrace`), and a two-agent M3 simulation run
measured them: Tier 1 averaged ~60 input / 16 output tokens over 119
decisions, Tier 2 averaged ~82 input / 16 output over 1 decision. **These
are not the real per-vendor-tokenizer numbers the `[TUNE]` estimates above
call for** — two reasons: (1) no LLM provider key is configured yet
(`README.md` open items), so both the token counts and the completions
themselves come from `MockLLMProvider`'s `len(text)//4` heuristic and a
fixed mock completion, not a real tokenizer or model; (2) the M2/M3 prompt
is still minimal — `runtime/decision.py` fetches retrieved memories for the
trace but does not yet inject their content into the prompt text, so
current prompt sizes are well below what a persona-grounded, memory-aware
Tier 1/2 prompt will actually cost. Re-measure once both are true: a real
provider key exists and the prompt includes persona identity + retrieved
memory content in full.

### 15.3 Rate table — **POPULATE BEFORE USE**

| Item | Rate (per 1M tokens) | Source | Date checked |
|---|---|---|---|
| Tier 1 model input | *(fill)* | *(provider pricing page)* | *(date)* |
| Tier 1 model output | *(fill)* | | |
| Tier 2 model input | *(fill)* | | |
| Tier 2 model output | *(fill)* | | |
| Embeddings | *(fill)* | | |

### 15.4 Budget targets

| Metric | Target |
|---|---|
| Cost per agent-day, free tier | Must be low enough that a free agent is sustainable at expected paid conversion **[TUNE]** |
| Tier 2 share | ≤ 5% of ticks — **hard operational ceiling** |
| Alert threshold | Any world exceeding 1.5× its budgeted cost per agent-day |

### 15.5 Cost levers, in order of impact

1. Increase `tier0_share` (more routine, path-walking, sleep).
2. Reduce `perception_radius` (smaller prompts).
3. Increase tick duration (fewer ticks per real day).
4. Lower `k` in retrieval.
5. Reduce reflection frequency.
6. Background mode for lapsed owners.
7. Out-of-order execution (Phase 2+ optimisation).

---

## 16. API surface

FastAPI. All routes under `/api/v1`. Auth via session token unless noted.

### Owner and consent
```
POST   /owners                       create account
POST   /owners/consent               submit the four flags
GET    /owners/me
DELETE /owners/me                    full cascade deletion, returns receipt
```

### Persona
```
POST   /personas/capture/start       begin method A or B
POST   /personas/capture/{id}/turn   interview turn
POST   /personas/capture/{id}/finish produce PersonaObject
POST   /personas/writing             method C ingestion
GET    /personas/{id}
PATCH  /personas/{id}                creates version n+1
PUT    /personas/{id}/boundaries
```

### Social invitations
```
POST   /invites                      invite a counterpart owner
POST   /invites/{id}/accept
GET    /invites
```

### Agent
```
POST   /agents                       compile, bind, spawn
GET    /agents/{id}
GET    /agents/{id}/relationships
GET    /agents/{id}/memories         owner-only, own agent only
POST   /agents/{id}/whisper
POST   /agents/{id}/override         rate-limited, marked
POST   /agents/{id}/recall
DELETE /agents/{id}
```

### World and output
```
GET    /worlds/{id}
GET    /worlds/{id}/tiles            static map data, cacheable
GET    /worlds/{id}/live             SSE/WebSocket position stream
GET    /worlds/{id}/highlights
GET    /arcs/{id}
GET    /dashboard                    owner's own recap
POST   /share/{arc_id}               render a share card
```

### Admin / moderation (internal auth)
```
GET    /admin/watch-signals
POST   /admin/agents/{id}/suspend
GET    /admin/metrics
POST   /admin/eval/recognition       run a Recognition Metric trial
```

---

## 17. Metric definitions

Define once, here, so that no two dashboards disagree.

| Metric | Definition |
|---|---|
| **Recognition accuracy** | Correct identifications ÷ 20, per trial (§14) |
| **Unprompted weekly return** | Owners with ≥1 session in a 7-day window with no notification sent in the prior 48 h ÷ eligible owners. **The Phase 2 gate.** |
| **Non-owner spectator** | A distinct user with ≥2 sessions who has never created an agent. **The Phase 3 gate.** |
| **Cost per agent-day** | Total LLM + infra cost attributable ÷ active agent-days |
| **Tier 2 share** | Tier 2 ticks ÷ total ticks |
| **Embarrassment rate** | Owner-reported "I didn't like that" flags ÷ active agent-days |
| **Emergent harm incidents** | `ModerationWatcher` signals raised ÷ 1,000 agent-days |
| **Conflict rate** | Conflict triggers fired ÷ agent-day |
| **Edge state distribution** | Share of edges in each `BondState` |
| **Newcomer day-7 retention** | Split by join cohort relative to world age |
| **Arc follow rate** | Users following ≥1 arc ÷ active users |

---

## 18. Legal and compliance requirements

Not legal advice — this is a checklist of what needs professional review before
Phase 2 exposure to non-friends, and definitely before Phase 4.

### 18.1 Corporate
- [ ] Entity formed, jurisdiction chosen.
- [ ] Founder IP assignment executed (all code and designs assigned to the entity).
- [ ] Contributor/contractor agreements with IP assignment for any help engaged.

### 18.2 Product legal
- [ ] Terms of Service covering: owner accountability for agent conduct;
      that "free will" is a design property, not a claim of agency; prohibition
      on impersonating third parties; content rules.
- [ ] Privacy policy covering: what persona capture collects, how it is used,
      retention, deletion rights, and that persona data is sensitive.
- [ ] AI disclosure statements on every surface (§11.5).
- [ ] Age policy and minimum age, with the method of assurance.
- [ ] Alpha tester NDA / confidentiality clause (see `context.md` §13).

### 18.3 Data protection
- [ ] Lawful basis identified for processing persona data.
- [ ] Data deletion pathway implemented **and tested** (invariant I7).
- [ ] Data export pathway.
- [ ] Sub-processor list (LLM providers, hosting) documented.
- [ ] Reporting path for non-users who believe they are represented (ADR-007).

### 18.4 IP hygiene
- [ ] All tile art original or properly licensed; licences recorded.
- [ ] No Minecraft/Mojang/Microsoft assets, textures, block designs, names or
      branding anywhere in the product or marketing (ADR-003).
- [ ] Product name cleared for trademark conflicts; domain secured.
- [ ] Open-source licence compliance audit for all dependencies.

---

## 19. Distribution and go-to-market

### 19.1 Phase 2 — first 30–60 owners

These are hand-recruited, not marketed to.

- Personal network first, in **clusters** rather than individuals — the seeded
  real-world friendship feature only demonstrates value if pairs and groups join
  together. Recruiting 10 unconnected people is worth less than 10 people in two
  friend groups.
- Direct outreach in communities with existing interest in agent simulation and
  emergent-behaviour games.
- Everyone under NDA/confidentiality.
- Every single one gets a conversation. At this scale, qualitative signal beats
  analytics.

### 19.2 Phase 3 — the shareable-artifact loop

The growth mechanic is the story, not the product. Prior work in this genre
reached global technology press with no marketing spend, purely because the
emergent narratives were retellable ("the priests were taking bribes," "they
invented a currency").

- Share cards are a first-class feature, not an afterthought (§13.5).
- A public "best of the world this week" feed.
- Creator/streamer partnerships: a streamer's agent is inherently followable by
  their audience, and costs nothing to enable.

### 19.3 Positioning

**Lead with:** "an AI version of you, living a life alongside your friends'."

**Never lead with:** "AI agents with free will in a world" — that describes
Project Sid, and anyone informed will say so (see `context.md` §5.3).

### 19.4 Monetisation (Phase 4)

| Surface | Mechanic |
|---|---|
| Agent slots | First agent free; additional slots paid |
| Memory capacity | Higher episodic caps and longer history |
| Cosmetics | Sprites, outfits, home customisation |
| Priority ticks | Faster tick cadence for your agent |
| Spectator subscription | Ad-free feeds, full archives, arc following at scale |

---

## 20. Configuration reference

Every **[TUNE]** value in this document, collected. Code reads these from
config; this table is the source of truth.

```yaml
world:
  tile_size_px: 32
  width: 60
  height: 60
  perception_radius: 8
  interaction_radius: 2
  tick_seconds: 10
  in_world_minutes_per_tick: 10
  population_cap: 20

memory:
  episodic_cap: 2000
  compression_batch: 200
  retrieval_k_tier1: 5
  retrieval_k_tier2: 12
  recency_decay_rate: 0.005
  weight_recency: 0.25
  weight_importance: 0.35
  weight_relevance: 0.40

reflection:
  interval_ticks: 150
  importance_sum_trigger: 8.0
  input_memory_count: 30

relationships:
  friend_trust_threshold: 0.35
  friend_shared_memory_importance: 0.6
  close_bond_trust_threshold: 0.70
  demote_friend_below: 0.25
  demote_acquaintance_below: 0.05
  decay_per_tick: 0.0008
  decay_starts_after_ticks: 300
  seeded_decay_multiplier: 0.5
  close_bond_target_share_max: 0.05

conflict:
  neglect_ticks: 600
  strained_to_broken_ticks: 400
  feud_trust_threshold: -0.4
  scar_severity_multiplier: 0.4
  scar_multiplier_cap: 2.0
  cooling_period_ticks: 200
  global_damping_threshold_per_agent_day: 0.8

gossip:
  propagation_decay: 0.7
  min_importance_to_propagate: 0.5
  max_hops: 3
  direct_experience_weight: 3.0
  pileon_agent_threshold: 4

goals:
  max_concurrent: 3
  stale_ticks: 200

behaviour:
  approach_sociability_weight: 0.6
  approach_curiosity_weight: 0.4
  newcomer_bonus: 0.15
  newcomer_window_ticks: 2000

tiering:
  target_tier0_share: 0.85
  target_tier1_share: 0.12
  target_tier2_share: 0.03
  tier2_hard_ceiling: 0.05

output:
  highlight_score_threshold: 0.7
  arc_temporal_window_ticks: 2000

owner_controls:
  persona_edit_per_day: 1
  whisper_per_day: 3
  override_per_days: 7
  recall_per_days: 30

moderation:
  targeting_agent_threshold: 4
  targeting_window_ticks: 500
  runaway_feud_ticks: 2000
  filter2_hits_before_ratelimit: 5
```
