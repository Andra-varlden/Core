"""Shared trait-vector math used by every capture method and by the M1
acceptance tests (About/plan.md T1.3, T1.4).
"""

from __future__ import annotations

import math

from otherworld.models.persona import TraitVector

TRAIT_NAMES: tuple[str, ...] = tuple(TraitVector.model_fields.keys())


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def cosine_distance(a: TraitVector, b: TraitVector) -> float:
    """1 - cosine similarity, computed on vectors centered at the neutral
    0.5 default.

    Every trait lives in [0, 1] with 0.5 meaning "no signal", so two raw
    trait vectors both sit in the same positive octant and point in nearly
    the same direction from the origin regardless of how different the two
    people actually are — plain cosine similarity is close to 1 even for
    opposite personalities. Centering at 0.5 turns each dimension into
    "which way does this trait lean, and how far", which is what "two
    different people" (T1.3) actually means here.
    """
    va = [getattr(a, name) - 0.5 for name in TRAIT_NAMES]
    vb = [getattr(b, name) - 0.5 for name in TRAIT_NAMES]
    dot = sum(x * y for x, y in zip(va, vb, strict=True))
    norm_a = math.sqrt(sum(x * x for x in va))
    norm_b = math.sqrt(sum(y * y for y in vb))
    if norm_a == 0.0 or norm_b == 0.0:
        return 1.0
    similarity = dot / (norm_a * norm_b)
    return 1.0 - similarity


def traits_agree_within(a: TraitVector, b: TraitVector, tolerance: float = 0.2) -> int:
    """Count of traits where two vectors agree within `tolerance`.

    Used by T1.4: method A vs method B on the same person must agree within
    0.2 on at least 8 of 12 traits.
    """
    return sum(
        1
        for name in TRAIT_NAMES
        if abs(getattr(a, name) - getattr(b, name)) <= tolerance
    )
