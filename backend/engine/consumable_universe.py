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
    # Element-tagged crit damage — guards that the damage-type tags stay in _ALL_TAGS.
    "fire_crit_dmg_inc", "lightning_crit_dmg_inc", "physical_crit_dmg_inc",
    # Condition-cap stat — guards that derive_condition_maximums runs in the universe.
    "max_focus_blessing_stacks_flat",
})

# Stats the AGGREGATOR reads directly (propagation / effect-scaling), outside the offense/defense/derive
# passes the synthetic run exercises. They ARE modeled — a node granting one should badge "Inactive" (grey,
# not active for your build) rather than "Unconsumed" (yellow). MUST stay in sync with the `source.total(...)`
# reads in engine/aggregator.py — test_consumable_universe.py scans the aggregator and fails if one is missing.
_AGGREGATOR_PROPAGATION_INPUTS = frozenset({
    "fervor_effect_inc", "numbed_effect_inc",
    "frail_effect_inc", "fire_infiltration_effect_inc", "cold_infiltration_effect_inc",
    "lightning_infiltration_effect_inc",
    "cast_speed_to_spell_burst_charge", "proj_speed_to_proj_dmg", "projectile_speed_inc",
    "movement_speed_inc", "movement_speed_additional",
    "movement_bonus_to_attack_speed", "movement_bonus_to_cast_speed", "movement_bonus_to_cdr",
})

_ALL_TAGS = [
    "attack", "spell", "minion", "projectile", "ranged", "channeled", "area", "melee", "trauma", "wilt",
    "ignite", "tangle", "sentry", "warcry", "reaping", "affliction", "multistrike",
    # Damage-type tags — element-tagged stats (e.g. fire_crit_dmg_inc) are read only when the skill's
    # mod_tags include that element (offense._CRIT_DMG_STATS tag-filter). The universe is the union over
    # ALL skills, so it carries every element tag; omitting these falsely badges type crit damage "yellow".
    "fire", "cold", "lightning", "erosion", "physical",
]
_FLAT_SUFFIXES = (
    "_attack_dmg_flat_min", "_attack_dmg_flat_max", "_spell_dmg_flat_min", "_spell_dmg_flat_max",
    "_dmg_gear_flat_min", "_dmg_gear_flat_max",
)
_DMG_TYPES = ("physical", "fire", "cold", "lightning", "erosion")

# Maximal support behavior so support-gated source reads fire (e.g. extra_jumps_flat under Augmentation /
# shotgun). Values are arbitrary-but-truthy; we only care which stats get read, not the numbers.
_MAX_SUPPORT_BEHAVIOR = {
    "augmentation_per_jump": 0.1, "lucky_damage": True, "same_target_shotgun": True,
    "chains_per_jump": 1, "falloff_coefficient": 0.5,
}


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
        # Include a Steep Strike form so the form-scoped steep_strike_additional_dmg read is exercised
        # (otherwise that modeled stat would false-yellow in the badges).
        hit_forms_by_level={1: [
            SkillHitForm(name="H", effectiveness_pct=100.0, form_type="additive", proc_stat_key=None),
            SkillHitForm(name="Steep", effectiveness_pct=100.0, form_type="additive",
                         proc_stat_key="steep_strike_chance")]},
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
    from engine.compute import derive_condition_maximums, derive_condition_minimums

    conv_keys = {k.value for k, m in STAT_META.items() if m.modifier_type == "conversion"}
    all_keys = [s.value for s in STAT_META]

    consumed: set[str] = set()
    # UNION over is_spell × support-behavior on/off — some support paths (lucky, shotgun) replace reads
    # the plain path makes, so neither alone is a superset.
    for is_spell in (False, True):
        for support in (None, _MAX_SUPPORT_BEHAVIOR):
            s = _make_source(conv_keys, all_keys)
            calculate_offense(s, _make_skill(is_spell), 1, is_main_skill=True, support_behavior=support)
            consumed |= s.consumed_stats
    # defense + derived display stats + condition max/min derivation (the latter reads each numeric
    # condition's max_from_stat/min_from_stat — e.g. max_*_blessing_stacks_flat, max_fervor_rating —
    # which automax/cap logic then consumes; without it those cap stats false-yellow).
    for fn in (calculate_defense, derive_stats, derive_condition_maximums, derive_condition_minimums):
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
    # engine.utility reads these to scale aura buffs by total Aura Effect (outside offense/defense/derive).
    consumed |= {"aura_effect_inc", "aura_effect_additional"}
    # engine.curse_resolver.apply_curses reads these to scale curses by Curse Effect + enforce the curse limit
    # (outside the offense/defense/derive passes). The per-type *_curse_taken pools it bakes are read inside the
    # synthetic offense pass (and aren't STAT_META keys), so they don't need listing here.
    consumed |= {"curse_effect_inc", "curse_effect_additional", "max_curses_flat", "curse_limit_cap_flat"}
    # engine.utility.apply_empower_buffs reads Empower Skill Effect (and Mass Effect reads max_charge_flat) to
    # scale the Euphoria buffs — outside the synthetic passes.
    consumed |= {"empower_effect_inc", "empower_effect_additional", "max_charge_flat"}
    # engine.utility.apply_reservation reads these for mana/life sealing (Compensation, support-imparted seal,
    # seal-to-life flag, Ward ES from sealed pools) — outside the offense/defense/derive passes.
    consumed |= {"sealed_mana_compensation_inc", "sealed_mana_compensation_additional",
                 "focus_skill_sealed_mana_comp_inc", "spirit_magi_sealed_mana_comp_inc",
                 "imparted_seal_mana_pct", "seal_to_life",
                 "energy_shield_per_sealed_mana", "energy_shield_per_sealed_life"}
    # support_resolver folds these skill-level sources into a support's effective level (+4 Support Skill
    # Level from Off the Beaten Track, tag-matched levels like +Attack Skill Level for an Attack support).
    consumed |= {"support_skill_level"}

    missing = _SANITY_FLOOR - consumed
    if missing:
        raise RuntimeError(
            f"consumable_universe regressed: floor stats not consumed by the synthetic run: {sorted(missing)}. "
            "The offense/defense/derive passes likely changed shape — fix before trusting badge classification."
        )
    return frozenset(consumed)
