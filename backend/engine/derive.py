from __future__ import annotations
from dataclasses import dataclass, field
from engine.models import BuildSource


_LOCAL_GEAR_DEFENSE = {
    "energy_shield_gear_flat": "energy_shield_gear_inc",
    "armor_gear_flat": "armor_gear_inc",
    "evasion_gear_flat": "evasion_gear_inc",
}


def local_gear_defense_sources(source: BuildSource, flat_key: str) -> list[dict]:
    """Finalized, per-item local-defense rows for computation and stat-breakdown display."""
    inc_key = _LOCAL_GEAR_DEFENSE[flat_key]
    flat_entries = [e for e in source.source_log if e.stat == flat_key and e.source_type == "gear"]
    if not flat_entries:
        return []

    # Mark the normal local increased stat as consumed; values are selected per item below.
    source.total(inc_key)
    chest_inc = source.total("chest_defense_inc")
    shield_defense_inc = source.total("shield_defense_inc")
    shield_es_inc = source.total("shield_energy_shield_inc") if flat_key == "energy_shield_gear_flat" else 0.0
    inc_entries = [e for e in source.source_log if e.stat == inc_key and e.source_type == "gear"]
    rows = []
    for flat in flat_entries:
        local_inc = sum(e.amount for e in inc_entries if e.gear_slot == flat.gear_slot)
        if flat.gear_slot == "chest":
            local_inc += chest_inc
        if flat.is_shield:
            local_inc += shield_defense_inc + shield_es_inc
        rows.append({
            "amount": flat.amount * (1.0 + local_inc),
            "multiplier": 1.0 + local_inc,
            "label": flat.label,
            "source_name": flat.source_name,
            "text": flat.text,
        })
    return rows


def local_gear_defense_total(source: BuildSource, flat_key: str) -> float:
    """Compute one defense type from the item's raw flat and its additive local increased pool."""
    rows = local_gear_defense_sources(source, flat_key)
    return sum(row["amount"] for row in rows) if rows else source.total(flat_key)


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
        add_pools=[["strength_additional"]],
    ),
    DerivedStat(
        key="dexterity",
        flat_keys=["dexterity_flat", "all_stats_flat"],
        inc_keys=["dexterity_inc", "all_stats_inc"],
        add_pools=[["dexterity_additional"]],
    ),
    DerivedStat(
        key="intelligence",
        flat_keys=["intelligence_flat", "all_stats_flat"],
        inc_keys=["intelligence_inc", "all_stats_inc"],
        add_pools=[["intelligence_additional"]],
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
        add_pools=[["max_mana_additional"]],
    ),
    DerivedStat(
        key="max_energy_shield",
        # *_gear_flat is folded per item by local_gear_defense_total(), not in the global increased pool.
        # so the gear % is NOT a global inc here — only the truly-global "% increased Max ES" pools.
        flat_keys=["max_energy_shield_flat"],
        inc_keys=["max_energy_shield_inc"],
        add_pools=[["max_energy_shield_additional"]],
    ),

    # ── Armor / Evasion ────────────────────────────────────────────────────────
    # defense_inc is a shared multiplier that applies to both armor and evasion.
    # armor_additional and evasion_additional are each one independent pool.
    # *_gear_flat is pre-scaled by the item's local "% gear X" (statsPayload) — not a global inc.
    DerivedStat(
        key="armor",
        flat_keys=["armor_flat"],
        inc_keys=["armor_inc", "defense_inc"],
        add_pools=[["armor_additional"]],
    ),
    DerivedStat(
        key="evasion",
        flat_keys=["evasion_flat"],
        inc_keys=["evasion_inc", "defense_inc"],
        add_pools=[["evasion_additional"]],
    ),
    # Movement speed is NOT a DerivedStat: it's displayed at a 0% baseline (reductions go negative), which the
    # linear (base+flat)×(1+inc)×Π(1+add) shape + its max(0,·) clamp can't represent. compute.py injects it
    # directly as the NET bonus = (1+Σinc)×(1+Σadditional) − 1.
]


def _additional_pool_factor(source: BuildSource, keys: list[str]) -> float:
    """Combine an ADDITIONAL pool as Π(1 + amount) over each source — so "+25% and +15% additional Max Life"
    MULTIPLY (×1.25×1.15 = ×1.4375) instead of summing to +40%. Each contribution (positive or negative) is
    its own multiplicative factor; a negative can't drop the factor below 0. Falls back to (1 + Σ) when
    contributions were added without source text (e.g. some tests use add() with no source_log)."""
    entries = [e for e in source.source_log if e.stat in keys]
    if not entries:
        return 1.0 + sum(source.total(k) for k in keys)
    factor = 1.0
    for e in entries:
        factor *= max(0.0, 1.0 + e.amount)
    return factor


def derive_stats(source: BuildSource, overrides: dict[str, float] | None = None) -> dict[str, float]:
    """Compute final effective stat values and inject them back into source.

    Called once per aggregation pass inside the compute fixed-point loop.
    Results are available via source.total(key) for the pipeline and
    the computed_stat condition injection step.

    `overrides` forces a derived stat to a FIXED final value (core-talent "set to / fixed at N"
    set-value mechanic) — the normal flat×inc×additional computation is skipped for that key.

    Returns {key: value} for all derived stats.
    """
    overrides = overrides or {}
    results: dict[str, float] = {}
    for d in ALL_DERIVED_STATS:
        if d.key in overrides:
            value = max(0.0, float(overrides[d.key]))
        else:
            flat_total = d.base + sum(source.total(k) for k in d.flat_keys)
            if d.key == "max_energy_shield":
                flat_total += local_gear_defense_total(source, "energy_shield_gear_flat")
            elif d.key == "armor":
                flat_total += local_gear_defense_total(source, "armor_gear_flat")
            elif d.key == "evasion":
                flat_total += local_gear_defense_total(source, "evasion_gear_flat")
            # Tortoise Shell: a % of FINAL Max Life is added as flat Energy Shield BEFORE ES inc/additional scale
            # it. max_life is derived earlier in this same pass (it precedes max_energy_shield), so read the just-
            # computed value from `results`. Done inline (not source.add) so it can't accumulate across passes.
            if d.key == "max_energy_shield":
                flat_total += results.get("max_life", 0.0) * source.total("max_life_as_es_pct")
            inc_total  = sum(source.total(k) for k in d.inc_keys)
            value      = flat_total * (1.0 + inc_total)
            for pool in d.add_pools:
                value *= _additional_pool_factor(source, pool)
            value = max(0.0, value)
        results[d.key] = value
        source.add(d.key, value)
    return results
