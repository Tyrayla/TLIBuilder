from __future__ import annotations
from dataclasses import dataclass, field
from engine.models import BuildSource


@dataclass
class DerivedStat:
    """
    Describes how one final effective stat is computed from its component sources.

    flat_keys:  all add together into a single flat pool
    inc_keys:   all add together; applied as (1 + total / 100)
    add_pools:  each inner list is one additive pool; pools multiply each other:
                value *= product((1 + sum(pool) / 100) for pool in add_pools)
    base:       starting value before flat sources are added (e.g. character base life)
    """
    key:       str
    flat_keys: list[str]
    inc_keys:  list[str]       = field(default_factory=list)
    add_pools: list[list[str]] = field(default_factory=list)
    base:      float           = 0.0


ALL_DERIVED_STATS: list[DerivedStat] = [

    # ── Attributes ─────────────────────────────────────────────────────────────
    # all_stats_flat / all_stats_inc contribute to every attribute.
    DerivedStat(
        key="strength",
        flat_keys=["strength_flat", "all_stats_flat"],
        inc_keys=["strength_inc", "all_stats_inc"],
    ),
    DerivedStat(
        key="dexterity",
        flat_keys=["dexterity_flat", "all_stats_flat"],
        inc_keys=["dexterity_inc", "all_stats_inc"],
    ),
    DerivedStat(
        key="intelligence",
        flat_keys=["intelligence_flat", "all_stats_flat"],
        inc_keys=["intelligence_inc", "all_stats_inc"],
    ),

    # ── Life / Mana / Energy Shield ────────────────────────────────────────────
    DerivedStat(
        key="max_life",
        flat_keys=["max_life_flat"],
        inc_keys=["max_life_inc"],
        add_pools=[["max_life_additional"]],
    ),
    DerivedStat(
        key="max_mana",
        flat_keys=["max_mana_flat"],
        inc_keys=["max_mana_inc"],
    ),
    DerivedStat(
        key="max_energy_shield",
        flat_keys=["max_energy_shield_flat", "energy_shield_gear_flat"],
        inc_keys=["max_energy_shield_inc", "energy_shield_gear_inc"],
    ),

    # ── Armor / Evasion ────────────────────────────────────────────────────────
    # defense_inc is a shared multiplier that applies to both armor and evasion.
    # armor_additional and evasion_additional are each one independent pool.
    DerivedStat(
        key="armor",
        flat_keys=["armor_flat", "armor_gear_flat"],
        inc_keys=["armor_inc", "armor_gear_inc", "defense_inc"],
        add_pools=[["armor_additional"]],
    ),
    DerivedStat(
        key="evasion",
        flat_keys=["evasion_flat", "evasion_gear_flat"],
        inc_keys=["evasion_inc", "evasion_gear_inc", "defense_inc"],
        add_pools=[["evasion_additional"]],
    ),
]

# Fast lookup by output key
DERIVED_BY_KEY: dict[str, DerivedStat] = {d.key: d for d in ALL_DERIVED_STATS}


def derive_stats(source: BuildSource) -> dict[str, float]:
    """Compute final effective stat values and inject them back into source.

    Called once per aggregation pass inside the compute fixed-point loop.
    Results are available via source.total(key) for the pipeline and
    the computed_stat condition injection step.

    Returns {key: value} for all derived stats.
    """
    results: dict[str, float] = {}
    for d in ALL_DERIVED_STATS:
        flat_total = d.base + sum(source.total(k) for k in d.flat_keys)
        inc_total  = sum(source.total(k) for k in d.inc_keys)
        value      = flat_total * (1.0 + inc_total)
        for pool in d.add_pools:
            pool_total = sum(source.total(k) for k in pool)
            value *= (1.0 + pool_total)
        value = max(0.0, value)
        results[d.key] = value
        source.add(d.key, value)
    return results
