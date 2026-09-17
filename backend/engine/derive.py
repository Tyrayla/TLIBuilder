from __future__ import annotations
from dataclasses import dataclass, field
from engine.models import BuildSource, SourceEntry


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
    inc_entries = [e for e in source.source_log if e.stat == inc_key and e.source_type == "gear"]
    targeted_keys = []
    if any(e.gear_slot == "chest" for e in flat_entries):
        targeted_keys.append("chest_defense_inc")
    if any(e.is_shield for e in flat_entries):
        targeted_keys.append("shield_defense_inc")
        if flat_key == "energy_shield_gear_flat":
            targeted_keys.append("shield_energy_shield_inc")
    targeted_entries = {key: [e for e in source.source_log if e.stat == key] for key in targeted_keys}
    targeted_totals = {key: source.total(key) for key in targeted_keys}

    # One row per equipped item, rather than one for each of its raw base/implicit/affix lines.
    # The nested increase rows retain the exact originating talent/gear source for the click-to-expand UI.
    items: dict[tuple[str | None, str | None, str], list[SourceEntry]] = {}
    for flat in flat_entries:
        identity = (flat.gear_slot, flat.source_name, flat.label)
        items.setdefault(identity, []).append(flat)

    rows = []
    for (_slot, _name, _label), item_flats in items.items():
        flat = item_flats[0]
        raw_amount = sum(e.amount for e in item_flats)
        applicable = [e for e in inc_entries if e.gear_slot == flat.gear_slot]
        if flat.gear_slot == "chest":
            applicable.extend(targeted_entries.get("chest_defense_inc", []))
        if flat.is_shield:
            applicable.extend(targeted_entries.get("shield_defense_inc", []))
            if flat_key == "energy_shield_gear_flat":
                applicable.extend(targeted_entries.get("shield_energy_shield_inc", []))
        local_inc = sum(e.amount for e in applicable)
        local_increases = [{
            "amount": e.amount,
            "label": e.label,
            "source_name": e.source_name,
            "text": e.text,
            "source_type": e.source_type,
        } for e in applicable]
        # Source-less targeted modifiers are uncommon (normal gameplay supplies source_log entries),
        # but preserve their numerical contribution for programmatic/custom builds as well.
        for key in targeted_keys:
            applies = (key == "chest_defense_inc" and flat.gear_slot == "chest") or (key != "chest_defense_inc" and flat.is_shield)
            logged = sum(e.amount for e in targeted_entries[key])
            if applies and logged == 0 and targeted_totals[key]:
                local_inc += targeted_totals[key]
                local_increases.append({
                    "amount": targeted_totals[key],
                    "label": "Unattributed",
                    "source_name": None,
                    "text": key,
                    "source_type": "custom",
                })
        rows.append({
            "amount": raw_amount * (1.0 + local_inc),
            "raw_amount": raw_amount,
            "multiplier": 1.0 + local_inc,
            "label": flat.label,
            "source_name": flat.source_name,
            "text": flat.text,
            "local_increases": local_increases,
        })
    return rows


def local_gear_defense_total_from_rows(source: BuildSource, flat_key: str, rows: list[dict]) -> float:
    """Sum one defense type's flat total from already-computed `local_gear_defense_sources` rows —
    lets a caller that already has `rows` (e.g. for the stat-breakdown display) avoid recomputing
    them a second time. `source.total(flat_key)` is always read (marks the key consumed, and is the
    whole answer when `rows` is empty). When `rows` is non-empty, its gear-item rows are already
    locally scaled; any REMAINING amount under `flat_key` belongs to a non-gear source landing on
    the same stat (rare — e.g. a talent's bare "+N maximum energy shield" phrasing routes here too,
    same as gear's "+N gear armor"/"+N gear evasion") — not tied to an item, so it isn't part of
    `rows` and applies unscaled, same as before this per-item split existed. Without this, such a
    contribution would be silently excluded from the total whenever the build also has ANY
    gear-sourced local defense (rows non-empty short-circuits the old empty-rows fallback)."""
    grand_total = source.total(flat_key)
    if not rows:
        return grand_total
    non_gear_total = grand_total - sum(row["raw_amount"] for row in rows)
    return sum(row["amount"] for row in rows) + non_gear_total


def local_gear_defense_total(source: BuildSource, flat_key: str) -> float:
    """Compute one defense type from the item's raw flat and its additive local increased pool."""
    return local_gear_defense_total_from_rows(source, flat_key, local_gear_defense_sources(source, flat_key))


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
    # *_gear_flat is folded per item by local_gear_defense_total(), not in the global increased pool.
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
