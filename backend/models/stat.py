from enum import Enum


class Stat(Enum):

    # ── Derived (computed from flat + inc + additional pools) ────────────────
    STRENGTH         = "strength"
    DEXTERITY        = "dexterity"
    INTELLIGENCE     = "intelligence"
    MAX_LIFE         = "max_life"
    MAX_MANA         = "max_mana"
    MAX_ENERGY_SHIELD = "max_energy_shield"
    ARMOR            = "armor"
    EVASION          = "evasion"

    # ── Attributes ───────────────────────────────────────────────────────────
    STRENGTH_FLAT = "strength_flat"
    STRENGTH_INC = "strength_inc"
    DEXTERITY_FLAT = "dexterity_flat"
    DEXTERITY_INC = "dexterity_inc"
    INTELLIGENCE_FLAT = "intelligence_flat"
    INTELLIGENCE_INC = "intelligence_inc"
    ALL_STATS_FLAT = "all_stats_flat"
    ALL_STATS_INC = "all_stats_inc"

    # ── Generic (cross-type damage) ──────────────────────────────────────────
    ARMOR_PEN = "armor_pen"
    DOUBLE_DMG_CHANCE = "double_dmg_chance"
    DMG_INC = "dmg_inc"
    DMG_ADDITIONAL = "dmg_additional"
    DMG_MAX_ADDITIONAL = "dmg_max_additional"
    POST_MOBILITY_DMG_ADDITIONAL = "post_mobility_dmg_additional"
    DMG_AVOID_CHANCE = "dmg_avoid_chance"
    BEAM_LENGTH_ADDITIONAL = "beam_length_additional"
    ALL_SKILL_LEVEL = "all_skill_level"
    ACTIVE_SKILL_LEVEL = "active_skill_level"
    SUPPORT_SKILL_LEVEL = "support_skill_level"
    ALL_RESISTANCE_REDUCTION = "all_resistance_reduction"   # negative value; reduces enemy elemental res
    ENEMY_NEARBY_DMG_TAKEN_ADDITIONAL = "enemy_nearby_dmg_taken_additional"  # additional dmg multiplier vs nearby enemies

    # ── Attack ───────────────────────────────────────────────────────────────
    ATTACK_DMG_INC = "attack_dmg_inc"
    ATTACK_DMG_ADDITIONAL = "attack_dmg_additional"
    ATTACK_DOUBLE_DMG_CHANCE = "attack_double_dmg_chance"
    ATTACK_SKILL_LEVEL = "attack_skill_level"
    TWO_HANDED_BASE_DMG_ADDITIONAL = "two_handed_base_dmg_additional"
    SHIELD_DMG_INC = "shield_dmg_inc"
    RANGED_DMG_INC = "ranged_dmg_inc"

    # ── Spell ────────────────────────────────────────────────────────────────
    SPELL_DMG_INC = "spell_dmg_inc"
    SPELL_DMG_ADDITIONAL = "spell_dmg_additional"
    SPELL_DOUBLE_DMG_CHANCE = "spell_double_dmg_chance"
    SPELL_SKILL_LEVEL = "spell_skill_level"
    SPELL_BURST_CHARGE_SPEED_INC = "spell_burst_charge_speed_inc"
    SPELL_BURST_CHANCE_GAIN_STACKS_FLAT = "spell_burst_chance_gain_stacks_flat"
    SPELL_BURST_HIT_DMG_ADDITIONAL = "spell_burst_hit_dmg_additional"
    LOW_MANA_SPELL_DMG_INC = "low_mana_spell_dmg_inc"

    # ── Melee ────────────────────────────────────────────────────────────────
    MELEE_DMG_INC = "melee_dmg_inc"
    MELEE_DMG_ADDITIONAL = "melee_dmg_additional"
    MELEE_SKILL_LEVEL = "melee_skill_level"

    # ── Area ─────────────────────────────────────────────────────────────────
    AREA_DMG_INC = "area_dmg_inc"
    AREA_DMG_ADDITIONAL = "area_dmg_additional"

    # ── Projectile ───────────────────────────────────────────────────────────
    PROJECTILE_DMG_INC = "projectile_dmg_inc"
    PROJECTILE_DMG_ADDITIONAL = "projectile_dmg_additional"
    PROJECTILE_SPEED_INC = "projectile_speed_inc"
    PROJECTILE_SKILL_LEVEL = "projectile_skill_level"
    PROJECTILE_CRIT_DMG_INC = "projectile_crit_dmg_inc"
    PROJECTILE_CRIT_RATING_INC = "projectile_crit_rating_inc"
    PROJECTILE_QUANTITY_FLAT = "projectile_quantity_flat"
    HORIZONTAL_PROJECTILE_PENETRATION_FLAT = "horizontal_projectile_penetration_flat"
    PARABOLIC_PROJECTILE_SPLITS_FLAT = "parabolic_projectile_splits_flat"

    # ── Minion ───────────────────────────────────────────────────────────────
    MINION_DMG_INC = "minion_dmg_inc"
    MINION_DMG_ADDITIONAL = "minion_dmg_additional"
    MINION_ELEMENTAL_DMG_INC = "minion_elemental_dmg_inc"
    MINION_ELEMENTAL_PEN = "minion_elemental_pen"
    MINION_MOVEMENT_SPEED_INC = "minion_movement_speed_inc"
    MINION_DMG_MAX = "minion_dmg_max"                 # increases max damage boundary
    MINION_DOUBLE_DMG_CHANCE = "minion_double_dmg_chance"
    MINION_SKILL_LEVEL = "minion_skill_level"
    MINION_FIRE_DMG_INC = "minion_fire_dmg_inc"
    MINION_FIRE_PEN_INC = "minion_fire_pen_inc"
    MINION_COLD_DMG_INC = "minion_cold_dmg_inc"
    MINION_LIGHTNING_DMG_INC = "minion_lightning_dmg_inc"
    MINION_EROSION_DMG_INC = "minion_erosion_dmg_inc"
    MINION_PHYSICAL_DMG_INC = "minion_physical_dmg_inc"
    MINION_MAX_LIFE_INC = "minion_max_life_inc"
    MINION_ATTACK_SPEED_INC = "minion_attack_speed_inc"
    MINION_CAST_SPEED_INC = "minion_cast_speed_inc"
    MINION_LIFE_REGEN_SPEED_INC = "minion_life_regen_speed_inc"
    MINION_MULTISTRIKE_CHANCE = "minion_multistrike_chance"
    MINION_IGNITE_CHANCE = "minion_ignite_chance"
    MINION_AFFLICTION_EFFECT_INC = "minion_affliction_effect_inc"
    MINION_AFFLICTION_PER_SECOND_FLAT = "minion_affliction_per_second_flat"
    MINION_ARMOR_PEN = "minion_armor_pen"
    MINION_DURATION_INC = "minion_duration_inc"
    MINION_PHYSIQUE_INC = "minion_physique_inc"
    MINION_LIFE_REGAIN_INC = "minion_life_regain_inc"
    MINION_SKILL_AREA_INC = "minion_skill_area_inc"
    MINION_DAMAGING_AILMENT_CHANCE = "minion_damaging_ailment_chance"
    MINION_TRAUMA_CHANCE = "minion_trauma_chance"
    MINION_PHYSICAL_DMG_FLAT_MIN = "minion_physical_dmg_flat_min"
    MINION_PHYSICAL_DMG_FLAT_MAX = "minion_physical_dmg_flat_max"
    MINION_FIRE_DMG_FLAT_MIN = "minion_fire_dmg_flat_min"
    MINION_FIRE_DMG_FLAT_MAX = "minion_fire_dmg_flat_max"
    MINION_COLD_DMG_FLAT_MIN = "minion_cold_dmg_flat_min"
    MINION_COLD_DMG_FLAT_MAX = "minion_cold_dmg_flat_max"
    MINION_LIGHTNING_DMG_FLAT_MIN = "minion_lightning_dmg_flat_min"
    MINION_LIGHTNING_DMG_FLAT_MAX = "minion_lightning_dmg_flat_max"
    MINION_EROSION_DMG_FLAT_MIN = "minion_erosion_dmg_flat_min"
    MINION_EROSION_DMG_FLAT_MAX = "minion_erosion_dmg_flat_max"

    # Synthetic Troops
    SYNTH_DOUBLE_DMG_CHANCE = "synth_double_dmg_chance"
    SYNTH_SKILL_LEVEL = "synth_skill_level"
    MAX_SYNTH_TROOPS_FLAT = "max_synth_troops_flat"
    COMMAND_PER_SECOND_FLAT = "command_per_second_flat"
    MAX_COMMAND_FLAT = "max_command_flat"
    SYNTH_TROOP_DMG_TAKEN_ADDITIONAL = "synth_troop_dmg_taken_additional"

    # ── Sentry ───────────────────────────────────────────────────────────────
    SENTRY_DMG_INC = "sentry_dmg_inc"
    SENTRY_DMG_ADDITIONAL = "sentry_dmg_additional"
    SENTRY_SKILL_CAST_FREQUENCY_INC = "sentry_skill_cast_frequency_inc"
    SENTRY_SKILL_CAST_FREQUENCY_ADDITIONAL = "sentry_skill_cast_frequency_additional"
    SENTRY_CRIT_DMG_INC = "sentry_crit_dmg_inc"
    SENTRY_CRIT_RATING_INC = "sentry_crit_rating_inc"
    MAX_SENTRY_QUANTITY_FLAT = "max_sentry_quantity_flat"
    SENTRY_DURATION_INC = "sentry_duration_inc"
    SENTRY_SKILL_AREA_INC = "sentry_skill_area_inc"
    SENTRY_START_TIME_ADDITIONAL = "sentry_start_time_additional"
    SENTRY_PROJECTILE_SPEED_INC = "sentry_projectile_speed_inc"

    # ── Spirit Magi ──────────────────────────────────────────────────────────
    SPIRIT_MAGI_INITIAL_GROWTH_FLAT = "spirit_magi_initial_growth_flat"
    SPIRIT_MAGI_DMG_INC = "spirit_magi_dmg_inc"
    SPIRIT_MAGI_DMG_ADDITIONAL = "spirit_magi_dmg_additional"
    SPIRIT_MAGI_ULTIMATE_DMG_INC = "spirit_magi_ultimate_dmg_inc"
    SPIRIT_MAGI_ORIGIN_EFFECT_INC = "spirit_magi_origin_effect_inc"
    SPIRIT_MAGI_SKILL_LEVEL = "spirit_magi_skill_level"
    SPIRIT_MAGI_CRIT_RATING_FLAT = "spirit_magi_crit_rating_flat"
    SPIRIT_MAGI_ENHANCED_SKILL_CHANCE = "spirit_magi_enhanced_skill_chance"
    SPIRIT_MAGI_CDR_SPEED_INC = "spirit_magi_cdr_speed_inc"
    SPIRIT_MAGI_DMG_TAKEN_ADDITIONAL = "spirit_magi_dmg_taken_additional"
    MAX_SPIRIT_MAGI_FLAT = "max_spirit_magi_flat"

    # ── Physical ─────────────────────────────────────────────────────────────
    PHYSICAL_DMG_INC = "physical_dmg_inc"
    PHYSICAL_DMG_ADDITIONAL = "physical_dmg_additional"
    PHYSICAL_AS_LIGHTNING = "physical_as_lightning"
    PHYSICAL_AS_COLD = "physical_as_cold"
    PHYSICAL_AS_FIRE = "physical_as_fire"
    PHYSICAL_AS_EROSION = "physical_as_erosion"
    PHYSICAL_AS_ELEMENTAL = "physical_as_elemental"    # adds 40% as all 3 elements
    PHYSICAL_SKILL_LEVEL = "physical_skill_level"
    PHYSICAL_ATTACK_DMG_FLAT_MIN = "physical_attack_dmg_flat_min"
    PHYSICAL_ATTACK_DMG_FLAT_MAX = "physical_attack_dmg_flat_max"
    PHYSICAL_SPELL_DMG_FLAT_MIN = "physical_spell_dmg_flat_min"
    PHYSICAL_SPELL_DMG_FLAT_MAX = "physical_spell_dmg_flat_max"
    PHYSICAL_DMG_REFLECTION = "physical_dmg_reflection"

    # ── Lightning ────────────────────────────────────────────────────────────
    LIGHTNING_DMG_INC = "lightning_dmg_inc"
    LIGHTNING_DMG_ADDITIONAL = "lightning_dmg_additional"
    LIGHTNING_PEN = "lightning_pen"
    LIGHTNING_AS_EROSION = "lightning_as_erosion"
    LIGHTNING_ATTACK_DMG_FLAT_MIN = "lightning_attack_dmg_flat_min"
    LIGHTNING_ATTACK_DMG_FLAT_MAX = "lightning_attack_dmg_flat_max"
    LIGHTNING_SPELL_DMG_FLAT_MIN = "lightning_spell_dmg_flat_min"
    LIGHTNING_SPELL_DMG_FLAT_MAX = "lightning_spell_dmg_flat_max"
    LIGHTNING_SKILL_LEVEL = "lightning_skill_level"
    LIGHTNING_DMG_REFLECTION = "lightning_dmg_reflection"

    # ── Cold ─────────────────────────────────────────────────────────────────
    COLD_DMG_INC = "cold_dmg_inc"
    COLD_DMG_ADDITIONAL = "cold_dmg_additional"
    COLD_PEN = "cold_pen"
    COLD_AS_EROSION = "cold_as_erosion"
    COLD_DMG_REFLECTION = "cold_dmg_reflection"
    COLD_ATTACK_DMG_FLAT_MIN = "cold_attack_dmg_flat_min"
    COLD_ATTACK_DMG_FLAT_MAX = "cold_attack_dmg_flat_max"
    COLD_SPELL_DMG_FLAT_MIN = "cold_spell_dmg_flat_min"
    COLD_SPELL_DMG_FLAT_MAX = "cold_spell_dmg_flat_max"
    COLD_SKILL_LEVEL = "cold_skill_level"

    # ── Fire ─────────────────────────────────────────────────────────────────
    FIRE_DMG_INC = "fire_dmg_inc"
    FIRE_DMG_ADDITIONAL = "fire_dmg_additional"
    FIRE_PEN = "fire_pen"
    FIRE_ATTACK_DMG_FLAT_MIN = "fire_attack_dmg_flat_min"
    FIRE_ATTACK_DMG_FLAT_MAX = "fire_attack_dmg_flat_max"
    FIRE_SPELL_DMG_FLAT_MIN = "fire_spell_dmg_flat_min"
    FIRE_SPELL_DMG_FLAT_MAX = "fire_spell_dmg_flat_max"
    FIRE_SKILL_LEVEL = "fire_skill_level"
    FIRE_AS_EROSION = "fire_as_erosion"
    FIRE_DOT_DMG_INC = "fire_dot_dmg_inc"
    FIRE_DMG_REFLECTION = "fire_dmg_reflection"

    # ── Erosion ──────────────────────────────────────────────────────────────
    EROSION_DMG_INC = "erosion_dmg_inc"
    EROSION_DMG_ADDITIONAL = "erosion_dmg_additional"
    EROSION_PEN = "erosion_pen"
    EROSION_DMG_REFLECTION = "erosion_dmg_reflection"
    EROSION_ATTACK_DMG_FLAT_MIN = "erosion_attack_dmg_flat_min"
    EROSION_ATTACK_DMG_FLAT_MAX = "erosion_attack_dmg_flat_max"
    EROSION_SPELL_DMG_FLAT_MIN = "erosion_spell_dmg_flat_min"
    EROSION_SPELL_DMG_FLAT_MAX = "erosion_spell_dmg_flat_max"
    EROSION_SKILL_LEVEL = "erosion_skill_level"

    # ── Elemental ────────────────────────────────────────────────────────────
    ELEMENTAL_DMG_INC = "elemental_dmg_inc"
    ELEMENTAL_DMG_ADDITIONAL = "elemental_dmg_additional"
    ELEMENTAL_PEN = "elemental_pen"

    # ── Ailments — Generic ───────────────────────────────────────────────────
    AILMENT_DMG_INC = "ailment_dmg_inc"
    AILMENT_DMG_FLAT_MIN = "ailment_dmg_flat_min"
    AILMENT_DMG_FLAT_MAX = "ailment_dmg_flat_max"
    AILMENT_DURATION_INC = "ailment_duration_inc"
    DAMAGING_AILMENT_CHANCE = "damaging_ailment_chance"
    ELEMENTAL_AILMENT_AVOID_CHANCE = "elemental_ailment_avoid_chance"
    DOT_DMG_INC = "dot_dmg_inc"

    # ── Ignite ───────────────────────────────────────────────────────────────
    IGNITE_DMG_INC = "ignite_dmg_inc"
    IGNITE_DMG_ADDITIONAL = "ignite_dmg_additional"
    IGNITE_DMG_FLAT_MIN = "ignite_dmg_flat_min"
    IGNITE_DMG_FLAT_MAX = "ignite_dmg_flat_max"
    IGNITE_CHANCE = "ignite_chance"
    IGNITE_DURATION_INC = "ignite_duration_inc"
    IGNITE_EFFECT_RECEIVED_INC = "ignite_effect_received_inc"
    MAX_IGNITE_FLAT = "max_ignite_flat"

    # ── Wilt ─────────────────────────────────────────────────────────────────
    WILT_DMG_INC = "wilt_dmg_inc"
    WILT_DMG_ADDITIONAL = "wilt_dmg_additional"
    WILT_DMG_FLAT_MIN = "wilt_dmg_flat_min"
    WILT_DMG_FLAT_MAX = "wilt_dmg_flat_max"
    WILT_CHANCE = "wilt_chance"
    WILT_DURATION_INC = "wilt_duration_inc"

    # ── Tangle ───────────────────────────────────────────────────────────────
    TANGLE_DMG_INC = "tangle_dmg_inc"
    TANGLE_DURATION_INC = "tangle_duration_inc"
    MAX_TANGLE_QUANTITY_FLAT = "max_tangle_quantity_flat"

    # ── Trauma ───────────────────────────────────────────────────────────────
    TRAUMA_DMG_INC = "trauma_dmg_inc"
    TRAUMA_DMG_ADDITIONAL = "trauma_dmg_additional"
    TRAUMA_CHANCE = "trauma_chance"
    TRAUMA_DMG_ADDITIONAL_ON_CRIT = "trauma_dmg_additional_on_crit"
    TRAUMA_REAPING_DURATION_INC = "trauma_reaping_duration_inc"
    TRAUMA_BASE_DMG_FLAT_MIN = "trauma_base_dmg_flat_min"
    TRAUMA_BASE_DMG_FLAT_MAX = "trauma_base_dmg_flat_max"
    WILT_BASE_DMG_FLAT_MIN = "wilt_base_dmg_flat_min"
    WILT_BASE_DMG_FLAT_MAX = "wilt_base_dmg_flat_max"
    IGNITE_BASE_DMG_FLAT_MIN = "ignite_base_dmg_flat_min"
    IGNITE_BASE_DMG_FLAT_MAX = "ignite_base_dmg_flat_max"

    # ── Frostbite ────────────────────────────────────────────────────────────
    FROSTBITE_EFFECT_INC = "frostbite_effect_inc"
    MAX_FROSTBITE_RATING_FLAT = "max_frostbite_rating_flat"

    # ── Affliction ───────────────────────────────────────────────────────────
    AFFLICTION_EFFECT_INC = "affliction_effect_inc"
    AFFLICTION_PER_SECOND_FLAT = "affliction_per_second_flat"

    # ── Deterioration ────────────────────────────────────────────────────────
    DETERIORATION_CHANCE = "deterioration_chance"
    DETERIORATION_DMG_INC = "deterioration_dmg_inc"
    DETERIORATION_DMG_ADDITIONAL = "deterioration_dmg_additional"
    DETERIORATION_DURATION_ADDITIONAL = "deterioration_duration_additional"

    # ── Status Effects ───────────────────────────────────────────────────────
    NUMBED_EFFECT_INC = "numbed_effect_inc"
    NUMBED_THRESHOLD_INC = "numbed_threshold_inc"
    SLOW_CHANCE = "slow_chance"
    SLOW_EFFECT_RECEIVED_INC = "slow_effect_received_inc"
    BLIND_CHANCE = "blind_chance"
    PARALYSIS_EFFECT_2H_INC = "paralysis_effect_2h_inc"

    # ── Channeled / Triggered / Combo Mechanics ──────────────────────────────
    CHANNELED_DMG_INC = "channeled_dmg_inc"
    CHANNELED_ATTACK_SPEED_INC = "channeled_attack_speed_inc"
    CHANNELED_CAST_SPEED_INC = "channeled_cast_speed_inc"
    TRIGGERED_DMG_INC = "triggered_dmg_inc"
    COMBO_FINISHER_ADDITIONAL = "combo_finisher_additional"
    COMBO_FINISHER_CRIT_DMG_INC = "combo_finisher_crit_dmg_inc"
    COMBO_STARTER_ATTACK_SPEED_ADDITIONAL = "combo_starter_attack_speed_additional"
    COMBO_STARTER_CAST_SPEED_ADDITIONAL = "combo_starter_cast_speed_additional"
    COMBO_STARTERS_COMBO_POINTS_FLAT = "combo_starters_combo_points_flat"
    MULTISTRIKE_INCREASING_DMG_INC = "multistrike_increasing_dmg_inc"
    BARRAGE_DMG_PER_WAVE_INC = "barrage_dmg_per_wave_inc"
    MULTISTRIKE_CHANCE = "multistrike_chance"
    MAX_CHANNELED_STACKS_FLAT = "max_channeled_stacks_flat"
    MIN_CHANNELED_STACKS_FLAT = "min_channeled_stacks_flat"
    JUMP_DMG_FOR_EVERY_ADDITIONAL = "jump_dmg_for_every_additional"  # revisit stacking behavior

    # ── Steep Strike ─────────────────────────────────────────────────────────
    STEEP_STRIKE_CHANCE = "steep_strike_chance"
    STEEP_STRIKE_ADDITIONAL_DMG = "steep_strike_additional_dmg"
    SWEEP_SLASH_ADDITIONAL_DMG = "sweep_slash_additional_dmg"

    # ── Cast Speed ───────────────────────────────────────────────────────────
    CAST_SPEED_INC = "cast_speed_inc"
    CAST_SPEED_ADDITIONAL = "cast_speed_additional"

    # ── Attack Speed ─────────────────────────────────────────────────────────
    ATTACK_SPEED_GEAR = "attack_speed_gear"
    ATTACK_SPEED_MH = "attack_speed_mh"
    ATTACK_SPEED_INC = "attack_speed_inc"
    ATTACK_SPEED_ADDITIONAL = "attack_speed_additional"

    # ── Other Speeds ─────────────────────────────────────────────────────────
    MOVEMENT_SPEED_INC = "movement_speed_inc"
    FOCUS_SPEED_INC = "focus_speed_inc"

    # ── Critical Strike — Rating ─────────────────────────────────────────────
    ATTACK_CRIT_RATING_GEAR = "attack_crit_rating_gear"
    ATTACK_CRIT_RATING_MH = "attack_crit_rating_mh"
    CRIT_RATING_INC = "crit_rating_inc"
    ATTACK_CRIT_RATING_INC = "attack_crit_rating_inc"
    SPELL_CRIT_RATING_INC = "spell_crit_rating_inc"
    MINION_CRIT_RATING_INC = "minion_crit_rating_inc"
    ATTACK_CRIT_RATING_FLAT = "attack_crit_rating_flat"
    SPELL_CRIT_RATING_FLAT = "spell_crit_rating_flat"
    MINION_CRIT_RATING_FLAT = "minion_crit_rating_flat"

    # ── Critical Strike — Damage ─────────────────────────────────────────────
    CRIT_DMG_INC = "crit_dmg_inc"
    ATTACK_CRIT_DMG_INC = "attack_crit_dmg_inc"
    SPELL_CRIT_DMG_INC = "spell_crit_dmg_inc"
    MINION_CRIT_DMG_INC = "minion_crit_dmg_inc"
    PHYSICAL_CRIT_DMG_INC = "physical_crit_dmg_inc"
    LIGHTNING_CRIT_DMG_INC = "lightning_crit_dmg_inc"
    COLD_CRIT_DMG_INC = "cold_crit_dmg_inc"
    FIRE_CRIT_DMG_INC = "fire_crit_dmg_inc"
    EROSION_CRIT_DMG_INC = "erosion_crit_dmg_inc"

    # ── Double Damage / Knockback ─────────────────────────────────────────────
    KNOCKBACK_CHANCE = "knockback_chance"
    KNOCKBACK_DISTANCE_INC = "knockback_distance_inc"

    # ── Life ─────────────────────────────────────────────────────────────────
    MAX_LIFE_FLAT = "max_life_flat"
    MAX_LIFE_INC = "max_life_inc"
    MAX_LIFE_ADDITIONAL = "max_life_additional"
    LIFE_REGEN_FLAT = "life_regen_flat"
    LIFE_REGEN_INC = "life_regen_inc"                # % of max life per second
    LIFE_REGEN_SPEED_INC = "life_regen_speed_inc"    # multiplier to regen rate
    LIFE_REGAIN_INC = "life_regain_inc"
    LIFE_REGAIN_INTERVAL_ADDITIONAL = "life_regain_interval_additional"
    REGAIN_INTERVAL_ADDITIONAL = "regain_interval_additional"
    LIFE_ON_SKILL_USE_FLAT = "life_on_skill_use_flat"
    LIFE_ON_DEFEAT_PCT = "life_on_defeat_pct"
    INJURY_BUFFER_INC = "injury_buffer_inc"

    # ── Mana ─────────────────────────────────────────────────────────────────
    MAX_MANA_FLAT = "max_mana_flat"
    MAX_MANA_INC = "max_mana_inc"
    MANA_REGEN_FLAT = "mana_regen_flat"
    MANA_REGEN_INC = "mana_regen_inc"
    MANA_REGEN_PCT = "mana_regen_pct"                # % of max mana per second
    MANA_BEFORE_LIFE_INC = "mana_before_life_inc"
    SKILL_COST_FLAT = "skill_cost_flat"              # flat addition to skill cost (negative = reduction)
    ATTACK_SKILL_COST_FLAT = "attack_skill_cost_flat"
    SPELL_SKILL_COST_FLAT = "spell_skill_cost_flat"
    SKILL_COST_INC = "skill_cost_inc"
    SKILL_COST_REDUCTION = "skill_cost_reduction"    # legacy / talent-tree source
    SEALED_MANA_COMPENSATION_INC = "sealed_mana_compensation_inc"

    # ── Energy Shield ─────────────────────────────────────────────────────────
    MAX_ENERGY_SHIELD_FLAT = "max_energy_shield_flat"
    MAX_ENERGY_SHIELD_INC = "max_energy_shield_inc"
    ENERGY_SHIELD_REGAIN_INC = "energy_shield_regain_inc"
    ENERGY_SHIELD_CHARGE_SPEED_INC = "energy_shield_charge_speed_inc"
    ENERGY_SHIELD_REGAIN_INTERVAL_ADDITIONAL = "energy_shield_regain_interval_additional"
    ENERGY_SHIELD_CHARGE_INTERVAL_ADDITIONAL = "energy_shield_charge_interval_additional"

    # ── Barrier ───────────────────────────────────────────────────────────────
    BARRIER_ABSORPTION_RATE_INC = "barrier_absorption_rate_inc"
    BARRIER_SHIELD_INC = "barrier_shield_inc"

    # ── Defense ───────────────────────────────────────────────────────────────
    ARMOR_FLAT = "armor_flat"
    ARMOR_INC = "armor_inc"
    ARMOR_ADDITIONAL = "armor_additional"
    EVASION_FLAT = "evasion_flat"
    EVASION_INC = "evasion_inc"
    EVASION_ADDITIONAL = "evasion_additional"
    EVASION_ON_SPELL_DMG_INC = "evasion_on_spell_dmg_inc"
    DEFENSE_INC = "defense_inc"
    SHIELD_DEFENSE_INC = "shield_defense_inc"
    SHIELD_DEFENSE_ADDITIONAL = "shield_defense_additional"
    ARMOR_EFFECTIVE_RATE_NON_PHYSICAL_INC = "armor_effective_rate_non_physical_inc"
    ELEMENTAL_RESISTANCE = "elemental_resistance"
    FIRE_RESISTANCE = "fire_resistance"
    COLD_RESISTANCE = "cold_resistance"
    LIGHTNING_RESISTANCE = "lightning_resistance"
    EROSION_RESISTANCE = "erosion_resistance"
    FIRE_RESISTANCE_MAX_INC = "fire_resistance_max_inc"
    COLD_RESISTANCE_MAX_INC = "cold_resistance_max_inc"
    LIGHTNING_RESISTANCE_MAX_INC = "lightning_resistance_max_inc"
    EROSION_RESISTANCE_MAX_INC = "erosion_resistance_max_inc"
    ATTACK_BLOCK_CHANCE_INC = "attack_block_chance_inc"
    SPELL_BLOCK_CHANCE_INC = "spell_block_chance_inc"
    BLOCK_RATIO_INC = "block_ratio_inc"
    INTIMIDATING_EFFECT_INC = "intimidating_effect_inc"
    SHIELD_ENERGY_SHIELD_INC = "shield_energy_shield_inc"
    CHEST_DEFENSE_INC = "chest_defense_inc"

    # ── Damage Taken ─────────────────────────────────────────────────────────
    DMG_TAKEN_ADDITIONAL = "dmg_taken_additional"
    PHYSICAL_DMG_TAKEN_ADDITIONAL = "physical_dmg_taken_additional"
    ELEMENTAL_DMG_TAKEN_ADDITIONAL = "elemental_dmg_taken_additional"
    TRAUMA_DMG_TAKEN_INC = "trauma_dmg_taken_inc"
    DOT_DMG_TAKEN_ADDITIONAL = "dot_dmg_taken_additional"

    # ── Damage Taken Conversion ───────────────────────────────────────────────
    COLD_TAKEN_AS_FIRE_INC = "cold_taken_as_fire_inc"
    LIGHTNING_TAKEN_AS_FIRE_INC = "lightning_taken_as_fire_inc"
    PHYSICAL_TAKEN_AS_LIGHTNING_INC = "physical_taken_as_lightning_inc"
    PHYSICAL_TAKEN_AS_COLD_INC = "physical_taken_as_cold_inc"
    PHYSICAL_TAKEN_AS_FIRE_INC = "physical_taken_as_fire_inc"
    EROSION_TAKEN_AS_LIGHTNING_INC = "erosion_taken_as_lightning_inc"
    EROSION_TAKEN_AS_COLD_INC = "erosion_taken_as_cold_inc"
    EROSION_TAKEN_AS_FIRE_INC = "erosion_taken_as_fire_inc"

    # ── Cooldown Recovery ────────────────────────────────────────────────────
    CDR_SPEED_INC = "cdr_speed_inc"
    WARCRY_CDR_SPEED_INC = "warcry_cdr_speed_inc"

    # ── Skill Mechanics ───────────────────────────────────────────────────────
    SKILL_AREA_INC = "skill_area_inc"
    SKILL_EFFECT_DURATION_INC = "skill_effect_duration_inc"
    RESTORATION_EFFECT_INC = "restoration_effect_inc"

    # ── Reaping ───────────────────────────────────────────────────────────────
    REAPING_DURATION_INC = "reaping_duration_inc"
    REAPING_RECOVERY_SPEED_INC = "reaping_recovery_speed_inc"

    # ── Buff / Aura Effects ───────────────────────────────────────────────────
    MAX_CURSE_FLAT = "max_curse_flat"
    CURSE_EFFECT_AGAINST_INC = "curse_effect_against_inc"
    TAUNT_ON_HIT_CHANCE = "taunt_on_hit_chance"
    ATTACK_TAUNT_ON_HIT_CHANCE = "attack_taunt_on_hit_chance"
    FERVOR_EFFECT_INC = "fervor_effect_inc"
    BLUR_EFFECT_INC = "blur_effect_inc"
    WARCRY_EFFECT_INC = "warcry_effect_inc"
    ELIXIR_EFFECT_INC = "elixir_effect_inc"
    AURA_EFFECT_INC = "aura_effect_inc"
    CURSE_EFFECT_INC = "curse_effect_inc"
    CURSE_SKILL_AREA_INC = "curse_skill_area_inc"
    MARK_EFFECT_INC = "mark_effect_inc"
    MARK_ON_CRIT_CHANCE = "mark_on_crit_chance"
    CC_EFFECT_INC = "cc_effect_inc"
    ILL_OMEN_EFFICIENCY_INC = "ill_omen_efficiency_inc"
    DEMOLISHER_CHARGE_SPEED_INC = "demolisher_charge_speed_inc"
    AGILITY_BLESSING_DURATION_INC = "agility_blessing_duration_inc"
    FOCUS_BLESSING_DURATION_INC = "focus_blessing_duration_inc"
    TENACITY_BLESSING_DURATION_INC = "tenacity_blessing_duration_inc"
    BLESSING_DURATION_INC = "blessing_duration_inc"
    FOCUS_DMG_ENHANCEMENT_ADDITIONAL = "focus_dmg_enhancement_additional"
    AILMENT_DMG_ENHANCEMENT_ADDITIONAL = "ailment_dmg_enhancement_additional"
    WARCRY_MIN_TARGETS_FLAT = "warcry_min_targets_flat"
    FOCUS_SKILL_LEVEL = "focus_skill_level"

    # ── Gear-Specific Stats ───────────────────────────────────────────────────
    PHYSICAL_DMG_GEAR_INC = "physical_dmg_gear_inc"
    ENERGY_SHIELD_GEAR_FLAT = "energy_shield_gear_flat"
    ENERGY_SHIELD_GEAR_INC = "energy_shield_gear_inc"
    WEAPON_ATTACK_SPEED = "weapon_attack_speed"
    ARMOR_GEAR_FLAT = "armor_gear_flat"
    ARMOR_GEAR_INC = "armor_gear_inc"
    EVASION_GEAR_FLAT = "evasion_gear_flat"
    EVASION_GEAR_INC = "evasion_gear_inc"
    PHYSICAL_DMG_GEAR_FLAT_MIN = "physical_dmg_gear_flat_min"
    PHYSICAL_DMG_GEAR_FLAT_MAX = "physical_dmg_gear_flat_max"
    FIRE_DMG_GEAR_FLAT_MIN = "fire_dmg_gear_flat_min"
    FIRE_DMG_GEAR_FLAT_MAX = "fire_dmg_gear_flat_max"
    COLD_DMG_GEAR_FLAT_MIN = "cold_dmg_gear_flat_min"
    COLD_DMG_GEAR_FLAT_MAX = "cold_dmg_gear_flat_max"
    LIGHTNING_DMG_GEAR_FLAT_MIN = "lightning_dmg_gear_flat_min"
    LIGHTNING_DMG_GEAR_FLAT_MAX = "lightning_dmg_gear_flat_max"
    EROSION_DMG_GEAR_FLAT_MIN = "erosion_dmg_gear_flat_min"
    EROSION_DMG_GEAR_FLAT_MAX = "erosion_dmg_gear_flat_max"
    ELEMENTAL_DMG_GEAR_FLAT_MIN = "elemental_dmg_gear_flat_min"
    ELEMENTAL_DMG_GEAR_FLAT_MAX = "elemental_dmg_gear_flat_max"

    # ── Flat Quantity / Mechanic Stats ────────────────────────────────────────
    MAX_ENERGY_FLAT = "max_energy_flat"
    MAX_CHARGES_FLAT = "max_charges_flat"
    MAX_SPELL_BURST_FLAT = "max_spell_burst_flat"
    EXTRA_JUMPS_FLAT = "extra_jumps_flat"
    MAX_TERRA_CHARGE_STACKS_FLAT = "max_terra_charge_stacks_flat"
    TERRA_CHARGE_RECOVERY_SPEED_INC = "terra_charge_recovery_speed_inc"
    MAX_TERRA_QUANTITY_FLAT = "max_terra_quantity_flat"
    MAX_WARCRY_SKILL_CHARGES_FLAT = "max_warcry_skill_charges_flat"
    MAX_SHADOW_QUANTITY_FLAT = "max_shadow_quantity_flat"
    SHADOW_DMG_ADDITIONAL = "shadow_dmg_additional"
    DMG_TO_LIFE_ADDITIONAL = "dmg_to_life_additional"
    ELIXIR_CHARGING_PROGRESS_FLAT = "elixir_charging_progress_flat"
    BEAM_DMG_ADDITIONAL = "beam_dmg_additional"

    # ── Skill Levels ─────────────────────────────────────────────────────────
    MAIN_SKILL_LEVEL = "main_skill_level"
    PASSIVE_SKILL_LEVEL = "passive_skill_level"
    EMPOWER_SKILL_LEVEL = "empower_skill_level"
    DEFENSIVE_SKILL_LEVEL = "defensive_skill_level"
    PERSISTENT_SKILL_LEVEL = "persistent_skill_level"

    # ── Blessings ─────────────────────────────────────────────────────────────
    MAX_TENACITY_BLESSING_STACKS_FLAT = "max_tenacity_blessing_stacks_flat"
    MAX_AGILITY_BLESSING_STACKS_FLAT = "max_agility_blessing_stacks_flat"
    MAX_FOCUS_BLESSING_STACKS_FLAT = "max_focus_blessing_stacks_flat"
