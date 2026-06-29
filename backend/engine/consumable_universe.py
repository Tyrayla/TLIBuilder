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
    "fervor_effect_inc", "numbed_effect_inc", "numbed_effect_additional",
    "frail_effect_inc", "fire_infiltration_effect_inc", "cold_infiltration_effect_inc",
    "lightning_infiltration_effect_inc",
    "cast_speed_to_spell_burst_charge", "proj_speed_to_proj_dmg", "projectile_speed_inc",
    "movement_speed_inc", "movement_speed_additional",
    "movement_bonus_to_attack_speed", "movement_bonus_to_cast_speed", "movement_bonus_to_cdr",
})

_ALL_TAGS = [
    "attack", "spell", "minion", "projectile", "ranged", "channeled", "area", "melee", "trauma", "wilt",
    "ignite", "tangle", "sentry", "warcry", "reaping", "affliction", "multistrike", "spell_burst",
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
    # engine.compute reads Ailment Duration for the Numbed-ailment display box (per-stack lifetime).
    consumed |= {"ailment_duration_inc"}
    # engine.curse_resolver.apply_curses reads these to scale curses by Curse Effect + enforce the curse limit
    # (outside the offense/defense/derive passes). The per-type *_curse_taken pools it bakes are read inside the
    # synthetic offense pass (and aren't STAT_META keys), so they don't need listing here.
    consumed |= {"curse_effect_inc", "curse_effect_additional", "max_curses_flat", "curse_limit_cap_flat"}
    # engine.utility.apply_empower_buffs reads Empower Skill Effect (and Mass Effect reads max_charge_flat) to
    # scale the Euphoria buffs — outside the synthetic passes.
    consumed |= {"empower_effect_inc", "empower_effect_additional", "max_charge_flat"}
    # engine.utility.apply_elixir_buffs reads Elixir Skill Effect to scale elixir buffs, plus the timing pools for
    # the per-elixir display: Skill Effect Duration (inc + additional) and Elixir Duration scale duration, Cooldown
    # Recovery Speed scales cooldown, Charging Progress + Max Charge feed charges — all outside the synthetic passes.
    consumed |= {"elixir_effect_inc", "elixir_effect_additional",
                 "elixir_duration_additional", "elixir_charging_progress_flat",
                 "skill_effect_duration_inc", "skill_effect_duration_additional", "cdr_speed_inc"}
    # engine.recovery (post-loop sustain stage) reads the Restoration / Regain / Regen / Temporary-pool stats —
    # outside the synthetic offense/defense/derive passes, so whitelist them.
    consumed |= {"restoration_effect_inc", "restoration_effect_additional",
                 "restoration_duration_inc", "restoration_duration_additional",
                 "life_regain_inc", "energy_shield_regain_inc", "regain_interval_additional",
                 "life_regain_interval_additional", "energy_shield_regain_interval_additional",
                 "life_regen_flat", "life_regen_inc", "life_regen_speed_inc",
                 "mana_regen_flat", "mana_regen_inc", "mana_regen_pct",
                 "temporary_life_flat", "temporary_life_pct", "temporary_mana_flat", "temporary_mana_pct",
                 "max_temporary_life_pct", "max_temporary_mana_pct", "excess_restoration_to_es_pct",
                 "life_regain_to_restoration", "es_regain_to_restoration"}
    # engine.consumption (self-consume drains) reads the typed consume-rate stats outside the offense/defense passes.
    consumed |= {f"{p}_consumed_{b}_per_{c}"
                 for p in ("life", "mana", "energy_shield")
                 for b in ("pct_current", "pct_max", "flat")
                 for c in ("sec", "cast")}
    consumed |= {f"{p}_consumed_{b}_per_attack_use"
                 for p in ("life", "mana") for b in ("pct_current", "pct_max", "flat")}
    consumed |= {"consumed_recently_life", "consumed_recently_mana", "consumed_recently_energy_shield"}
    # AS-per-consumed (Tide) is read in the compute loop's feedback injection, outside the synthetic offense run.
    consumed |= {"attack_speed_inc_per_life_consumed", "attack_speed_inc_per_life_consumed_cap"}
    # engine.utility.apply_reservation reads these for mana/life sealing (Compensation, support-imparted seal,
    # seal-to-life flag, Ward ES from sealed pools) — outside the offense/defense/derive passes.
    consumed |= {"sealed_mana_compensation_inc", "sealed_mana_compensation_additional",
                 "focus_skill_sealed_mana_comp_inc", "spirit_magi_sealed_mana_comp_inc",
                 "imparted_seal_mana_pct", "seal_to_life",
                 "energy_shield_per_sealed_mana", "energy_shield_per_sealed_life"}
    # support_resolver folds these skill-level sources into a support's effective level (+4 Support Skill
    # Level from Off the Beaten Track, tag-matched levels like +Attack Skill Level for an Attack support).
    consumed |= {"support_skill_level"}
    # Tangle mode (offense.calculate_offense / compute._offense_for_slot) reads these outside the synthetic
    # passes: the Tangle Damage Enhancement multiplier, and the count stats that size attached/placeable tangles.
    # (tangle_dmg_inc / tangle_dmg_additional / tangle_crit_rating_flat are already covered — the synthetic skill
    # carries the "tangle" tag in _ALL_TAGS, so the tag-filtered pools read them.)
    consumed |= {"tangle_dmg_enhancement_additional", "max_tangle_quantity_flat", "extra_tangle_applied_flat",
                 "has_dormant_entanglement_flag",
                 # display-only tangle mechanic reads (duration/attach range) in calculate_offense's tangle mode
                 "tangle_duration_inc", "tangle_duration_additional", "tangle_attach_range_inc"}
    # Spell Burst mode (offense.calculate_offense / compute._offense_for_slot) reads these outside the synthetic
    # passes: Max Spell Burst (count), the charge-speed pools, and Surging's stacks-per-cast. The burst hit-damage
    # additional pool is already covered — the synthetic skill carries the "spell_burst" tag in _ALL_TAGS.
    consumed |= {"max_spell_burst_flat", "spell_burst_charge_speed_inc", "spell_burst_charge_speed_additional",
                 "spell_burst_chance_gain_stacks_flat",
                 # auto-trigger sources (offense finalizes auto), charge/burst conversions (aggregator), Squidnova
                 "spell_burst_auto_trigger_flag", "spell_burst_auto_charge_threshold",
                 "attack_speed_to_spell_burst_charge",
                 "charge_speed_to_spell_burst_hit_dmg", "charge_speed_to_spell_burst_hit_dmg_per",
                 "charge_speed_to_spell_burst_hit_dmg_cap",
                 "squidnova_effect_inc", "has_squidnova_flag"}

    # Channeled mode (offense.calculate_offense) reads the stack-cap pools to set the RESET cadence; they only
    # fire for a channeled skill (Icebound Beam), outside the synthetic passes. projectile_quantity_flat scales
    # a projectile-shotgun form's blade count (Icy Blade).
    consumed |= {"max_channeled_stacks_flat", "min_channeled_stacks_flat", "projectile_quantity_flat"}

    # Rosa High Court Chariot: No Guard (offense enemy-vulnerability) + Block Ratio Upper Limit (defense), both
    # engine-computed / read outside the synthetic passes.
    consumed |= {"no_guard_dmg_taken", "block_ratio_upper_limit_flat"}

    # Howling Gale canvas supports: Furious Sweep's Gale attack-frequency-additional (offense Gale-rate calc),
    # Headwind's knockback enemy-vuln (offense enemy-vulnerability), and the surfaced knockback_chance (non-DPS).
    consumed |= {"channeled_attack_frequency_additional", "knockback_dmg_taken", "knockback_chance"}

    # Icebound Beam canvas supports (offense reads these for the Icy Blade / beam-suppression calc): Chilling
    # Spike's suppression-disable + extra-blade equivalents, and Ring Blade's Frozen-proc burst rate.
    consumed |= {"continuous_suppression_disable", "icy_blade_extra_blade_equiv", "icy_blade_frozen_burst_rate"}

    # Frostbite ailment: max_frostbite_rating_flat (compute derives Frostbite Rating from it) + frostbite_effect_inc
    # + the baked frostbite_cold_taken enemy-vuln (offense cold branch) — read outside the synthetic passes.
    consumed |= {"max_frostbite_rating_flat", "frostbite_effect_inc", "frostbite_cold_taken"}

    # Multistrike (offense multistrike stage, attack skills): chance + per-stack increment (+ its additional) +
    # initial-count pre-stack + Cat Dive's max-count proc chance. Gated to multistrike builds, so read outside
    # the synthetic passes — whitelist them so a modeled multistrike stat never false-yellows.
    consumed |= {"multistrike_chance", "multistrike_increasing_dmg_inc", "multistrike_increasing_dmg_additional",
                 "initial_multistrike_count_flat", "multistrike_max_count_proc_chance"}

    # Selena Sing with the Tide: Tide enemy-vuln (offense enemy-vulnerability) + the Tide Effect scalars the trait
    # module emits/reads. Engine-computed / read outside the synthetic passes — whitelist so they never false-yellow.
    consumed |= {"tide_dmg_taken", "tide_effect_inc", "tide_effect_additional"}

    # Rosa Unsullied Blade: spell→attack bridge flag + Mercury Baptism fraction (offense), main-hand additional
    # (offense main-hand flat injection), Mercury Points + mana-override (trait module / future mana hookup).
    consumed |= {"spell_dmg_to_attack", "mercury_baptism_fraction", "main_hand_dmg_additional",
                 "max_mercury_points_flat", "max_mercury_points_inc", "mana_cost_override",
                 "spell_ripple_fraction"}

    # Chromatic Shot: Lightchaser's main-attribute ratio boost + the shots-on-target shotgun count, both read in
    # offense (presence-gated) outside the synthetic passes — whitelist so they never false-yellow.
    consumed |= {"main_stat_dmg_bonus_inc", "chromatic_shots_on_target_flat"}

    missing = _SANITY_FLOOR - consumed
    if missing:
        raise RuntimeError(
            f"consumable_universe regressed: floor stats not consumed by the synthetic run: {sorted(missing)}. "
            "The offense/defense/derive passes likely changed shape — fix before trusting badge classification."
        )
    return frozenset(consumed)
