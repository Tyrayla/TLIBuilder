"""The maximal set of stat keys the engine can EVER read, across all skill types/tags.

Used by the modifier badges to split two states the per-build `consumed_stats` cannot tell apart:
  • a stat the engine models but YOUR selected skill doesn't read  → "Inactive" (grey)
  • a stat the engine never reads anywhere (resolves but unmodeled) → "Unconsumed" (yellow)

Computed by running offense (attack AND spell, every tag), defense, and derive once over a synthetic
source that carries every stat — then collecting the stats those passes actually read (`consumed_stats`).
Conversion stats are zeroed (a 100% conversion would chain all damage to one type and mask the stats the
other types read). The speed-additional pools are read via `source.source_log`, not `source.total`, so they
never record into `consumed_stats` — they're added back explicitly. Cached: computed once per process.

SANITY FLOOR: a short list of stats that MUST appear. If the synthetic run regresses (e.g. a skill-resolver
change throws) and drops below the floor, we raise — so the universe can never silently shrink and wrongly
badge live stats as unmodeled. The frontend also fails open (treats an empty universe as all-Inactive).
"""
from __future__ import annotations

from functools import lru_cache

# Stats that are unmistakably read by the offense/defense math. If any is missing the synthetic run broke.
_SANITY_FLOOR = frozenset({
    "dmg_inc", "attack_dmg_inc", "spell_dmg_inc", "crit_rating_inc", "crit_dmg_inc",
    "attack_speed_inc", "cast_speed_inc", "max_life_inc", "max_energy_shield_inc",
    "fire_dmg_inc", "cold_dmg_inc", "lightning_dmg_inc", "attack_speed_additional",
})

# Stats the AGGREGATOR reads directly (propagation / effect-scaling), outside the offense/defense/derive
# passes the synthetic run exercises. They ARE modeled — a node granting one should badge "Inactive" (grey,
# not active for your build) rather than "Unconsumed" (yellow). MUST stay in sync with the `source.total(...)`
# reads in engine/aggregator.py — test_consumable_universe.py scans the aggregator and fails if one is missing.
_AGGREGATOR_PROPAGATION_INPUTS = frozenset({
    "fervor_effect_inc", "numbed_effect_inc",
    "cast_speed_to_spell_burst_charge", "proj_speed_to_proj_dmg", "projectile_speed_inc",
    "movement_speed_inc", "movement_bonus_to_attack_speed", "movement_bonus_to_cast_speed",
    "movement_bonus_to_cdr",
})

_ALL_TAGS = [
    "attack", "spell", "minion", "projectile", "channeled", "area", "melee", "trauma", "wilt",
    "ignite", "tangle", "sentry", "warcry", "reaping", "affliction", "multistrike",
]
_FLAT_SUFFIXES = (
    "_attack_dmg_flat_min", "_attack_dmg_flat_max", "_spell_dmg_flat_min", "_spell_dmg_flat_max",
    "_dmg_gear_flat_min", "_dmg_gear_flat_max",
)
_DMG_TYPES = ("physical", "fire", "cold", "lightning", "erosion")


def _make_source(conv_keys, all_keys):
    from engine.models import BuildSource
    s = BuildSource()
    for k in all_keys:
        s.add(k, 0.0 if k in conv_keys else 1.0)
    for t in _DMG_TYPES:
        for suf in _FLAT_SUFFIXES:
            s.add(t + suf, 10.0)
    s.add("weapon_attack_speed", 1.0)
    s._recording = True
    return s


def _make_skill(is_spell):
    from engine.skill_resolver import ResolvedSkill, SkillHitForm
    return ResolvedSkill(
        skill_id="__universe__", name="Universe", tags=list(_ALL_TAGS), max_level=1,
        hit_forms_by_level={1: [SkillHitForm(name="H", effectiveness_pct=100.0,
                                             form_type="additive", proc_stat_key=None)]},
        supported=True, base_steep_strike_chance=0.0, is_spell=is_spell,
        base_dmg_by_level=({1: {t: (10.0, 10.0) for t in _DMG_TYPES}} if is_spell else {}),
        base_cast_time=1.0, added_dmg_effectiveness=1.36,
        main_stat=["strength", "dexterity", "intelligence"],
    )


@lru_cache(maxsize=1)
def consumable_universe() -> frozenset[str]:
    from models.stat_meta import STAT_META
    from engine.offense import calculate_offense, _APS_ADDITIONAL_STATS, _CAST_ADDITIONAL_STATS
    from engine.defense import calculate_defense
    from engine.derive import derive_stats

    conv_keys = {k.value for k, m in STAT_META.items() if m.modifier_type == "conversion"}
    all_keys = [s.value for s in STAT_META]

    consumed: set[str] = set()
    for is_spell in (False, True):
        s = _make_source(conv_keys, all_keys)
        calculate_offense(s, _make_skill(is_spell), 1, is_main_skill=True)
        consumed |= s.consumed_stats
    for fn in (calculate_defense, derive_stats):
        s = _make_source(conv_keys, all_keys)
        fn(s)
        consumed |= s.consumed_stats
    # Speed-additional pools read via source_log, not source.total → never self-record. Add them back.
    for k, _ in _APS_ADDITIONAL_STATS:
        consumed.add(k)
    for k, _ in _CAST_ADDITIONAL_STATS:
        consumed.add(k)
    # Aggregator-level propagation/effect reads (see note above).
    consumed |= _AGGREGATOR_PROPAGATION_INPUTS

    missing = _SANITY_FLOOR - consumed
    if missing:
        raise RuntimeError(
            f"consumable_universe regressed: floor stats not consumed by the synthetic run: {sorted(missing)}. "
            "The offense/defense/derive passes likely changed shape — fix before trusting badge classification."
        )
    return frozenset(consumed)
