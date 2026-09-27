"""Central configuration.

Every tunable numeric value in the simulation is defined here, and only here.
Values must match `About/spec.md` §20 exactly — that document is the source
of truth for what each number is and why. If you change a number in code,
change it in the doc in the same PR (ADR-009).
"""

from __future__ import annotations

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorldConfig(BaseModel):
    tile_size_px: int = 32
    width: int = 60
    height: int = 60
    perception_radius: int = 8
    interaction_radius: int = 2
    tick_seconds: int = 10
    in_world_minutes_per_tick: int = 10
    population_cap: int = 20


class MemoryConfig(BaseModel):
    episodic_cap: int = 2000
    compression_batch: int = 200
    retrieval_k_tier1: int = 5
    retrieval_k_tier2: int = 12
    recency_decay_rate: float = 0.005
    weight_recency: float = 0.25
    weight_importance: float = 0.35
    weight_relevance: float = 0.40


class ReflectionConfig(BaseModel):
    interval_ticks: int = 150
    # spec.md §5.1's own cost model (§15.2: "~58 reflections/agent/day, every
    # 150 ticks") assumes the interval is the ordinary cadence and this sum
    # trigger only an "alternative" for unusually eventful stretches. The
    # original 8.0 [TUNE] guess didn't survive contact with a real 5-agent,
    # always-witnessed world: the M4 real trial measured actual importance
    # accrual at ~0.89/tick (witnessed routine chatter alone gets there,
    # since +0.10 fires whenever 3+ of the other 4 agents see it), so 8.0
    # tripped within ~9 ticks — reflection fired 5-16x more often than the
    # interval implied (confirmed against real belief-memory counts: alpha
    # world ~10,000 ticks logged 500-1,075 beliefs/agent against an
    # interval-only prediction of ~66), silently multiplying LLM spend for
    # the whole run. Set above what ~150 ticks of ordinary busy chatter
    # accrues (150 x 0.89 =~ 133) so the interval is normally what fires,
    # while a genuinely eventful burst (several relationship transitions or
    # conflicts close together) can still trigger it early, as intended.
    importance_sum_trigger: float = 200.0
    input_memory_count: int = 30


class RelationshipsConfig(BaseModel):
    friend_trust_threshold: float = 0.35
    friend_shared_memory_importance: float = 0.6
    close_bond_trust_threshold: float = 0.70
    demote_friend_below: float = 0.25
    demote_acquaintance_below: float = 0.05
    decay_per_tick: float = 0.0008
    decay_starts_after_ticks: int = 300
    seeded_decay_multiplier: float = 0.5
    close_bond_target_share_max: float = 0.05


class ConflictConfig(BaseModel):
    neglect_ticks: int = 600
    strained_to_broken_ticks: int = 400
    feud_trust_threshold: float = -0.4
    scar_severity_multiplier: float = 0.4
    scar_multiplier_cap: float = 2.0
    cooling_period_ticks: int = 200
    global_damping_threshold_per_agent_day: float = 0.8
    damping_check_interval_ticks: int = 200
    damping_factor_floor: float = 0.1


class GossipConfig(BaseModel):
    propagation_decay: float = 0.7
    min_importance_to_propagate: float = 0.5
    max_hops: int = 3
    direct_experience_weight: float = 3.0
    pileon_agent_threshold: int = 4


class GoalsConfig(BaseModel):
    max_concurrent: int = 3
    stale_ticks: int = 200


class FactionsConfig(BaseModel):
    scan_interval_ticks: int = 500
    min_clique_size: int = 3
    min_clique_degree_for_pair: int = 2
    exclusion_acquaintance_threshold: int = 3
    exclusion_persistence_ticks: int = 1000


class MaintenanceConfig(BaseModel):
    """The periodic relationship-maintenance scan (`social/maintenance.py`):
    trust decay, decay-driven demotion, Strained timeout/escalation, and the
    scan-tied conflict triggers (NEGLECT, CONTAGION) — none of which are
    tied to any single action, so nothing in `runtime/resolver.py` ever
    checks them on its own."""

    scan_interval_ticks: int = 50


class BehaviourConfig(BaseModel):
    approach_sociability_weight: float = 0.6
    approach_curiosity_weight: float = 0.4
    newcomer_bonus: float = 0.15
    newcomer_window_ticks: int = 2000


class TieringConfig(BaseModel):
    target_tier0_share: float = 0.85
    target_tier1_share: float = 0.12
    target_tier2_share: float = 0.03
    tier2_hard_ceiling: float = 0.05


class OutputConfig(BaseModel):
    highlight_score_threshold: float = 0.7
    arc_temporal_window_ticks: int = 2000


class OwnerControlsConfig(BaseModel):
    persona_edit_per_day: int = 1
    whisper_per_day: int = 3
    override_per_days: int = 7
    recall_per_days: int = 30


class ModerationConfig(BaseModel):
    targeting_agent_threshold: int = 4
    targeting_window_ticks: int = 500
    runaway_feud_ticks: int = 2000
    filter2_hits_before_ratelimit: int = 5


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_nested_delimiter="__", extra="ignore")

    database_url: str = "postgresql+asyncpg://otherworld:otherworld@localhost:5432/otherworld"
    database_url_sync: str = "postgresql+psycopg://otherworld:otherworld@localhost:5432/otherworld"
    # A separate database, never touched by alembic or the running app.
    # tests/conftest.py creates and drops the full schema on it per test —
    # pointing that at `database_url` would periodically wipe the dev DB.
    test_database_url: str = "postgresql+asyncpg://otherworld:otherworld@localhost:5432/otherworld_test"
    redis_url: str = "redis://localhost:6379/0"

    # LLM provider. See otherworld.llm.factory and About/spec.md §15.3.
    groq_api_key: str | None = None

    world: WorldConfig = WorldConfig()
    memory: MemoryConfig = MemoryConfig()
    reflection: ReflectionConfig = ReflectionConfig()
    relationships: RelationshipsConfig = RelationshipsConfig()
    conflict: ConflictConfig = ConflictConfig()
    gossip: GossipConfig = GossipConfig()
    goals: GoalsConfig = GoalsConfig()
    factions: FactionsConfig = FactionsConfig()
    maintenance: MaintenanceConfig = MaintenanceConfig()
    behaviour: BehaviourConfig = BehaviourConfig()
    tiering: TieringConfig = TieringConfig()
    output: OutputConfig = OutputConfig()
    owner_controls: OwnerControlsConfig = OwnerControlsConfig()
    moderation: ModerationConfig = ModerationConfig()


settings = Settings()
