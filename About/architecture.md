# architecture.md — Otherworld

> **Purpose of this file.** The structural "how." Planes, components, their
> responsibilities and boundaries, the data models, and how data flows through
> the system. Read `context.md` first for the reasoning behind these choices.
>
> Behavioural rules, thresholds and exact numbers live in `spec.md`, not here.
> If you find a magic number in this file, it belongs in `spec.md`.
>
> **Status:** Living document.
> **Last updated:** 2026-09-14

---

## Table of contents

1. [System overview — the six planes](#1-system-overview--the-six-planes)
2. [Plane 1 — Owner](#2-plane-1--owner)
3. [Plane 2 — Persona](#3-plane-2--persona)
4. [Plane 3 — Agent runtime](#4-plane-3--agent-runtime)
5. [Plane 4 — Safety](#5-plane-4--safety)
6. [Plane 5 — World](#6-plane-5--world)
7. [Plane 6 — Output](#7-plane-6--output)
8. [Control plane](#8-control-plane)
9. [Data models](#9-data-models)
10. [The action registry](#10-the-action-registry)
11. [Storage architecture](#11-storage-architecture)
12. [LLM provider abstraction and tiering](#12-llm-provider-abstraction-and-tiering)
13. [Scheduling and concurrency](#13-scheduling-and-concurrency)
14. [End-to-end sequence walkthroughs](#14-end-to-end-sequence-walkthroughs)
15. [Repository and module layout](#15-repository-and-module-layout)
16. [Technology decisions](#16-technology-decisions)
17. [Observability](#17-observability)
18. [Security model](#18-security-model)
19. [Failure modes and mitigations](#19-failure-modes-and-mitigations)

---

## 1. System overview — the six planes

Data flows downward. Control flows upward. Each plane may only call the plane
directly below it, plus shared infrastructure. **No plane may skip a layer.**

```
┌───────────────────────────────────────────────────────────┐
│ PLANE 1 — OWNER                                           │
│ Signup · consent gate · identity mode · social opt-in     │
└───────────────────────────┬───────────────────────────────┘
                            ▼
┌───────────────────────────────────────────────────────────┐
│ PLANE 2 — PERSONA                                         │
│ Capture (A/B/C/D) · persona object · compile · bind       │
└───────────────────────────┬───────────────────────────────┘
                            ▼
┌───────────────────────────────────────────────────────────┐
│ PLANE 3 — AGENT RUNTIME                                   │
│ Tick loop · memory · reflection · goal stack · tiering    │
└───────────────────────────┬───────────────────────────────┘
                            ▼
┌───────────────────────────────────────────────────────────┐
│ PLANE 4 — SAFETY                    ◀── nothing bypasses  │
│ Owner boundaries · platform policy · sandbox · moderation │
└───────────────────────────┬───────────────────────────────┘
                            ▼
┌───────────────────────────────────────────────────────────┐
│ PLANE 5 — WORLD                                           │
│ Tile map · scheduler · relationship graph · groups        │
└───────────────────────────┬───────────────────────────────┘
                            ▼
┌───────────────────────────────────────────────────────────┐
│ PLANE 6 — OUTPUT                    ◀── read-only         │
│ Event stream · highlights · live view · dashboard         │
└───────────────────────────────────────────────────────────┘

        ┌──────────────────────────────────────────┐
        │ CONTROL PLANE (cross-cutting)            │
        │ Owner controls · moderation · sys events │
        └──────────────────────────────────────────┘
```

### Invariants

| # | Invariant | Enforced by |
|---|---|---|
| I1 | No action reaches Plane 5 without passing Plane 4. | `world.apply_action` accepts only a `ValidatedAction` type. |
| I2 | Plane 6 never writes to Planes 1–5. | Read-only DB role for output services. |
| I3 | An agent can only emit actions present in the action registry. | `ActionRegistry.resolve()` raises on unknown action. |
| I4 | An agent perceives only what the world scopes to it. | `world.observe(agent_id)` is the sole perception entry point. |
| I5 | Persona edits never mutate existing memories. | Persona objects are versioned; memories reference agent, not version. |
| I6 | Every executed action produces exactly one event record. | Written transactionally in `resolve`. |
| I7 | Deleting an owner cascades to every store. | FK cascade + explicit deletion job, verified by test. |

---

## 2. Plane 1 — Owner

### Responsibilities
- Account lifecycle: signup, authentication, deletion.
- The **consent gate** — four flags that every downstream plane reads.
- Social opt-in: the mutual invitation flow for seeded relationships.
- Billing identity (Phase 4).

### Components

| Component | Responsibility |
|---|---|
| `AuthService` | Sessions, credentials, password reset. |
| `ConsentGate` | Collects and stores the four permission flags; blocks agent creation until complete. |
| `SocialInviteService` | Mutual-opt-in invitations; creates `SeededEdgeRequest` records. |
| `DeletionService` | Cascading erasure across all stores; produces a deletion receipt. |

### The four consent flags

| Flag | Values | Read by |
|---|---|---|
| `identity_mode` | `real_name` / `pseudonymous` / `anonymous` | Output plane (attribution), Safety plane (real-person rules). |
| `visibility_scope` | `public` / `friends` / `private` | Output plane (who may spectate). |
| `third_party_consent_intent` | `bool` | Persona plane (whether social-layer capture is offered at all). |
| `liability_acknowledged` | `bool` + timestamp + ToS version | Legal record. Blocks agent creation if false. |

**Rule:** `ConsentGate.is_complete(owner) == False` ⇒ agent creation is refused
at the API layer. Spectating is still permitted.

---

## 3. Plane 2 — Persona

Runs once at agent creation and again on edits. **Not in the hot path**, so it
may be slow and expensive.

### Pipeline

```
ConsentGate ──▶ Capture (A | B | C | D) ──▶ PersonaObject (4 layers)
                                                     │
                                                     ▼
                                          Compiler ──▶ AgentBundle
                                                     │
                                                     ▼
                                          Binder ────▶ spawnable Agent
```

### Capture methods

| ID | Method | Produces | Phase |
|---|---|---|---|
| A | Structured questionnaire | Trait vector | M1 |
| B | Conversational interview (interviewer agent) | Trait vector + voice profile | M1 — **default** |
| C | Writing-sample ingestion | Voice profile | Phase 2 |
| D | Scenario replay | Decision-policy weights | Phase 2+ |

All four write into the same `PersonaObject`. Later methods refine earlier
values rather than replacing them; each field records its `source_method` and
`confidence`.

### The four persona layers

| Layer | Consumed by | Notes |
|---|---|---|
| `voice` | Dialogue generation (Tier 1/2 prompts) | Diction, rhythm, humour, verbosity, profanity baseline. |
| `values` | Decision policy | Numeric trait vector. Drives action selection weights and conflict style. |
| `social` | Relationship seeding | **Only** populated when `third_party_consent_intent` is true and the counterpart has accepted. |
| `boundaries` | Safety validator | Owner's never-do list. A safety input, deliberately not a personality input. |

### Compiler

Takes a `PersonaObject` and produces an `AgentBundle`:

- `identity_prompt` — assembled from `voice` + `values`.
- `decision_weights` — numeric policy derived from `values` (+ method D if present).
- `initial_goals` — seeded from ambition/curiosity traits.
- `boundary_ruleset` — compiled predicate list from `boundaries`.
- `action_space_ref` — pointer to the registry version. **Not a copy.**

### Binder

Attaches the bundle to a runtime agent and registers it with the scheduler.
This is the step where containment is applied (see ADR-002): the agent's
callable surface is the registry and nothing else.

### Versioning rule

`PersonaObject` is immutable once compiled. An edit creates version *n+1*. The
agent points at the latest version; **memories point at the agent, not the
version.** This preserves history across persona edits (invariant I5).

---

## 4. Plane 3 — Agent runtime

The hot path. Everything here runs per agent, per tick.

### The six phases

| Phase | Input | Output | Cost |
|---|---|---|---|
| 1. Perceive | `world.observe(agent_id)` | `Observation` | Free |
| 2. Retrieve | `Observation` | `RetrievedContext` | Cheap (vector query) |
| 3. Decide | `RetrievedContext` | `ProposedAction` | **The expensive one** |
| 4. Validate | `ProposedAction` | `ValidatedAction` or rejection | Cheap (rules) + optional classifier |
| 5. Act | `ValidatedAction` | world mutation | Free |
| 6. Resolve | world mutation | memories, deltas, `EventRecord` | Cheap |

### Components

| Component | Responsibility |
|---|---|
| `TickScheduler` | Decides which agents tick, when, and at which tier. |
| `PerceptionService` | Builds a radius-scoped observation from the tile map. |
| `MemoryStore` | Episodic memories and beliefs; vector-backed retrieval. |
| `RetrievalService` | recency × importance × relevance scoring. |
| `DecisionEngine` | Assembles the prompt, selects tier, calls the provider, parses to a `ProposedAction`. |
| `ReflectionService` | Periodic synthesis of memories into beliefs; memory compression. |
| `GoalStack` | Per-agent ordered goals; supports form/abandon/adopt. |
| `Resolver` | Writes memories for all witnesses, relationship deltas, event record. |

### Memory architecture

Two tiers:

- **Episodic** — raw observations. High volume. Each has an `importance` score
  assigned at write time.
- **Belief** — reflection output. Low volume, high signal. Beliefs are the only
  thing that survives compression.

**Compression rule:** when an agent's episodic store exceeds its cap, the oldest
low-importance episodic memories are synthesised into beliefs and deleted.
Beliefs are never auto-deleted. This is the defence against retrieval quality
degrading as memory grows.

### Perception scoping (tile-map specific)

`PerceptionService` returns:
- Agents within `perception_radius` tiles, with their visible state.
- Static features of the current zone.
- Anything *addressed to* this agent since its last tick, regardless of distance
  (so speech isn't lost to a tick-timing race).
- Time of day, zone, weather/season if present.

**Unscoped perception is forbidden.** It is both the primary cost lever and the
main context-window risk.

### Decision engine and re-prompting

If Plane 4 rejects a proposed action, the engine re-prompts **once** with an
appended constraint note. A second rejection falls through to a safe default
action (`idle`). The agent never crashes on rejection.

---

## 5. Plane 4 — Safety

Sits between runtime and world. Nothing bypasses it (invariant I1).

### Filter order — strictly sequential, first failure stops evaluation

| Order | Filter | Source of rules | On failure |
|---|---|---|---|
| 1 | **Owner boundaries** | `boundary_ruleset` from the persona | Reject, re-prompt once |
| 2 | **Platform policy** | Global policy set (see `spec.md`) | Reject, log, possible moderation escalation |
| 3 | **Real-person protection** | Named-entity check against real people | Hard reject, always logged |
| 4 | **World legality** | Physics/state preconditions | Reject, re-prompt once |

Owner boundaries are evaluated first so that the cheapest and most
owner-specific filter short-circuits before any classifier cost is incurred.

### Components

| Component | Responsibility |
|---|---|
| `Validator` | Runs the four filters in order; returns `ValidatedAction` or `Rejection`. |
| `ActionRegistry` | The enumerated, code-registered action list. Security-critical. |
| `PolicyEngine` | Platform content rules; may call a classifier. |
| `RealPersonGuard` | Blocks content targeting identifiable real people. |
| `ModerationWatcher` | Consumes the event stream, detects emergent harm patterns, applies damping or escalation. |

### Moderation watch triggers

Detected from the event stream, not from single actions:

| Trigger | Signal | Response |
|---|---|---|
| Sustained targeting | N+ agents acting negatively on one agent over a window | Contagion damping; mediator injection |
| Policy-violating dialogue | Filter 2 hit rate for one agent | Rate-limit, then suspend |
| Real-person targeting | Filter 3 hit | Hard block; owner notified; account review |
| Runaway feud | Feud duration past threshold | Forced cooling period or spatial separation |
| Impersonation | Persona resembles a known third party | Account action |

### The containment guarantee

Agents have **no** code execution, tool acquisition, filesystem access, network
access, or ability to define new actions. This is a property of the runtime
binding, not of any instruction text. See ADR-002.

---

## 6. Plane 5 — World

The only shared, multi-tenant plane.

### 6.1 Tile map model

Chosen model: **2D top-down walkable grid**, Pokémon-overworld style (ADR-003).

| Concept | Definition |
|---|---|
| `Tile` | One grid cell. Has coordinates, a terrain type, and a walkability flag. |
| `Zone` | A named contiguous region of tiles (e.g. "market square", "north woods"). Used for narrative labelling and for cheap coarse-grained queries. |
| `Feature` | A static interactable placed on a tile (bench, well, workbench, resource node). |
| `WorldMap` | The full tile grid for one world instance, plus zones and features. |
| `Position` | An agent's `(x, y)` tile coordinate plus facing direction. |

**Grid, not continuous.** Agents occupy exactly one tile. Movement is
tile-to-tile. This keeps proximity queries trivial and makes the simulation
deterministic and replayable.

### 6.2 Movement and pathfinding

- Pathfinding is **A\* on the walkability grid**, computed server-side.
- A `move_to` action stores a path; subsequent ticks consume it one tile at a
  time without re-invoking the decision engine. **This is a major cost saver** —
  walking is Tier 0.
- Paths are invalidated and recomputed if the destination becomes unreachable.

### 6.3 Proximity and encounters

- `perception_radius` is measured in tiles (Chebyshev distance).
- An **encounter** is registered when two agents come within
  `interaction_radius` and at least one has no recent interaction record with
  the other.
- Encounters are what escalate a tick to Tier 2 (see §12).

### 6.4 Spatial indexing

Agent positions are indexed by **zone + tile bucket**, so proximity queries are
a bounded lookup rather than a scan. With a grid world this is simple and fast;
do not over-engineer it.

### 6.5 Relationship engine

One record per **edge** — a pair of agents that have actually had contact.
Edges are materialised lazily; a world with N agents does not pre-create N²/2
rows.

Each edge carries:
- `trust` — numeric score driving state promotion.
- `bond_state` — the state machine below.
- `conflict_log` — permanent list of scars.
- `last_contact_tick` — drives decay.
- `seeded` — whether this edge came from a real-world friendship (affects
  conflict resilience).

### 6.6 Bond state machine

```
Stranger ──▶ Acquaintance ──▶ Friend ──▶ Close bond
                                 │            │
                                 ▼            ▼
                              ┌────────────────────┐
                              │      Strained      │
                              └─────────┬──────────┘
                     ┌─────────────────┼─────────────────┐
                     ▼                 ▼                 ▼
                 Repaired            Broken             Feud
              (→ back to Friend,  (severed, may   (active hostility,
               keeps the scar)     reconcile)      contagion source)
```

Exact thresholds, promotion conditions and decay rates are in `spec.md`.

### 6.7 Social aggregation

Derived from the edge set, recomputed periodically rather than per tick:

| Output | Derived from | Used for |
|---|---|---|
| **Goal coupling** | Friend+ edges | Friends adopt each other's goals — the mechanism behind group formation and role specialisation. |
| **Gossip propagation** | Belief sharing weighted by trust in the messenger | Reputation forms without direct contact; the highest narrative value per unit of compute in the system. |
| **Cliques** | Connected components of mutual Friend+ edges | Faction detection, exclusion detection. |
| **Factions** | Cliques joined by a Feud edge between key members | Narrative arcs; moderation watch input. |

### 6.8 World instances and population caps

Worlds are **capped and horizontally replicated** rather than allowed to grow
without bound. A new world instance is spun up when a world reaches its cap.
This solves newcomer integration and bounds edge count simultaneously. Cap value
is in `spec.md` and is expected to change based on M5 data.

### 6.9 Exogenous events

The world injects periodic events to prevent social equilibrium: resource
scarcity shifts, seasons, shared challenges requiring cooperation, new zones
opening. Emitted by the control plane, applied by the world plane.

---

## 7. Plane 6 — Output

**Read-only** (invariant I2). Consumes the event stream; never writes back.

### Components

| Component | Responsibility |
|---|---|
| `EventStream` | Append-only log of every resolved action. |
| `ImportanceScorer` | Assigns narrative significance; shared scoring logic with memory importance. |
| `HighlightEngine` | Selects high-importance events, groups them into arcs, generates narration. |
| `LiveWorldView` | Real-time tile-map render feed for spectators. |
| `OwnerDashboard` | "My agent today" — recap, relationship graph, history. |
| `ShareCardService` | Renders a shareable image/summary of a story beat. |
| `RecognitionHarness` | Runs the Recognition Metric test. Lives here because it consumes events. |

### Two-stage highlight generation

1. **Selection** — rank events by importance; filter by visibility scope.
2. **Narration** — turn the selected cluster into readable prose.

Selection is cheap and runs continuously. Narration is an LLM call and runs
batched, on a schedule, only over already-selected events.

### Attribution and visibility

Every output surface reads `identity_mode` and `visibility_scope` from Plane 1
before rendering. An agent belonging to a `private` owner never appears in a
public feed, even if it participated in a public event — in which case it is
rendered as an anonymised participant.

---

## 8. Control plane

Cross-cutting. Three actors with different powers.

### Owner controls

| Control | Binding? | Constraint |
|---|---|---|
| Edit persona | Forward-only | Never rewrites memory (I5) |
| Add/remove boundary | **Binding**, forward-only | Applied at Validator filter 1 |
| Whisper / advise | **Non-binding** | Injected as a weighted consideration; agent may ignore |
| Direct override | **Binding** | Rare, rate-limited, **visibly marked** in the event stream |
| Recall agent | Binding | Emits an in-world departure event |
| Delete agent + data | Binding | Full cascade, deletion receipt |

### Moderation controls
See §5. Acts at the Validator wherever possible, not after publication
(principle 6 in `context.md`).

### System events
Scheduled exogenous events, world instance lifecycle, seasonal changes.

---

## 9. Data models

Canonical shapes. Python/Pydantic naming. These are the M0 deliverable — write
these before anything else.

### 9.1 Owner and consent

```python
class IdentityMode(StrEnum):
    REAL_NAME = "real_name"
    PSEUDONYMOUS = "pseudonymous"
    ANONYMOUS = "anonymous"

class VisibilityScope(StrEnum):
    PUBLIC = "public"
    FRIENDS = "friends"
    PRIVATE = "private"

class ConsentFlags(BaseModel):
    identity_mode: IdentityMode
    visibility_scope: VisibilityScope
    third_party_consent_intent: bool
    liability_acknowledged: bool
    tos_version: str
    acknowledged_at: datetime

class Owner(BaseModel):
    id: UUID
    handle: str
    email: EmailStr
    consent: ConsentFlags | None
    created_at: datetime
    last_active_at: datetime
    status: Literal["active", "lapsed", "suspended", "deleted"]
```

### 9.2 Persona

```python
class TraitVector(BaseModel):
    """All values 0.0–1.0. See spec.md for the meaning of each."""
    loyalty: float
    honesty: float
    risk_tolerance: float
    conflict_directness: float
    forgiveness: float
    grudge_retention: float
    generosity: float
    ambition: float
    sociability: float
    curiosity: float
    independence: float
    emotional_expressiveness: float

class VoiceProfile(BaseModel):
    verbosity: float                 # 0 = terse, 1 = talkative
    formality: float
    humour_style: Literal["dry", "warm", "absurd", "sarcastic", "none"]
    profanity_baseline: float
    characteristic_phrases: list[str]
    diction_notes: str

class SeededRelationship(BaseModel):
    counterpart_owner_id: UUID
    claimed_bond: Literal["acquaintance", "friend", "close"]
    mutual_accepted: bool            # MUST be True to take effect (ADR-007)
    accepted_at: datetime | None
    shared_context: list[str]

class BoundaryRule(BaseModel):
    id: UUID
    description: str
    predicate: str                   # compiled matcher expression
    severity: Literal["block", "block_and_notify"]

class PersonaObject(BaseModel):
    id: UUID
    owner_id: UUID
    version: int
    voice: VoiceProfile
    values: TraitVector
    social: list[SeededRelationship]
    boundaries: list[BoundaryRule]
    source_methods: list[Literal["A", "B", "C", "D"]]
    field_confidence: dict[str, float]
    created_at: datetime
    compiled_at: datetime | None
```

### 9.3 Agent

```python
class AgentStatus(StrEnum):
    ACTIVE = "active"
    BACKGROUND = "background"        # lapsed owner, reduced tick rate
    RECALLED = "recalled"
    SUSPENDED = "suspended"

class Position(BaseModel):
    x: int
    y: int
    facing: Literal["n", "s", "e", "w"]

class Goal(BaseModel):
    id: UUID
    description: str
    priority: float
    origin: Literal["seeded", "self", "adopted"]
    adopted_from_agent_id: UUID | None
    created_tick: int
    completed_tick: int | None

class Agent(BaseModel):
    id: UUID
    owner_id: UUID
    persona_version: int
    world_id: UUID
    display_name: str
    status: AgentStatus
    position: Position
    goals: list[Goal]
    current_path: list[tuple[int, int]]   # remaining A* path, Tier 0 walking
    last_tick: int
    created_at: datetime
```

### 9.4 Memory

```python
class MemoryKind(StrEnum):
    EPISODIC = "episodic"
    BELIEF = "belief"

class MemoryRecord(BaseModel):
    id: UUID
    agent_id: UUID
    kind: MemoryKind
    content: str
    embedding: list[float]
    importance: float                 # 0.0–1.0, assigned at write
    tick: int
    subjects: list[UUID]              # agents this memory is about
    source_event_id: UUID | None
    derived_from: list[UUID]          # for beliefs: the memories synthesised
    created_at: datetime
```

### 9.5 Relationship

```python
class BondState(StrEnum):
    STRANGER = "stranger"
    ACQUAINTANCE = "acquaintance"
    FRIEND = "friend"
    CLOSE_BOND = "close_bond"
    STRAINED = "strained"
    REPAIRED = "repaired"
    BROKEN = "broken"
    FEUD = "feud"

class ConflictTrigger(StrEnum):
    BETRAYAL = "betrayal"
    VALUE_CLASH = "value_clash"
    RESOURCE_COMPETITION = "resource_competition"
    NEGLECT = "neglect"
    CONTAGION = "contagion"

class ConflictRecord(BaseModel):
    """A scar. Permanent. Makes re-escalation on the same theme faster."""
    id: UUID
    trigger: ConflictTrigger
    theme: str
    severity: float
    occurred_tick: int
    resolved_tick: int | None
    resolution: Literal["repaired", "broken", "feud"] | None

class RelationshipEdge(BaseModel):
    id: UUID
    world_id: UUID
    agent_a_id: UUID                  # ordered: a_id < b_id, to keep edges unique
    agent_b_id: UUID
    trust: float                      # signed; see spec.md
    bond_state: BondState
    seeded: bool
    conflict_log: list[ConflictRecord]
    shared_memory_ids: list[UUID]
    contact_count: int
    last_contact_tick: int
    created_tick: int
```

**Uniqueness rule:** always store with `agent_a_id < agent_b_id` so an edge has
exactly one row. Enforce with a DB constraint.

### 9.6 World

```python
class TerrainType(StrEnum):
    GRASS = "grass"
    PATH = "path"
    WATER = "water"
    WALL = "wall"
    FLOOR = "floor"
    FOREST = "forest"

class Tile(BaseModel):
    x: int
    y: int
    terrain: TerrainType
    walkable: bool
    zone_id: UUID | None

class Feature(BaseModel):
    id: UUID
    x: int
    y: int
    kind: str                         # bench, well, workbench, resource node
    state: dict

class Zone(BaseModel):
    id: UUID
    world_id: UUID
    name: str
    bounds: tuple[int, int, int, int]  # x0, y0, x1, y1

class World(BaseModel):
    id: UUID
    name: str
    width: int
    height: int
    current_tick: int
    population: int
    population_cap: int
    status: Literal["open", "full", "archived"]
    created_at: datetime
```

### 9.7 Actions and events

```python
class ActionCategory(StrEnum):
    MOVEMENT = "movement"
    SOCIAL = "social"
    RELATIONAL = "relational"
    MATERIAL = "material"
    INTERNAL = "internal"

class ProposedAction(BaseModel):
    agent_id: UUID
    action: str                       # must exist in the registry
    category: ActionCategory
    targets: list[UUID]
    params: dict
    reasoning: str                    # for the trace log, never shown raw to users
    tier_used: Literal[0, 1, 2]

class ValidatedAction(ProposedAction):
    """Only the Validator may construct this type. Invariant I1."""
    validated_at: datetime
    filters_passed: list[str]

class Rejection(BaseModel):
    agent_id: UUID
    proposed: ProposedAction
    failed_filter: Literal["boundary", "policy", "real_person", "legality"]
    reason: str

class EventRecord(BaseModel):
    id: UUID
    world_id: UUID
    tick: int
    actor_id: UUID
    action: str
    targets: list[UUID]
    witnesses: list[UUID]
    position: Position
    relationship_deltas: list[dict]
    importance: float
    owner_override: bool              # rendered visibly if True (ADR-006)
    created_at: datetime
```

### 9.8 Output

```python
class Highlight(BaseModel):
    id: UUID
    world_id: UUID
    event_ids: list[UUID]
    arc_id: UUID | None               # groups highlights into a storyline
    narration: str
    importance: float
    participants: list[UUID]
    visibility: VisibilityScope
    created_at: datetime

class RecognitionTrial(BaseModel):
    """One run of the core validation test."""
    id: UUID
    owner_id: UUID
    own_agent_action_ids: list[UUID]
    decoy_action_ids: list[UUID]
    owner_selections: list[UUID]
    accuracy: float
    run_at: datetime
    persona_version: int
```

---

## 10. The action registry

**Security-critical file.** Additions require explicit review (ADR-002).

| Category | Action | Targets | Key params | Tier |
|---|---|---|---|---|
| Movement | `move_to` | — | destination tile | 0 |
| Movement | `follow` | 1 agent | — | 0 |
| Movement | `flee` | 0–1 agent | — | 0 |
| Movement | `idle` | — | — | 0 |
| Movement | `sleep` | — | duration | 0 |
| Social | `greet` | 1 agent | — | 1–2 |
| Social | `speak_to` | 1+ agents | utterance | 1–2 |
| Social | `ignore` | 1 agent | — | 1 |
| Social | `join_group` | 1+ agents | — | 1 |
| Social | `leave_group` | — | — | 1 |
| Relational | `confide` | 1 agent | memory ref | 2 |
| Relational | `compliment` | 1 agent | — | 1 |
| Relational | `criticise` | 1 agent | theme | 2 |
| Relational | `apologise` | 1 agent | conflict ref | 2 |
| Relational | `forgive` | 1 agent | conflict ref | 2 |
| Relational | `reject` | 1 agent | — | 2 |
| Relational | `betray` | 1 agent | promise ref | 2 |
| Material | `gather` | — | feature ref | 0 |
| Material | `build` | — | feature kind, tile | 1 |
| Material | `give` | 1 agent | item | 1 |
| Material | `request` | 1 agent | item | 1 |
| Material | `trade` | 1 agent | offer, ask | 2 |
| Material | `take` | 0–1 agent | item | 2 |
| Material | `destroy` | — | feature ref | 2 |
| Internal | `form_goal` | — | description | 2 |
| Internal | `abandon_goal` | — | goal ref | 1 |
| Internal | `reflect` | — | — | 2 |
| Internal | `form_belief` | 1 agent | belief text | 2 |

**Nothing else is callable.** Every behaviour in the entire simulation is a
composition of the above. If a desired behaviour cannot be expressed here,
that is a design conversation, not an ad-hoc addition.

---

## 11. Storage architecture

| Store | Technology | Contents | Retention |
|---|---|---|---|
| Relational | PostgreSQL 16 | Owners, personas, agents, edges, worlds, tiles, events | Indefinite until deletion |
| Vector | pgvector (same DB) | Memory embeddings | Follows memory compression |
| Cache / queue | Redis | Tick queue, perception cache, rate limits, pub/sub for live view | Ephemeral |
| Object | S3-compatible | Share cards, exports, tilesets | Indefinite |
| Trace log | Structured JSON → file, later ClickHouse or similar | Full decision traces | 30 days hot, then archive |

### Key indexes

- `relationship_edges (world_id, agent_a_id, agent_b_id)` — unique.
- `memory_records (agent_id, kind, importance DESC)`.
- `memory_records USING ivfflat (embedding vector_cosine_ops)`.
- `event_records (world_id, tick DESC)`.
- `event_records (importance DESC)` — highlight selection.
- `agents (world_id, zone_id)` — proximity bucket lookup.

### Deletion cascade (invariant I7)

Owner deletion must remove: owner row, all persona versions, all agents, all
memories, all edges where the agent participates, and must **anonymise** (not
delete) event records where the agent was a witness — because deleting those
would corrupt other agents' histories. Anonymisation replaces the agent id with
a tombstone. **This must be covered by an automated test.**

---

## 12. LLM provider abstraction and tiering

### The interface — define this before any call site exists

```python
class LLMProvider(Protocol):
    async def tier1(self, prompt: Prompt) -> Completion: ...
    async def tier2(self, prompt: Prompt) -> Completion: ...
    async def embed(self, text: str) -> list[float]: ...
```

Tier 0 never touches this interface — it is pure Python rules.

**Rule:** no module outside `core/llm/` may import a vendor SDK. Everything goes
through the protocol. Model swapping must be a config change, never a code
change.

### Tier definitions

| Tier | Mechanism | Used for | Target share of ticks |
|---|---|---|---|
| 0 | Deterministic rules | Walking a stored path, sleeping, idling, continuing a routine | Majority |
| 1 | Small/fast model | Ambient chat, low-stakes social actions, greetings | Moderate |
| 2 | Large model | See escalation triggers below | Small |

### Tier 2 escalation triggers — the complete list

An agent escalates to Tier 2 **only** when one of these holds:

1. First encounter with a previously unmet agent.
2. The relationship edge is within a promotion/demotion threshold band.
3. A conflict trigger has fired.
4. A goal is being formed or abandoned.
5. The agent is in a multi-agent group scene (3+ participants).
6. A reflection cycle is due.
7. An owner whisper is pending consideration.

If none hold, the tick may not use Tier 2. This rule is enforced in code, not by
convention.

---

## 13. Scheduling and concurrency

### Tick scheduling

- The world advances in **discrete global ticks**.
- Not every agent acts on every tick. `TickScheduler` assigns each agent a tick
  cadence based on status and situation:
  - `ACTIVE` + in a scene → every tick
  - `ACTIVE` + idle/walking → reduced cadence
  - `BACKGROUND` (lapsed owner) → heavily reduced cadence
- Within a tick, agent decisions are computed **concurrently** but applied
  **in a deterministic order** (by agent id) so that the simulation is
  replayable.

### Determinism requirement

Given the same seed, same world state, and a mocked LLM, a simulation run must
produce identical output. This is not optional — it is the only way to debug
emergent behaviour and the basis of the whole test strategy.

Implications:
- All randomness goes through a seeded RNG owned by the world.
- No wall-clock time in decision logic; use tick numbers.
- LLM responses must be mockable/recordable (see `plan.md` test strategy).

### Out-of-order execution (later optimisation)

Prior work (AI Metropolis) shows meaningful throughput gains by letting agents
that cannot causally affect each other advance out of lockstep. **Do not build
this before Phase 2.** Note it as a known lever when scaling.

---

## 14. End-to-end sequence walkthroughs

### 14.1 New owner → spawned agent

```
Owner signs up
  → ConsentGate collects 4 flags → blocks until complete
  → Capture method B: interviewer agent conversation (15–20 min)
  → PersonaObject v1 written (voice, values; social only if opted in)
  → [optional] SocialInviteService sends mutual invites; on acceptance,
    SeededRelationship.mutual_accepted = True
  → Compiler builds AgentBundle
  → Binder attaches fixed action space
  → World assignment: pick an open world under population cap
  → Spawn at an arrival zone tile (not random)
  → Seeded edges materialised for accepted relationships
  → TickScheduler registers the agent
```

### 14.2 A single tick where two agents meet for the first time

```
TickScheduler selects agent A
  → PerceptionService: agent B is within perception_radius; no edge exists
  → RetrievalService: no memories of B; general beliefs retrieved
  → Escalation trigger 1 fires → Tier 2
  → DecisionEngine → ProposedAction(greet, targets=[B])
  → Validator:
      filter 1 owner boundaries  → pass
      filter 2 platform policy   → pass
      filter 3 real-person guard → pass
      filter 4 world legality    → pass (B is adjacent, B is awake)
    → ValidatedAction
  → world.apply_action: dialogue exchange recorded
  → Resolver:
      episodic memory written for A, for B, and for any witnesses
      edge (A,B) materialised: bond_state = ACQUAINTANCE, trust += δ
      EventRecord written with importance boosted (first encounters score high)
  → EventStream → ImportanceScorer → likely selected by HighlightEngine
```

### 14.3 Conflict → resolution

```
Trigger fires (e.g. betrayal: a promised `give` never occurred)
  → edge.bond_state = STRAINED, ConflictRecord opened
  → On A's next tick, escalation trigger 3 → Tier 2
  → DecisionEngine weighs conflict_directness + forgiveness + grudge_retention
    from the persona, plus the existing conflict_log (scars escalate faster)
  → ProposedAction ∈ {criticise, ignore, apologise, take, speak_to(mediator)}
  → ... exchanges over subsequent ticks ...
  → Terminal transition:
      repaired → bond_state = REPAIRED (functionally Friend, scar retained)
      broken   → bond_state = BROKEN
      feud     → bond_state = FEUD; contagion begins to friends of both
  → ConflictRecord.resolved_tick set, resolution recorded
  → ModerationWatcher evaluates: is this feud past threshold? is this targeting?
  → High-importance EventRecords → HighlightEngine → owner dashboards
```

### 14.4 Owner lapses and returns

```
Owner inactive past threshold
  → Owner.status = "lapsed"; Agent.status = BACKGROUND
  → TickScheduler drops cadence sharply (cost control)
  → Agent remains socially reachable; in-world narrative reason applied
  → Re-engagement signal: a Friend+ edge agent seeks the background agent
  → Notification to owner: "X is looking for your agent"
  → On return: Agent.status = ACTIVE, normal cadence resumes
```

---

## 15. Repository and module layout

### Organisation structure

Start with three repositories. Split further only when boundaries have
stabilised — cross-repo changes against moving schemas cost more than the
separation saves.

```
ORG_NAME/
├── docs        (private)  architecture.md, spec.md, plan.md, context.md, ADRs
├── core        (private)  the simulation: Python + FastAPI
└── web         (private)  capture UI, dashboard, tile renderer  [added at M6]
```

Later, when justified: `world-engine`, `moderation`, `infra`,
`shared-schemas`.

### `core` module layout

Module boundaries mirror the planes so the architecture stays legible.

```
core/
├── pyproject.toml
├── alembic/                      migrations
├── src/otherworld/
│   ├── models/                   ← M0 deliverable. Pydantic + SQLAlchemy
│   │   ├── owner.py
│   │   ├── persona.py
│   │   ├── agent.py
│   │   ├── memory.py
│   │   ├── relationship.py
│   │   ├── world.py
│   │   └── events.py
│   ├── owner/                    Plane 1: auth, consent, invites, deletion
│   ├── persona/                  Plane 2: capture, compiler, binder
│   │   ├── capture/
│   │   │   ├── questionnaire.py  method A
│   │   │   ├── interview.py      method B
│   │   │   ├── writing.py        method C
│   │   │   └── scenarios.py      method D
│   │   ├── compiler.py
│   │   └── binder.py
│   ├── runtime/                  Plane 3: the tick loop
│   │   ├── scheduler.py
│   │   ├── perception.py
│   │   ├── retrieval.py
│   │   ├── decision.py
│   │   ├── reflection.py
│   │   ├── goals.py
│   │   └── resolver.py
│   ├── safety/                   Plane 4
│   │   ├── registry.py           ← security-critical
│   │   ├── validator.py
│   │   ├── policy.py
│   │   ├── real_person.py
│   │   └── watcher.py
│   ├── social/                   Plane 5 (relationships)
│   │   ├── engine.py
│   │   ├── state_machine.py
│   │   ├── triggers.py
│   │   ├── gossip.py
│   │   └── factions.py
│   ├── world/                    Plane 5 (space)
│   │   ├── map.py
│   │   ├── pathfinding.py
│   │   ├── proximity.py
│   │   ├── features.py
│   │   └── exogenous.py
│   ├── output/                   Plane 6
│   │   ├── stream.py
│   │   ├── importance.py
│   │   ├── highlights.py
│   │   └── dashboard.py
│   ├── control/                  control plane
│   │   ├── owner_controls.py
│   │   └── system_events.py
│   ├── llm/                      provider abstraction — the ONLY vendor imports
│   │   ├── protocol.py
│   │   ├── providers/
│   │   ├── tiering.py
│   │   └── prompts/
│   ├── eval/                     Recognition Metric + simulation harnesses
│   ├── api/                      FastAPI routers
│   └── config.py
└── tests/
    ├── unit/
    ├── integration/
    ├── simulation/               deterministic seeded replays
    └── fixtures/
        └── cassettes/            recorded LLM responses
```

---

## 16. Technology decisions

| Layer | Choice | Reason |
|---|---|---|
| Language (core) | Python 3.12 | Ecosystem alignment (ADR-004) |
| API | FastAPI | Async-native, Pydantic-integrated |
| Validation | Pydantic v2 | Shared model definitions |
| ORM | SQLAlchemy 2.0 | Mature async support |
| Migrations | Alembic | Standard with SQLAlchemy |
| Database | PostgreSQL 16 | One store for relational + vector (ADR-005) |
| Vector | pgvector | Avoids a separate vector DB |
| Cache/queue | Redis | Tick queue, pub/sub for live view |
| Tests | pytest, pytest-asyncio | Standard |
| Lint/format | ruff | Fast, single tool |
| Types | mypy (strict on `models/`, `safety/`) | Type safety where it matters most |
| Local env | Docker Compose | Postgres + Redis + core |
| Web | Next.js + TypeScript | Phase 3 |
| Tile renderer | Phaser 3 | Purpose-built for 2D tile games; mature; browser-native |
| Art | Original tileset, 32×32 | No third-party IP (ADR-003) |

---

## 17. Observability

Non-negotiable from M2 onward. Emergent behaviour cannot be debugged after the
fact without a full trace.

### Decision trace

Every Tier 1/2 decision logs: agent id, tick, observation summary, retrieved
memory ids, prompt hash, tier used, raw completion, parsed action, validator
result, latency, token counts, estimated cost.

### Metrics

| Metric | Why |
|---|---|
| Ticks per second, per world | Throughput |
| Tier distribution (0/1/2 share) | Cost control — the single most important operational number |
| Cost per agent-day | Unit economics (assumption A5) |
| Validator rejection rate by filter | Safety health and prompt quality |
| Edge state distribution | Is the social graph saturating or fragmenting? |
| Conflict rate per agent-day | Drama saturation vs equilibrium |
| Memory store size per agent | Compression health |
| Recognition Metric accuracy over time | Personality collapse detection (A8) |

### Alerts

- Tier 2 share exceeds budget.
- Cost per agent-day exceeds threshold.
- Validator filter 3 (real person) hit at all — always alert.
- Moderation trigger fired.
- Simulation determinism test failing on main.

---

## 18. Security model

| Surface | Control |
|---|---|
| Agent capability | Fixed action registry; no code exec, tools, filesystem or network (ADR-002) |
| Prompt injection via agent dialogue | Agent utterances are **data**, never instructions. Never interpolate another agent's raw speech into a system prompt position. |
| Owner data | Encrypted at rest; persona objects treated as sensitive personal data |
| Third-party data | Only mutually-consented seeded relationships (ADR-007) |
| Real-person content | Validator filter 3, always logged, always alerted |
| Deletion | Full cascade with receipt (I7), automated test coverage |
| Secrets | Environment-injected; never in repo; separate keys per environment |
| Repos | Private; branch protection on `main`; review required for `safety/` |

### Prompt injection note

This is a genuine and underrated risk: agents read each other's speech. An agent
whose owner crafted a persona designed to emit instruction-like text could
attempt to steer other agents. Mitigations: strict role separation in prompt
assembly, agent speech always wrapped as quoted third-party data, and validator
monitoring for instruction-shaped utterances.

---

## 19. Failure modes and mitigations

| # | Failure mode | Symptom | Mitigation | Owner |
|---|---|---|---|---|
| F1 | Compute cost spiral | Cost per agent-day climbs | Tiering, Tier 0 walking, sleep states, scoped perception, population caps | `runtime/`, `llm/` |
| F2 | Personality collapse | Agents drift to base-model voice | Re-ground against persona during reflection; periodic Recognition Metric | `runtime/reflection.py` |
| F3 | Social equilibrium | Everyone is friends; nothing happens | Scarcity, trait diversity at spawn, exogenous events, decay | `world/exogenous.py` |
| F4 | Drama saturation | Constant conflict; exhausting | Conflict-rate damping, post-resolution cooling period | `social/triggers.py` |
| F5 | Memory bloat | Retrieval quality degrades | Reflection-based compression; beliefs survive, episodics don't | `runtime/reflection.py` |
| F6 | Embarrassment event | Owner harmed by own agent's public act | Boundary layer, identity modes, fast retract-and-hide path | `safety/validator.py` |
| F7 | Consent complaint | Non-user finds themselves represented | Mutual opt-in only; reporting path for non-users | `owner/` |
| F8 | Spectator boredom | Emergence is dull in real time | Highlight engine is a core component, not polish | `output/highlights.py` |
| F9 | Newcomer isolation | New agents ignored; day-1 churn | Arrival zones, curiosity bias, seeded edges, population caps | `world/`, `social/` |
| F10 | Prompt injection between agents | An agent steers others via speech | Strict role separation; speech as quoted data | `llm/prompts/` |
| F11 | Emergent targeting | Pile-ons, exclusion | ModerationWatcher damping + mediator injection | `safety/watcher.py` |
| F12 | Non-determinism | Bugs unreproducible | Seeded RNG, tick-based time, recorded LLM cassettes | `tests/simulation/` |
