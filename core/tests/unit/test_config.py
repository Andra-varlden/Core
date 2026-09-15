"""T0.6 — config loads every key in About/spec.md §20."""

from otherworld.config import Settings

EXPECTED_SECTIONS_AND_KEYS = {
    "world": {
        "tile_size_px", "width", "height", "perception_radius", "interaction_radius",
        "tick_seconds", "in_world_minutes_per_tick", "population_cap",
    },
    "memory": {
        "episodic_cap", "compression_batch", "retrieval_k_tier1", "retrieval_k_tier2",
        "recency_decay_rate", "weight_recency", "weight_importance", "weight_relevance",
    },
    "reflection": {"interval_ticks", "importance_sum_trigger", "input_memory_count"},
    "relationships": {
        "friend_trust_threshold", "friend_shared_memory_importance", "close_bond_trust_threshold",
        "demote_friend_below", "demote_acquaintance_below", "decay_per_tick",
        "decay_starts_after_ticks", "seeded_decay_multiplier", "close_bond_target_share_max",
    },
    "conflict": {
        "neglect_ticks", "strained_to_broken_ticks", "feud_trust_threshold",
        "scar_severity_multiplier", "scar_multiplier_cap", "cooling_period_ticks",
        "global_damping_threshold_per_agent_day",
    },
    "gossip": {
        "propagation_decay", "min_importance_to_propagate", "max_hops",
        "direct_experience_weight", "pileon_agent_threshold",
    },
    "goals": {"max_concurrent", "stale_ticks"},
    "behaviour": {
        "approach_sociability_weight", "approach_curiosity_weight",
        "newcomer_bonus", "newcomer_window_ticks",
    },
    "tiering": {
        "target_tier0_share", "target_tier1_share", "target_tier2_share", "tier2_hard_ceiling",
    },
    "output": {"highlight_score_threshold", "arc_temporal_window_ticks"},
    "owner_controls": {
        "persona_edit_per_day", "whisper_per_day", "override_per_days", "recall_per_days",
    },
    "moderation": {
        "targeting_agent_threshold", "targeting_window_ticks",
        "runaway_feud_ticks", "filter2_hits_before_ratelimit",
    },
}


def test_every_spec_section_and_key_present():
    s = Settings()
    for section, keys in EXPECTED_SECTIONS_AND_KEYS.items():
        assert hasattr(s, section), f"missing config section: {section}"
        sub = getattr(s, section)
        for key in keys:
            assert hasattr(sub, key), f"missing config key: {section}.{key}"


def test_spec_values_match_doc_defaults():
    s = Settings()
    assert s.world.population_cap == 20
    assert s.memory.episodic_cap == 2000
    assert s.relationships.close_bond_target_share_max == 0.05
    assert s.tiering.tier2_hard_ceiling == 0.05
