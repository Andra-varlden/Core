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
    importance_sum_trigger: float = 8.0
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


class GossipConfig(BaseModel):
    propagation_decay: float = 0.7
    min_importance_to_propagate: float = 0.5
    max_hops: int = 3
    direct_experience_weight: float = 3.0
    pileon_agent_threshold: int = 4


class GoalsConfig(BaseModel):
    max_concurrent: int = 3
    stale_ticks: int = 200


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
    redis_url: str = "redis://localhost:6379/0"

    world: WorldConfig = WorldConfig()
    memory: MemoryConfig = MemoryConfig()
    reflection: ReflectionConfig = ReflectionConfig()
    relationships: RelationshipsConfig = RelationshipsConfig()
    conflict: ConflictConfig = ConflictConfig()
    gossip: GossipConfig = GossipConfig()
    goals: GoalsConfig = GoalsConfig()
    behaviour: BehaviourConfig = BehaviourConfig()
    tiering: TieringConfig = TieringConfig()
    output: OutputConfig = OutputConfig()
    owner_controls: OwnerControlsConfig = OwnerControlsConfig()
    moderation: ModerationConfig = ModerationConfig()


settings = Settings()
