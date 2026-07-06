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
    STRENGTH_ADDITIONAL = "strength_additional"
    DEXTERITY_FLAT = "dexterity_flat"
    DEXTERITY_INC = "dexterity_inc"
    DEXTERITY_ADDITIONAL = "dexterity_additional"
    INTELLIGENCE_FLAT = "intelligence_flat"
    INTELLIGENCE_INC = "intelligence_inc"
    INTELLIGENCE_ADDITIONAL = "intelligence_additional"
    ALL_STATS_FLAT = "all_stats_flat"
    ALL_STATS_INC = "all_stats_inc"

    # ── Generic (cross-type damage) ──────────────────────────────────────────
    ARMOR_PEN = "armor_pen"
    DOUBLE_DMG_CHANCE = "double_dmg_chance"
    TRIPLE_DMG_CHANCE = "triple_dmg_chance"
    QUADRUPLE_DMG_CHANCE = "quadruple_dmg_chance"
    DMG_INC = "dmg_inc"
    DMG_ADDITIONAL = "dmg_additional"
    HIT_DMG_ADDITIONAL = "hit_dmg_additional"
    DMG_MAX_ADDITIONAL = "dmg_max_additional"
    DMG_MIN_ADDITIONAL = "dmg_min_additional"
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
    # Additional damage scoped to the MAIN-HAND weapon's share of an attack hit (e.g. Rosa Born to Cleanse).
    # A standard additional multiplier, applied only to the weapon1 base portion (offense injects it into the flat).
    MAIN_HAND_DMG_ADDITIONAL = "main_hand_dmg_additional"
    ATTACK_DOUBLE_DMG_CHANCE = "attack_double_dmg_chance"
    ATTACK_SKILL_LEVEL = "attack_skill_level"
    TWO_HANDED_BASE_DMG_ADDITIONAL = "two_handed_base_dmg_additional"
    SHIELD_DMG_INC = "shield_dmg_inc"
    RANGED_DMG_INC = "ranged_dmg_inc"

    # ── Spell ────────────────────────────────────────────────────────────────
    SPELL_DMG_INC = "spell_dmg_inc"
    SPELL_DMG_ADDITIONAL = "spell_dmg_additional"
    # Flag (Rosa Unsullied Blade): when >0, Spell DAMAGE pools (spell_dmg_inc/additional + per-element spell damage)
    # ALSO apply to attack skills — offense augments the damage-pool tag set with "spell" for attacks.
    SPELL_DMG_TO_ATTACK = "spell_dmg_to_attack"
    SPELL_DOUBLE_DMG_CHANCE = "spell_double_dmg_chance"
    SPELL_SKILL_LEVEL = "spell_skill_level"
    SPELL_BURST_CHARGE_SPEED_INC = "spell_burst_charge_speed_inc"
    SPELL_BURST_CHARGE_SPEED_ADDITIONAL = "spell_burst_charge_speed_additional"
    SPELL_BURST_CHANCE_GAIN_STACKS_FLAT = "spell_burst_chance_gain_stacks_flat"
    SPELL_BURST_HIT_DMG_ADDITIONAL = "spell_burst_hit_dmg_additional"
    # Auto-trigger sources (stat-driven so the mod lines badge Consumed). _FLAG = unconditional (Burst Activation);
    # _CHARGE_THRESHOLD = conditional charge-factor threshold (Solid River: auto only when charge speed ≥ N×base).
    SPELL_BURST_AUTO_TRIGGER_FLAG = "spell_burst_auto_trigger_flag"
    SPELL_BURST_AUTO_CHARGE_THRESHOLD = "spell_burst_auto_charge_threshold"
    # Coefficient: N% of Attack Speed bonuses also apply to Spell Burst Charge Speed (Insatiable Greed, 1.5).
    ATTACK_SPEED_TO_SPELL_BURST_CHARGE = "attack_speed_to_spell_burst_charge"
    # Solid River: "For every +X% Spell Burst Charge Speed, +Y% burst hit damage, up to +Z%" (stepwise, capped).
    CHARGE_SPEED_TO_SPELL_BURST_HIT_DMG = "charge_speed_to_spell_burst_hit_dmg"
    CHARGE_SPEED_TO_SPELL_BURST_HIT_DMG_PER = "charge_speed_to_spell_burst_hit_dmg_per"
    CHARGE_SPEED_TO_SPELL_BURST_HIT_DMG_CAP = "charge_speed_to_spell_burst_hit_dmg_cap"
    # Squiddle / Squidnova (pact spirit): bursting grants Squidnova → conditional buff; Effect scales it.
    SQUIDNOVA_EFFECT_INC = "squidnova_effect_inc"
    HAS_SQUIDNOVA_FLAG = "has_squidnova_flag"
    # Hasten (community name; in-game tooltip "Quickness", glossary id 10000106) + Attack Aggression
    # (glossary id 10000100): keyword buffs GRANTED by gear/grafts/talents. The grant lines parse to these
    # marker flags; compute auto-enables the matching condition, and the aggregator applies the buff effects.
    HAS_HASTEN_FLAG = "has_hasten_flag"
    ATTACK_AGGRESSION_FLAG = "attack_aggression_flag"
    # Aim (Euphoria buff): granted by "Triggers Lv. N Aim while standing still" gear or the Aim skill. The flag
    # carries the Aim LEVEL as its value (like has_squidnova_flag carries a threshold); compute auto-enables
    # aim_active + aim_level, and the aggregator applies the Euphoria effects (Ranged/Beam scoped).
    AIM_TRIGGER_FLAG = "aim_trigger_flag"
    # Skill Area for skills cast by Spell Burst (Prairie Fire / Kismet Ripple) — DISPLAY-only (Skill Area isn't a DPS
    # lever). Scales by Max Spell Burst M: the support pool is pre-scaled ×min(M,cap) in compute; the _PER pool is
    # per-burst-stack, scaled ×M in offense. Folded into the displayed skill_area_inc in burst mode.
    SPELL_BURST_AREA_ADDITIONAL = "spell_burst_area_additional"
    SPELL_BURST_AREA_ADDITIONAL_PER = "spell_burst_area_additional_per"
    # Burst-activation sustain (fire ONCE per burst trigger, folded into net recovery at the burst rate).
    MANA_LOST_PCT_CURRENT_PER_BURST = "mana_lost_pct_current_per_burst"          # Surging Inspiration
    LIFE_RESTORED_PCT_LOST_PER_BURST = "life_restored_pct_lost_per_burst"        # Solid River
    ENERGY_SHIELD_RESTORED_PCT_LOST_PER_BURST = "energy_shield_restored_pct_lost_per_burst"
    # Destiny kismet Flash Flood: "Halves Spell Burst Upper Limit" → halve M. (Its "+X% AS/CS per Spell Burst
    # triggered recently, up to Y%" resolves as a per-scaling of the generic Attack/Cast Speed additional on the
    # derived spell_burst_stacks_recently condition — no dedicated stat.)
    MAX_SPELL_BURST_HALVE_FLAG = "max_spell_burst_halve_flag"
    # Destiny kismet Perched River: "Critical Strikes have the Unlucky effect" → crit hits roll damage twice, keep the
    # LOWER (inverse of Lucky). Read in offense; only the crit portion is affected.
    UNLUCKY_CRIT = "unlucky_crit"

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
    MINION_COLD_DMG_ADDITIONAL = "minion_cold_dmg_additional"
    MINION_LIGHTNING_DMG_INC = "minion_lightning_dmg_inc"
    MINION_EROSION_DMG_INC = "minion_erosion_dmg_inc"
    MINION_PHYSICAL_DMG_INC = "minion_physical_dmg_inc"
    MINION_MAX_LIFE_INC = "minion_max_life_inc"
    MINION_ATTACK_SPEED_INC = "minion_attack_speed_inc"
    MINION_CAST_SPEED_INC = "minion_cast_speed_inc"
    MINION_LIFE_REGEN_SPEED_INC = "minion_life_regen_speed_inc"
    MINION_MULTISTRIKE_CHANCE = "minion_multistrike_chance"
    MINION_MULTISTRIKE_INCREASING_DMG_INC = "minion_multistrike_increasing_dmg_inc"
    MINION_IGNITE_CHANCE = "minion_ignite_chance"
    MINION_AFFLICTION_EFFECT_INC = "minion_affliction_effect_inc"
    MINION_AFFLICTION_PER_SECOND_FLAT = "minion_affliction_per_second_flat"
    MINION_ARMOR_PEN = "minion_armor_pen"
    MINION_DURATION_INC = "minion_duration_inc"
    MINION_PHYSIQUE_INC = "minion_physique_inc"
    # External +Projectile Quantity granted to a minion skill (multiple-projectile supports on the minion link,
    # a +Proj weapon shared to the minion, etc.). Some minion skills (Thunderlight Arrow) do NOT add firing
    # projectiles from this — instead each +1 grants additional damage — so it's read explicitly (no pipeline_stage).
    MINION_PROJECTILE_QUANTITY_FLAT = "minion_projectile_quantity_flat"
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
    # Core-talent additional-pool minion mods (subsystem not yet simulated — tracked, Inactive)
    MINION_PHYSICAL_DMG_ADDITIONAL = "minion_physical_dmg_additional"
    MINION_SPELL_DMG_ADDITIONAL = "minion_spell_dmg_additional"
    MINION_DMG_TAKEN_ADDITIONAL = "minion_dmg_taken_additional"
    MINION_ATTACK_SPEED_ADDITIONAL = "minion_attack_speed_additional"
    MINION_CAST_SPEED_ADDITIONAL = "minion_cast_speed_additional"
    MINION_ES_REGAIN_INC = "minion_es_regain_inc"
    SUMMON_SKILL_CAST_SPEED_ADDITIONAL = "summon_skill_cast_speed_additional"

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
    SENTRY_CAST_SPEED_ADDITIONAL = "sentry_cast_speed_additional"
    NON_SENTRY_SKILL_DMG_INC = "non_sentry_skill_dmg_inc"
    NON_SENTRY_SKILL_DMG_ADDITIONAL = "non_sentry_skill_dmg_additional"

    # ── Spirit Magi ──────────────────────────────────────────────────────────
    SPIRIT_MAGI_INITIAL_GROWTH_FLAT = "spirit_magi_initial_growth_flat"
    SPIRIT_MAGI_DMG_INC = "spirit_magi_dmg_inc"
    SPIRIT_MAGI_DMG_ADDITIONAL = "spirit_magi_dmg_additional"
    SPIRIT_MAGI_ULTIMATE_DMG_INC = "spirit_magi_ultimate_dmg_inc"
    SPIRIT_MAGI_ULTIMATE_DMG_ADDITIONAL = "spirit_magi_ultimate_dmg_additional"
    SPIRIT_MAGI_ORIGIN_EFFECT_INC = "spirit_magi_origin_effect_inc"
    SPIRIT_MAGI_ORIGIN_EFFECT_ADDITIONAL = "spirit_magi_origin_effect_additional"
    SPIRIT_MAGI_SKILL_LEVEL = "spirit_magi_skill_level"
    SPIRIT_MAGI_CRIT_RATING_FLAT = "spirit_magi_crit_rating_flat"
    SPIRIT_MAGI_SEALED_MANA_COMP_INC = "spirit_magi_sealed_mana_comp_inc"
    SPIRIT_MAGI_EMPOWER_EFFECT_ADDITIONAL = "spirit_magi_empower_effect_additional"
    SPIRIT_MAGI_ENHANCED_SKILL_CHANCE = "spirit_magi_enhanced_skill_chance"
    SPIRIT_MAGI_CDR_SPEED_INC = "spirit_magi_cdr_speed_inc"
    SPIRIT_MAGI_DMG_TAKEN_ADDITIONAL = "spirit_magi_dmg_taken_additional"
    MAX_SPIRIT_MAGI_FLAT = "max_spirit_magi_flat"

    # ── Physical ─────────────────────────────────────────────────────────────
    PHYSICAL_DMG_INC = "physical_dmg_inc"
    PHYSICAL_DMG_ADDITIONAL = "physical_dmg_additional"
    PHYSICAL_DMG_MIN_ADDITIONAL = "physical_dmg_min_additional"
    PHYSICAL_DMG_MAX_ADDITIONAL = "physical_dmg_max_additional"
    PHYSICAL_AS_LIGHTNING = "physical_as_lightning"
    PHYSICAL_AS_COLD = "physical_as_cold"
    PHYSICAL_AS_FIRE = "physical_as_fire"
    PHYSICAL_AS_EROSION = "physical_as_erosion"
    PHYSICAL_AS_ELEMENTAL = "physical_as_elemental"    # adds 40% as all 3 elements
    # ── Damage Type Conversion ────────────────────────────────────────────────
    # Priority chain (low→high): physical → lightning → cold → fire → erosion; conversion flows UP only.
    # `_convert_to_` reduces the source portion; `_as_` (adds-as) is extra. Both feed the offense
    # conversion stage. The physical_as_* + *_as_erosion adds-as keys already exist above / in their blocks.
    LIGHTNING_AS_COLD = "lightning_as_cold"
    LIGHTNING_AS_FIRE = "lightning_as_fire"
    COLD_AS_FIRE = "cold_as_fire"
    PHYSICAL_CONVERT_TO_LIGHTNING = "physical_convert_to_lightning"
    PHYSICAL_CONVERT_TO_COLD = "physical_convert_to_cold"
    PHYSICAL_CONVERT_TO_FIRE = "physical_convert_to_fire"
    PHYSICAL_CONVERT_TO_EROSION = "physical_convert_to_erosion"
    LIGHTNING_CONVERT_TO_COLD = "lightning_convert_to_cold"
    LIGHTNING_CONVERT_TO_FIRE = "lightning_convert_to_fire"
    LIGHTNING_CONVERT_TO_EROSION = "lightning_convert_to_erosion"
    COLD_CONVERT_TO_FIRE = "cold_convert_to_fire"
    COLD_CONVERT_TO_EROSION = "cold_convert_to_erosion"
    FIRE_CONVERT_TO_EROSION = "fire_convert_to_erosion"
    # Per-type Lucky indicators (>0 ⇒ that damage type rolls twice, keeps higher). Lucky keys off the
    # FINAL damage type after conversion (tested). Populated by sources like Everburn Thunderfire
    # ("Lightning Damage has Luck against Ignited") — gate via a conditional contribution.
    LUCKY_PHYSICAL = "lucky_physical"
    LUCKY_LIGHTNING = "lucky_lightning"
    LUCKY_COLD = "lucky_cold"
    LUCKY_FIRE = "lucky_fire"
    LUCKY_EROSION = "lucky_erosion"
    # Unlucky = the inverse (roll twice, keep the LOWER). Per FINAL damage type, mirrors the Lucky pool; Lucky and
    # Unlucky on the same type cancel. Plus the crit-CHANCE variants ("Critical Strikes have the Lucky/Unlucky effect").
    UNLUCKY_PHYSICAL = "unlucky_physical"
    UNLUCKY_LIGHTNING = "unlucky_lightning"
    UNLUCKY_COLD = "unlucky_cold"
    UNLUCKY_FIRE = "unlucky_fire"
    UNLUCKY_EROSION = "unlucky_erosion"
    LUCKY_CRIT = "lucky_crit"
    # ── Core-talent "conversion" lines that need other subsystems (tracked, inert until built) ──────────
    # Arcane: active-skill mana cost paid as life instead (cost mechanic; zero DPS impact; needs skill-cost
    #   modeling). NOT consumption, NOT the mana-before-life pool.
    MANA_COST_TO_LIFE_COST = "mana_cost_to_life_cost"
    # Ward: flat Max Energy Shield = coefficient × RAW Sealed (reserved) Mana / Life. Needs sealed mana/life.
    ENERGY_SHIELD_PER_SEALED_MANA = "energy_shield_per_sealed_mana"
    ENERGY_SHIELD_PER_SEALED_LIFE = "energy_shield_per_sealed_life"
    # Joined Force: fraction of the OFF-HAND weapon's (fully-scaled, attack-rate-ignored) damage added to the
    # main-hand's FINAL damage. Needs separate main/off-hand weapon damage modeling (engine averages today).
    JOINED_FORCE_OFFHAND_DMG = "joined_force_offhand_dmg"
    # Rebirth: fraction of Life / ES Regain (missing-pool recovery) turned into Restoration (heal-over-time).
    #   Needs the Regain/recovery subsystem. (Split per pool — the shared-stat splitter separates the line.)
    LIFE_REGAIN_TO_RESTORATION = "life_regain_to_restoration"
    ES_REGAIN_TO_RESTORATION = "es_regain_to_restoration"
    # Co-resonance: share attack/cast speed (inc + additional) onto Sentry Cast Frequency. Needs Sentry impl.
    ATTACK_SPEED_TO_ATTACK_SENTRY_CAST_FREQ = "attack_speed_to_attack_sentry_cast_freq"
    CAST_SPEED_TO_SPELL_SENTRY_CAST_FREQ = "cast_speed_to_spell_sentry_cast_freq"
    # Movement-speed bonus shared (coeff) onto Attack/Cast Speed / Cooldown Recovery (aggregator propagation).
    MOVEMENT_BONUS_TO_ATTACK_SPEED = "movement_bonus_to_attack_speed"
    MOVEMENT_BONUS_TO_ATTACK_SPEED_CAP = "movement_bonus_to_attack_speed_cap"  # upper bound on the converted AS bonus (Wrathful Vault +60%)
    MOVEMENT_BONUS_TO_CAST_SPEED = "movement_bonus_to_cast_speed"
    MOVEMENT_BONUS_TO_CDR = "movement_bonus_to_cdr"
    # Play Safe: flag (1.0) — propagate cast-speed inc + each cast-speed additional onto Spell Burst Charge
    #   Speed (aggregator). Spell burst charge speed isn't consumed yet, so this is ready, not yet DPS-active.
    CAST_SPEED_TO_SPELL_BURST_CHARGE = "cast_speed_to_spell_burst_charge"
    # Gale: coefficient (0.60) — additional Projectile Damage = coeff × increased Projectile Speed, as its OWN
    #   multiplicative factor (offense per-affix). FLAGGED for in-game pooling verification.
    PROJ_SPEED_TO_PROJ_DMG = "proj_speed_to_proj_dmg"
    # True Flame: coefficient (0.65) gated on enemy_ignited — the Affliction DoT-taken bonus also feeds Fire
    #   HIT damage. Inert until Affliction is modeled (no DoT-bonus value to read yet); gating is wired.
    AFFLICTION_DOT_TO_FIRE_HIT = "affliction_dot_to_fire_hit"
    # United Stand (2nd line): fraction of the minions' Regain effect also granted to you. Needs Regain +
    #   in-game testing of exactly how it applies. Low priority.
    MINION_REGAIN_SHARED_TO_PLAYER = "minion_regain_shared_to_player"
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
    # Chance to inflict an ADDITIONAL stack of Wilt (distinct mechanic from WILT_CHANCE = chance to inflict at all).
    WILT_ADDITIONAL_STACK_CHANCE = "wilt_additional_stack_chance"
    WILT_DURATION_INC = "wilt_duration_inc"

    # ── Tangle ───────────────────────────────────────────────────────────────
    TANGLE_DMG_INC = "tangle_dmg_inc"
    TANGLE_DURATION_INC = "tangle_duration_inc"
    TANGLE_DURATION_ADDITIONAL = "tangle_duration_additional"
    MAX_TANGLE_QUANTITY_FLAT = "max_tangle_quantity_flat"
    EXTRA_TANGLE_APPLIED_FLAT = "extra_tangle_applied_flat"  # +N Tangles attachable per enemy
    TANGLE_DMG_ADDITIONAL = "tangle_dmg_additional"          # additional pool (multiplicative); Dormant Entanglement
    TANGLE_DMG_ENHANCEMENT_ADDITIONAL = "tangle_dmg_enhancement_additional"  # SEPARATE multiplier, additive within itself (matches *_enhancement_additional convention)
    TANGLE_CRIT_RATING_FLAT = "tangle_crit_rating_flat"      # added to the tangled skill's crit rating
    TANGLE_ATTACH_RANGE_INC = "tangle_attach_range_inc"      # display/tracked (base 8m); not a DPS factor
    # Magister "gain 1 stack of <Blessing> when generating Tangle / activating Spell Burst" nodes → full-uptime
    # flag the compute loop reads to pin that blessing to its max while the build generates tangles/bursts.
    FOCUS_BLESSING_FULL_UPTIME_FLAG = "focus_blessing_full_uptime_flag"
    AGILITY_BLESSING_FULL_UPTIME_FLAG = "agility_blessing_full_uptime_flag"
    TENACITY_BLESSING_FULL_UPTIME_FLAG = "tenacity_blessing_full_uptime_flag"
    # Magister "immediately starts Charging Energy Shield on generate" → recognized but NYI (needs an ES-recharge
    # timing model); emitted so the line surfaces (Unconsumed) instead of silently dropping.
    ES_CHARGE_ON_GENERATE_FLAG = "es_charge_on_generate_flag"

    # ── Trauma ───────────────────────────────────────────────────────────────
    TRAUMA_DMG_INC = "trauma_dmg_inc"
    TRAUMA_DMG_ADDITIONAL = "trauma_dmg_additional"
    TRAUMA_CHANCE = "trauma_chance"
    TRAUMA_DMG_ADDITIONAL_ON_CRIT = "trauma_dmg_additional_on_crit"
    TRAUMA_REAPING_DURATION_INC = "trauma_reaping_duration_inc"
    TRAUMA_BASE_DMG_FLAT_MIN = "trauma_base_dmg_flat_min"
    TRAUMA_BASE_DMG_FLAT_MAX = "trauma_base_dmg_flat_max"
    TRAUMA_LIMIT_FLAT = "trauma_limit_flat"
    WILT_BASE_DMG_FLAT_MIN = "wilt_base_dmg_flat_min"
    WILT_BASE_DMG_FLAT_MAX = "wilt_base_dmg_flat_max"
    IGNITE_BASE_DMG_FLAT_MIN = "ignite_base_dmg_flat_min"
    IGNITE_BASE_DMG_FLAT_MAX = "ignite_base_dmg_flat_max"

    # ── Frostbite ────────────────────────────────────────────────────────────
    FROSTBITE_EFFECT_INC = "frostbite_effect_inc"
    MAX_FROSTBITE_RATING_FLAT = "max_frostbite_rating_flat"

    # ── Affliction ───────────────────────────────────────────────────────────
    AFFLICTION_EFFECT_INC = "affliction_effect_inc"
    AFFLICTION_EFFECT_ADDITIONAL = "affliction_effect_additional"
    AFFLICTION_PER_SECOND_FLAT = "affliction_per_second_flat"

    # ── Deterioration ────────────────────────────────────────────────────────
    DETERIORATION_CHANCE = "deterioration_chance"
    DETERIORATION_DMG_INC = "deterioration_dmg_inc"
    DETERIORATION_DMG_ADDITIONAL = "deterioration_dmg_additional"
    DETERIORATION_DURATION_ADDITIONAL = "deterioration_duration_additional"

    # ── Status Effects ───────────────────────────────────────────────────────
    NUMBED_EFFECT_INC = "numbed_effect_inc"
    # "additional Numbed Effect" — a separate MULTIPLICATIVE pool from numbed_effect_inc (e.g. Erika
    # Lightning Shadow). per_stack = base × (1+Σ inc) × (1+Σ additional). See aggregator Numbed block.
    NUMBED_EFFECT_ADDITIONAL = "numbed_effect_additional"
    # Raises the Electrify stack cap (Erika Lightning Shadow — Dazzling Lightning). Feeds the
    # electrify_stacks condition's max_from_stat.
    MAX_ELECTRIFY_STACKS_FLAT = "max_electrify_stacks_flat"
    NUMBED_THRESHOLD_INC = "numbed_threshold_inc"
    # Enemy-vulnerability: additional Lightning Damage the target takes from Numbed stacks.
    # Engine-injected by the aggregator (not a gear/talent affix); consumed by offense's
    # enemy-vulnerability stage. See docs/CHAIN_LIGHTNING_IMPLEMENTATION_PLAN.md §4.
    NUMBED_LIGHTNING_TAKEN = "numbed_lightning_taken"
    # Frail (Spell-form) and Infiltration (per element-type) enemy debuffs — "Additionally increases
    # <X> Damage taken". Effect-inc stats scale the per-application value (like Numbed Effect); the
    # *_taken stats are engine-injected by the aggregator and consumed by offense's enemy-vulnerability
    # stage (Frail gated on the skill being a Spell; Infiltration on the damage type).
    FRAIL_EFFECT_INC = "frail_effect_inc"
    FIRE_INFILTRATION_EFFECT_INC = "fire_infiltration_effect_inc"
    COLD_INFILTRATION_EFFECT_INC = "cold_infiltration_effect_inc"
    LIGHTNING_INFILTRATION_EFFECT_INC = "lightning_infiltration_effect_inc"
    FRAIL_SPELL_TAKEN = "frail_spell_taken"
    FIRE_INFILTRATION_TAKEN = "fire_infiltration_taken"
    COLD_INFILTRATION_TAKEN = "cold_infiltration_taken"
    LIGHTNING_INFILTRATION_TAKEN = "lightning_infiltration_taken"
    # Curse enemy-vulnerability pools — "+X% additional <type> Damage taken" baked from an applied curse skill,
    # scaled by Curse Effect, consumed per FINAL damage type by offense's enemy-vulnerability stage (so they're
    # conversion-correct). Per-type for the elemental/physical/erosion curses; hit_curse_taken (Timid) is all hit.
    PHYSICAL_CURSE_TAKEN = "physical_curse_taken"
    FIRE_CURSE_TAKEN = "fire_curse_taken"
    COLD_CURSE_TAKEN = "cold_curse_taken"
    LIGHTNING_CURSE_TAKEN = "lightning_curse_taken"
    EROSION_CURSE_TAKEN = "erosion_curse_taken"
    HIT_CURSE_TAKEN = "hit_curse_taken"
    SLOW_CHANCE = "slow_chance"
    SLOW_EFFECT_RECEIVED_INC = "slow_effect_received_inc"
    BLIND_CHANCE = "blind_chance"
    PARALYSIS_EFFECT_2H_INC = "paralysis_effect_2h_inc"
    # No Guard (Rosa High Court Chariot — Desperation): a GLOBAL enemy-vulnerability debuff inflicted on the
    # at-max channeled dump. no_guard_dmg_taken is engine-computed by the trait module (base 10% × (1+stacks-lost)
    # × (1+Block-Ratio effect)) and consumed by offense's enemy-vulnerability stage like paralysis_dmg_taken.
    # no_guard_self_dmg_taken is the PLAYER self-debuff (No Guard hits you too) — emitted but NOT yet consumed by
    # defense (NYI; lands with the conditional-defense path), so it surfaces with an NYI badge.
    NO_GUARD_DMG_TAKEN = "no_guard_dmg_taken"
    NO_GUARD_SELF_DMG_TAKEN = "no_guard_self_dmg_taken"
    # Tide (Selena — Sing with the Tide): a GLOBAL enemy-vulnerability debuff while the enemy stands on a Tide
    # (base +5-20% by trait level, × Tide Effect). Engine-computed by the trait module, consumed by offense's
    # enemy-vulnerability stage like no_guard_dmg_taken.
    TIDE_DMG_TAKEN = "tide_dmg_taken"
    # Tide Effect (Selena): the effect-scalar that amplifies the Tide's damage bonuses (your on-Tide +15%, Wave
    # Aria, Idyll, and the enemy Tide damage-taken). Standard effect pooling: tide_mult = (1 + Σ inc) ×
    # Π(1 + additional). Only the Selena trait emits these today (no gear/parser source).
    TIDE_EFFECT_INC = "tide_effect_inc"
    TIDE_EFFECT_ADDITIONAL = "tide_effect_additional"
    # Mercury Baptism (Rosa — Unsullied Blade): recorded fraction (0.12-0.44) of non-channeled attack ELEMENTAL hit
    # damage, re-dealt as TRUE damage. Read by the offense Mercury Baptism stage.
    MERCURY_BAPTISM_FRACTION = "mercury_baptism_fraction"
    # Spell Ripple (Ethereal Prism): fraction (0.75 = 50% chance × 150%) of spell hit damage re-dealt as TRUE
    # damage. Read by the offense Spell Ripple stage.
    SPELL_RIPPLE_FRACTION = "spell_ripple_fraction"
    # Mercury Points resource (Rosa). max_mercury_points = flat × (1 + inc); feeds Utmost Devotion's per-point ele.
    MAX_MERCURY_POINTS_FLAT = "max_mercury_points_flat"
    MAX_MERCURY_POINTS_INC = "max_mercury_points_inc"
    # Flag (Rosa): the base trait overrides/prevents all non-Mystic-Mercury mana consumption; Utmost Devotion clears
    # it. Mana-system stat — no DPS consumer yet (mapped for a future mana-cost hookup).
    MANA_COST_OVERRIDE = "mana_cost_override"
    # NOTE for the future skill-cost model: there are two DISTINCT cost mechanics, do not conflate them.
    #   • "Skills no longer cost Mana" (core talent Frozen Lotus; support flag skill_no_mana_cost above) SETS the
    #     skill's BASE cost to 0 — so any cost increases/multipliers still resolve to 0, and cost-derived effects
    #     ("per N Mana spent") see 0. It is NOT a cost OVERRIDE/cap on the final value.
    #   • A cost override/cap (e.g. mana_cost_override) replaces the FINAL paid value.
    # Today neither is consumed (the engine has no skill mana-cost computation); Frozen Lotus resolves to an
    # unresolved/NYI status. When skill cost is modeled, Frozen Lotus must zero the BASE cost.

    # ── Channeled / Triggered / Combo Mechanics ──────────────────────────────
    CHANNELED_DMG_INC = "channeled_dmg_inc"
    CHANNELED_DMG_ADDITIONAL = "channeled_dmg_additional"
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
    INITIAL_MULTISTRIKE_COUNT_FLAT = "initial_multistrike_count_flat"
    # Multiplies the base Multistrike Damage Increment: effective increment = base × (1 + Σ this). Read by the
    # offense multistrike stage, NOT a damage pool.
    MULTISTRIKE_INCREASING_DMG_ADDITIONAL = "multistrike_increasing_dmg_additional"
    # Chromatic Shot. main_stat_dmg_bonus_inc: raises the main-attribute damage ratio (Lightchaser +25% → 0.5%/pt
    # becomes 0.625%/pt). chromatic_shots_on_target_flat: how many fired projectiles land on the target (the shotgun
    # hit count); the chromatic_shot module emits it (full under Lightchaser/tangle, else the user input).
    MAIN_STAT_DMG_BONUS_INC = "main_stat_dmg_bonus_inc"
    CHROMATIC_SHOTS_ON_TARGET_FLAT = "chromatic_shots_on_target_flat"
    # Cat Dive (Wind Stalker): per-attack chance during multistrike to be counted at the Max Multistrike Count
    # for increment purposes. Read by the offense multistrike stage.
    MULTISTRIKE_MAX_COUNT_PROC_CHANCE = "multistrike_max_count_proc_chance"
    MAX_CHANNELED_STACKS_FLAT = "max_channeled_stacks_flat"
    MIN_CHANNELED_STACKS_FLAT = "min_channeled_stacks_flat"
    # Additional strike rate for a channeled persistent entity (Howling Gale's Gale), e.g. Furious Sweep's
    # "+X% Gale Attack Frequency per channeled stack". offense multiplies the Gale rate by (1 + Σ this).
    CHANNELED_ATTACK_FREQUENCY_ADDITIONAL = "channeled_attack_frequency_additional"
    # Icebound Beam canvas supports. Chilling Spike disables the RESET continuous-suppression (beam stays full)
    # and adds extra penetrating Icy Blades (net single-target blade-equivalents, no shotgun). Ring Blade's
    # Frozen proc adds full Icy Blade bursts per second while the enemy is Frozen. All engine-read in offense.
    CONTINUOUS_SUPPRESSION_DISABLE = "continuous_suppression_disable"
    ICY_BLADE_EXTRA_BLADE_EQUIV = "icy_blade_extra_blade_equiv"
    ICY_BLADE_FROZEN_BURST_RATE = "icy_blade_frozen_burst_rate"
    JUMP_DMG_FOR_EVERY_ADDITIONAL = "jump_dmg_for_every_additional"  # revisit stacking behavior
    # Split Shot: Volley grants Shotgun Effect (the base skill "cannot hit the same enemy"). Presence-gated flag
    # emitted slot-local by skill_effects/split_shot.py; offense uses it to let projectiles shotgun one target.
    SAME_TARGET_SHOTGUN_GRANT = "same_target_shotgun_grant"

    # ── Steep Strike ─────────────────────────────────────────────────────────
    STEEP_STRIKE_CHANCE = "steep_strike_chance"
    STEEP_STRIKE_ADDITIONAL_DMG = "steep_strike_additional_dmg"
    SWEEP_SLASH_ADDITIONAL_DMG = "sweep_slash_additional_dmg"

    # ── Cast Speed ───────────────────────────────────────────────────────────
    CAST_SPEED_INC = "cast_speed_inc"
    CAST_SPEED_ADDITIONAL = "cast_speed_additional"
    WARCRY_CAST_SPEED_INC = "warcry_cast_speed_inc"   # "Warcry Cast Speed" (warcry-scoped; e.g. Lion's Roars)

    # ── Attack Speed ─────────────────────────────────────────────────────────
    ATTACK_SPEED_GEAR = "attack_speed_gear"
    ATTACK_SPEED_MH = "attack_speed_mh"
    ATTACK_SPEED_INC = "attack_speed_inc"
    ATTACK_SPEED_ADDITIONAL = "attack_speed_additional"

    # ── Other Speeds ─────────────────────────────────────────────────────────
    MOVEMENT_SPEED_INC = "movement_speed_inc"
    MOVEMENT_SPEED_ADDITIONAL = "movement_speed_additional"
    FOCUS_SPEED_INC = "focus_speed_inc"

    # ── Critical Strike — Rating ─────────────────────────────────────────────
    ATTACK_CRIT_RATING_GEAR = "attack_crit_rating_gear"
    ATTACK_CRIT_RATING_MH = "attack_crit_rating_mh"
    CRIT_RATING_INC = "crit_rating_inc"
    CRIT_RATING_ADDITIONAL = "crit_rating_additional"
    ATTACK_CRIT_RATING_INC = "attack_crit_rating_inc"
    SPELL_CRIT_RATING_INC = "spell_crit_rating_inc"
    MINION_CRIT_RATING_INC = "minion_crit_rating_inc"
    ATTACK_CRIT_RATING_FLAT = "attack_crit_rating_flat"
    WEAPON_CRIT_RATING_FLAT = "weapon_crit_rating_flat"
    SPELL_CRIT_RATING_FLAT = "spell_crit_rating_flat"
    MINION_CRIT_RATING_FLAT = "minion_crit_rating_flat"

    # ── Critical Strike — Damage ─────────────────────────────────────────────
    CRIT_DMG_INC = "crit_dmg_inc"
    CRIT_DMG_ADDITIONAL = "crit_dmg_additional"
    # "+X% additional damage when you land a Critical Strike" — an additional-damage pool weighted by the build's
    # FINALIZED crit chance (effective = X × crit_chance), folded into the additional product in offense. Used by
    # the Critical Strike Damage Increase support + Licorice Note's Razor Leaf ingredient.
    DMG_ADDITIONAL_ON_CRIT = "dmg_additional_on_crit"
    # "For every 400 Max Energy Shield, +X% additional damage, up to +Y%" (Licorice Note's Pixie Tear ingredient).
    # Per-unit (per 400 ES) and cap are separate stats; offense folds min(max_es/400 × per_unit, cap) into the
    # additional product. Not scaled by Elixir Effect.
    DMG_ADDITIONAL_PER_400_ES = "dmg_additional_per_400_es"
    DMG_ADDITIONAL_PER_400_ES_CAP = "dmg_additional_per_400_es_cap"
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
    KNOCKBACK_DISTANCE_ADDITIONAL = "knockback_distance_additional"
    # Howling Gale — Headwind: GLOBAL enemy-vulnerability (engine-computed by the support, gated on the
    # enemy_knocked_back condition). Read in offense._enemy_vuln_mult.
    KNOCKBACK_DMG_TAKEN = "knockback_dmg_taken"

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
    ENEMY_INJURY_BUFFER_INC = "enemy_injury_buffer_inc"   # debuff: enemies' injury buffer (downside)

    # ── Mana ─────────────────────────────────────────────────────────────────
    MAX_MANA_FLAT = "max_mana_flat"
    MAX_MANA_INC = "max_mana_inc"
    MAX_MANA_ADDITIONAL = "max_mana_additional"
    MANA_REGEN_FLAT = "mana_regen_flat"
    MANA_REGEN_SPEED_INC = "mana_regen_speed_inc"
    MANA_REGEN_PCT = "mana_regen_pct"                # % of max mana per second
    MANA_BEFORE_LIFE_INC = "mana_before_life_inc"
    SKILL_COST_FLAT = "skill_cost_flat"              # flat addition to skill cost (negative = reduction)
    ATTACK_SKILL_COST_FLAT = "attack_skill_cost_flat"
    SPELL_SKILL_COST_FLAT = "spell_skill_cost_flat"
    SKILL_COST_INC = "skill_cost_inc"
    SKILL_COST_ADDITIONAL = "skill_cost_additional"
    SKILL_COST_REDUCTION = "skill_cost_reduction"    # legacy / talent-tree source
    SEALED_MANA_COMPENSATION_INC = "sealed_mana_compensation_inc"
    SEALED_MANA_COMPENSATION_ADDITIONAL = "sealed_mana_compensation_additional"

    # ── Consumption (self-consume drains: Mana Boil, life-consume affixes) ─────
    # Per-event consume rate by pool × basis × cadence. The consumption stage turns these into life/mana/ES drained
    # per second (pct_current × current pool, pct_max × max pool, flat as-is; per_cast × casts/sec). Gated affixes
    # (while Fervor / at Full Life) ride the normal condition-gating of their contribution. NOT the skill's intrinsic
    # mana cost — that (Arcane / Frozen Lotus) stays a separate future gap.
    LIFE_CONSUMED_PCT_CURRENT_PER_SEC = "life_consumed_pct_current_per_sec"
    LIFE_CONSUMED_PCT_MAX_PER_SEC = "life_consumed_pct_max_per_sec"
    LIFE_CONSUMED_FLAT_PER_SEC = "life_consumed_flat_per_sec"
    LIFE_CONSUMED_PCT_CURRENT_PER_CAST = "life_consumed_pct_current_per_cast"
    LIFE_CONSUMED_PCT_MAX_PER_CAST = "life_consumed_pct_max_per_cast"
    LIFE_CONSUMED_FLAT_PER_CAST = "life_consumed_flat_per_cast"
    MANA_CONSUMED_PCT_CURRENT_PER_SEC = "mana_consumed_pct_current_per_sec"
    MANA_CONSUMED_PCT_MAX_PER_SEC = "mana_consumed_pct_max_per_sec"
    MANA_CONSUMED_FLAT_PER_SEC = "mana_consumed_flat_per_sec"
    MANA_CONSUMED_PCT_CURRENT_PER_CAST = "mana_consumed_pct_current_per_cast"
    MANA_CONSUMED_PCT_MAX_PER_CAST = "mana_consumed_pct_max_per_cast"
    MANA_CONSUMED_FLAT_PER_CAST = "mana_consumed_flat_per_cast"
    ENERGY_SHIELD_CONSUMED_PCT_CURRENT_PER_SEC = "energy_shield_consumed_pct_current_per_sec"
    ENERGY_SHIELD_CONSUMED_PCT_MAX_PER_SEC = "energy_shield_consumed_pct_max_per_sec"
    ENERGY_SHIELD_CONSUMED_FLAT_PER_SEC = "energy_shield_consumed_flat_per_sec"
    # Skill-type-SCOPED per-USE consume ("Consumes X% … when you use Attack Skills"): multiplied by the build's
    # ATTACK-skill use rate (not the generic cast rate), and counts only attack-skill uses. (per_cast above is the
    # unscoped "on skill use".)
    LIFE_CONSUMED_PCT_CURRENT_PER_ATTACK_USE = "life_consumed_pct_current_per_attack_use"
    LIFE_CONSUMED_PCT_MAX_PER_ATTACK_USE = "life_consumed_pct_max_per_attack_use"
    LIFE_CONSUMED_FLAT_PER_ATTACK_USE = "life_consumed_flat_per_attack_use"
    MANA_CONSUMED_PCT_CURRENT_PER_ATTACK_USE = "mana_consumed_pct_current_per_attack_use"
    MANA_CONSUMED_PCT_MAX_PER_ATTACK_USE = "mana_consumed_pct_max_per_attack_use"
    MANA_CONSUMED_FLAT_PER_ATTACK_USE = "mana_consumed_flat_per_attack_use"
    # Unsullied Blade (Rosa #2) mana cycle. Mystic Mercury consume BYPASSES the "Mana can only be consumed by
    # Mystic Mercury" lock (so the lock can zero every OTHER mana-consume source while this one still counts);
    # the lock itself is a flag emitted only by Unsullied Blade's base node (off when Utmost Devotion is picked).
    MANA_CONSUMED_PCT_CURRENT_PER_ATTACK_USE_MYSTIC = "mana_consumed_pct_current_per_attack_use_mystic"
    MANA_CONSUME_EXTERNAL_BLOCKED = "mana_consume_external_blocked"
    # Mana RESTORATION per non-channeled attack use (Realm of Mercury restores 15% of unsealed Max Mana/attack;
    # Born to Cleanse's −30% additional mana restoration applies via the trait before this is emitted).
    MANA_RESTORED_PCT_CURRENT_PER_ATTACK_USE = "mana_restored_pct_current_per_attack_use"
    # Derived (written back by the consumption stage so offense / conditions can read the rolling "consumed recently"
    # total = consumed_per_sec × the "recently" window).
    CONSUMED_RECENTLY_LIFE = "consumed_recently_life"
    CONSUMED_RECENTLY_MANA = "consumed_recently_mana"
    CONSUMED_RECENTLY_ENERGY_SHIELD = "consumed_recently_energy_shield"

    # Per-N-consumed CONSUMER scalings, NORMALIZED to "per 1 unit consumed recently" at parse time (a "+X% per N
    # consumed" affix → X/100/N). The consumption loop multiplies by consumed_recently and caps, emitting the result
    # into the live pools (so they converge). Cap is the affix's "up to Y%" (fraction); 0 = uncapped.
    DMG_ADDITIONAL_PER_LIFE_CONSUMED = "dmg_additional_per_life_consumed"
    DMG_ADDITIONAL_PER_LIFE_CONSUMED_CAP = "dmg_additional_per_life_consumed_cap"
    # Plain "+X% damage for every N Life consumed" is INCREASED (per the bonus-vs-additional rule); the
    # "additional damage" variant above stays additional. Folds into the generic increased pool in offense.
    DMG_INC_PER_LIFE_CONSUMED = "dmg_inc_per_life_consumed"
    DMG_INC_PER_LIFE_CONSUMED_CAP = "dmg_inc_per_life_consumed_cap"
    ATTACK_SPEED_INC_PER_LIFE_CONSUMED = "attack_speed_inc_per_life_consumed"
    ATTACK_SPEED_INC_PER_LIFE_CONSUMED_CAP = "attack_speed_inc_per_life_consumed_cap"
    SPELL_DMG_INC_PER_MANA_CONSUMED = "spell_dmg_inc_per_mana_consumed"
    SPELL_DMG_INC_PER_MANA_CONSUMED_CAP = "spell_dmg_inc_per_mana_consumed_cap"
    # Compensatory Life: "+X% Mana Regeneration Speed for every N Mana consumed". Folds into mana_regen_speed_inc (the same
    # stat the flat "Mana Regeneration Speed" affix resolves to), so it flows through the recovery mana-regen path.
    MANA_REGEN_SPEED_INC_PER_MANA_CONSUMED = "mana_regen_speed_inc_per_mana_consumed"
    MANA_REGEN_SPEED_INC_PER_MANA_CONSUMED_CAP = "mana_regen_speed_inc_per_mana_consumed_cap"
    # Per-N-consumed DIVISORS (the "N" in "for every N consumed"). consumed-recently is quantized DOWN to a whole
    # multiple of N before applying the per-unit benefit — "for every N" procs in discrete stacks, not fractionally.
    DMG_ADDITIONAL_PER_LIFE_CONSUMED_UNIT = "dmg_additional_per_life_consumed_unit"
    DMG_INC_PER_LIFE_CONSUMED_UNIT = "dmg_inc_per_life_consumed_unit"
    ATTACK_SPEED_INC_PER_LIFE_CONSUMED_UNIT = "attack_speed_inc_per_life_consumed_unit"
    SPELL_DMG_INC_PER_MANA_CONSUMED_UNIT = "spell_dmg_inc_per_mana_consumed_unit"
    MANA_REGEN_SPEED_INC_PER_MANA_CONSUMED_UNIT = "mana_regen_speed_inc_per_mana_consumed_unit"
    # Flat PHYSICAL damage added per N consumed recently (Blade-dancer's Fingers = Life→Attacks; Glacier Caster
    # Shield = Mana→Attacks+Spells). min/max are separate keys; attack/spell scope kept separate (honest scoping).
    # The "Stacks up to Z time(s)" cap is stored as a CONSUMED-AMOUNT cap (Z × N) so one cap clamps min AND max
    # proportionally. offense folds: capped = min(consumed_recently, cap); flat += capped × per_unit.
    PHYSICAL_ATTACK_DMG_FLAT_MIN_PER_LIFE_CONSUMED = "physical_attack_dmg_flat_min_per_life_consumed"
    PHYSICAL_ATTACK_DMG_FLAT_MAX_PER_LIFE_CONSUMED = "physical_attack_dmg_flat_max_per_life_consumed"
    PHYSICAL_ATTACK_DMG_FLAT_MIN_PER_MANA_CONSUMED = "physical_attack_dmg_flat_min_per_mana_consumed"
    PHYSICAL_ATTACK_DMG_FLAT_MAX_PER_MANA_CONSUMED = "physical_attack_dmg_flat_max_per_mana_consumed"
    PHYSICAL_SPELL_DMG_FLAT_MIN_PER_MANA_CONSUMED = "physical_spell_dmg_flat_min_per_mana_consumed"
    PHYSICAL_SPELL_DMG_FLAT_MAX_PER_MANA_CONSUMED = "physical_spell_dmg_flat_max_per_mana_consumed"
    PHYSICAL_DMG_FLAT_PER_LIFE_CONSUMED_CAP = "physical_dmg_flat_per_life_consumed_cap"
    PHYSICAL_DMG_FLAT_PER_MANA_CONSUMED_CAP = "physical_dmg_flat_per_mana_consumed_cap"
    # Crit per N consumed (Tyrant's Iron Fist = +5% INCREASED Crit Rating + ADDITIVE Crit Damage per ~890 Mana,
    # uncapped). Fold into crit_rating_inc and crit_dmg_inc (× consumed_recently_mana) in the offense crit stage.
    CRIT_RATING_INC_PER_MANA_CONSUMED = "crit_rating_inc_per_mana_consumed"
    CRIT_DMG_INC_PER_MANA_CONSUMED = "crit_dmg_inc_per_mana_consumed"
    CRIT_RATING_INC_PER_MANA_CONSUMED_UNIT = "crit_rating_inc_per_mana_consumed_unit"
    CRIT_DMG_INC_PER_MANA_CONSUMED_UNIT = "crit_dmg_inc_per_mana_consumed_unit"
    PHYSICAL_DMG_FLAT_PER_LIFE_CONSUMED_UNIT = "physical_dmg_flat_per_life_consumed_unit"
    PHYSICAL_DMG_FLAT_PER_MANA_CONSUMED_UNIT = "physical_dmg_flat_per_mana_consumed_unit"

    # ── Energy Shield ─────────────────────────────────────────────────────────
    MAX_ENERGY_SHIELD_FLAT = "max_energy_shield_flat"
    MAX_ENERGY_SHIELD_INC = "max_energy_shield_inc"
    MAX_ENERGY_SHIELD_ADDITIONAL = "max_energy_shield_additional"
    ENERGY_SHIELD_REGAIN_INC = "energy_shield_regain_inc"
    ENERGY_SHIELD_CHARGE_SPEED_INC = "energy_shield_charge_speed_inc"
    ENERGY_SHIELD_REGAIN_INTERVAL_ADDITIONAL = "energy_shield_regain_interval_additional"
    ENERGY_SHIELD_CHARGE_INTERVAL_ADDITIONAL = "energy_shield_charge_interval_additional"

    # ── Barrier ───────────────────────────────────────────────────────────────
    BARRIER_ABSORPTION_RATE_INC = "barrier_absorption_rate_inc"
    BARRIER_SHIELD_INC = "barrier_shield_inc"
    BARRIER_SHIELD_ADDITIONAL = "barrier_shield_additional"
    MAX_DEFLECTION_STACKS_FLAT = "max_deflection_stacks_flat"

    # ── Defense ───────────────────────────────────────────────────────────────
    ARMOR_FLAT = "armor_flat"
    ARMOR_INC = "armor_inc"
    ARMOR_ADDITIONAL = "armor_additional"
    EVASION_FLAT = "evasion_flat"
    EVASION_INC = "evasion_inc"
    EVASION_ADDITIONAL = "evasion_additional"
    EVASION_ON_SPELL_DMG_INC = "evasion_on_spell_dmg_inc"
    EVASION_ON_SPELL_DMG_ADDITIONAL = "evasion_on_spell_dmg_additional"
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
    # Aggregate max-resistance for Elemental (Fire/Cold/Lightning ONLY — Erosion is NOT elemental). Adds to each
    # of the three per-type caps in defense._elem_resist. (Tenacity Dew, scaled by Elixir Effect.)
    MAX_ELEMENTAL_RESISTANCE_INC = "max_elemental_resistance_inc"
    ATTACK_BLOCK_CHANCE_INC = "attack_block_chance_inc"
    SPELL_BLOCK_CHANCE_INC = "spell_block_chance_inc"
    BLOCK_RATIO_INC = "block_ratio_inc"
    # Raises the Block Ratio Upper Limit (base 60%, max 80%) — Rosa Invulnerability. Block Ratio (base 30%) is
    # clamped to this limit in defense.py.
    BLOCK_RATIO_UPPER_LIMIT_FLAT = "block_ratio_upper_limit_flat"
    INTIMIDATING_EFFECT_INC = "intimidating_effect_inc"
    SHIELD_ENERGY_SHIELD_INC = "shield_energy_shield_inc"
    CHEST_DEFENSE_INC = "chest_defense_inc"

    # ── Damage Taken ─────────────────────────────────────────────────────────
    DMG_TAKEN_ADDITIONAL = "dmg_taken_additional"
    PHYSICAL_DMG_TAKEN_ADDITIONAL = "physical_dmg_taken_additional"
    ELEMENTAL_DMG_TAKEN_ADDITIONAL = "elemental_dmg_taken_additional"
    TRAUMA_DMG_TAKEN_INC = "trauma_dmg_taken_inc"
    DOT_DMG_TAKEN_ADDITIONAL = "dot_dmg_taken_additional"
    CRIT_DMG_TAKEN_REDUCTION = "crit_dmg_taken_reduction"  # defensive: reduces incoming crit damage (not yet consumed by engine)

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
    CDR_SPEED_ADDITIONAL = "cdr_speed_additional"   # additional (multiplicative) CDR pool; pairs with CDR_SPEED_INC
    WARCRY_CDR_SPEED_INC = "warcry_cdr_speed_inc"

    # ── Skill Mechanics ───────────────────────────────────────────────────────
    SKILL_AREA_INC = "skill_area_inc"
    SKILL_AREA_ADDITIONAL = "skill_area_additional"   # additional Skill Area pool (e.g. Berserking Blade Sweep)
    ATTACK_SKILL_AREA_INC = "attack_skill_area_inc"
    # Coefficient: fraction of the skill-area bonus also applied as additional Steep Strike Damage
    # (Berserking Blade Rampage). Read by the per-slot finalize, not the offense pipeline directly.
    SKILL_AREA_TO_STEEP_STRIKE_DMG = "skill_area_to_steep_strike_dmg"
    SKILL_EFFECT_DURATION_INC = "skill_effect_duration_inc"
    SKILL_EFFECT_DURATION_ADDITIONAL = "skill_effect_duration_additional"
    RESTORATION_EFFECT_INC = "restoration_effect_inc"
    # ── Restoration / Recovery (heal-over-time; see engine/recovery.py) ────────
    # Restoration total = base × (1 + Σ restoration_effect_inc) × Π(1 + restoration_effect_additional). Duration =
    # base window × (1 + Σ restoration_duration_inc) × Π(1 + restoration_duration_additional). recovery/sec = total
    # ÷ max(duration, recast). Temporary Life/Mana = a separate used-first barrier (NOT folded into max_life).
    RESTORATION_EFFECT_ADDITIONAL = "restoration_effect_additional"
    RESTORATION_DURATION_INC = "restoration_duration_inc"
    RESTORATION_DURATION_ADDITIONAL = "restoration_duration_additional"
    TEMPORARY_LIFE_FLAT = "temporary_life_flat"
    TEMPORARY_LIFE_PCT = "temporary_life_pct"            # % of Base Max Life granted as Temporary Life
    TEMPORARY_MANA_FLAT = "temporary_mana_flat"
    TEMPORARY_MANA_PCT = "temporary_mana_pct"            # % of Base Max Mana granted as Temporary Mana
    MAX_TEMPORARY_LIFE_PCT = "max_temporary_life_pct"    # cap on Temporary Life (% of Base Max Life)
    MAX_TEMPORARY_MANA_PCT = "max_temporary_mana_pct"
    EXCESS_RESTORATION_TO_ES_PCT = "excess_restoration_to_es_pct"   # Pixie Tear: % of excess Life restoration → ES

    # ── Reaping ───────────────────────────────────────────────────────────────
    REAPING_DURATION_INC = "reaping_duration_inc"
    REAPING_DURATION_ADDITIONAL = "reaping_duration_additional"
    REAPING_RECOVERY_SPEED_INC = "reaping_recovery_speed_inc"

    # ── Buff / Aura Effects ───────────────────────────────────────────────────
    # (Curse limit lives in CURSE_LIMIT_CAP_FLAT / MAX_CURSES_FLAT below; the old duplicate `max_curse_flat`
    #  was consolidated into `max_curses_flat`.)
    CURSE_EFFECT_AGAINST_INC = "curse_effect_against_inc"
    TAUNT_ON_HIT_CHANCE = "taunt_on_hit_chance"
    ATTACK_TAUNT_ON_HIT_CHANCE = "attack_taunt_on_hit_chance"
    FERVOR_EFFECT_INC = "fervor_effect_inc"
    # SKILL-LOCAL increased Fervor Effect: adds into the same (increased) pool as fervor_effect_inc for a
    # skill's intrinsic Fervor damage bonus ONLY — it does NOT scale the global Fervor→crit. Read by
    # IntrinsicAdditional.skill_effect_key. e.g. Focused Slash: Tranquility (verified increased-not-
    # additional vs the in-game recount, 2026-06-13).
    FERVOR_EFFECT_SKILL_INC = "fervor_effect_skill_inc"
    # DPS-inert tracked chance: Moon Strike: Lunar Ring's circular-attack proc on Steep Strike (surfaced
    # to the user as a %, no single-target damage effect).
    MOON_STRIKE_CIRCULAR_CHANCE = "moon_strike_circular_chance"
    BLUR_EFFECT_INC = "blur_effect_inc"
    WARCRY_EFFECT_INC = "warcry_effect_inc"
    WARCRY_SKILL_AREA_INC = "warcry_skill_area_inc"
    ELIXIR_EFFECT_INC = "elixir_effect_inc"
    ELIXIR_EFFECT_ADDITIONAL = "elixir_effect_additional"
    ELIXIR_DURATION_ADDITIONAL = "elixir_duration_additional"
    AURA_EFFECT_INC = "aura_effect_inc"
    AURA_EFFECT_ADDITIONAL = "aura_effect_additional"
    # Empower Skill Effect — scales the Euphoria buff an empower skill grants (global gear/talents + slot-local from
    # the skill's own line + its empower supports). Increased sums, additional multiplies (like Aura Effect).
    EMPOWER_EFFECT_INC = "empower_effect_inc"
    EMPOWER_EFFECT_ADDITIONAL = "empower_effect_additional"
    MAX_CHARGE_FLAT = "max_charge_flat"   # "+N Max Charge(s)" — skill charges (cooldown skills only; e.g. Mass Effect)
    CURSE_EFFECT_INC = "curse_effect_inc"
    CURSE_EFFECT_ADDITIONAL = "curse_effect_additional"   # "+X% additional Curse Effect" (multiplies; e.g. Defile)
    CURSE_SKILL_AREA_INC = "curse_skill_area_inc"
    MAX_CURSES_FLAT = "max_curses_flat"                   # "You can cast N additional Curses" (curse limit +N)
    CURSE_LIMIT_CAP_FLAT = "curse_limit_cap_flat"         # "You can only cast N Curses" (Hekate's Vision — caps limit)
    FOCUS_SKILL_DMG_ADDITIONAL = "focus_skill_dmg_additional"
    FOCUS_SKILL_SEALED_MANA_COMP_INC = "focus_skill_sealed_mana_comp_inc"
    MARK_EFFECT_INC = "mark_effect_inc"
    MARK_ON_CRIT_CHANCE = "mark_on_crit_chance"
    CC_EFFECT_INC = "cc_effect_inc"
    ILL_OMEN_EFFICIENCY_INC = "ill_omen_efficiency_inc"
    DEMOLISHER_CHARGE_SPEED_INC = "demolisher_charge_speed_inc"
    # Demolisher supports: Cripple's "+X% additional damage for that cast" (the whole consuming cast); a generic
    # "at the center" additional-damage pool (Epicenter, reusable by future center-bonus sources).
    DEMOLISHER_CONSUME_DMG_ADDITIONAL = "demolisher_consume_dmg_additional"
    AT_CENTER_DMG_ADDITIONAL = "at_center_dmg_additional"
    # Activation-medium trigger cadence: a seconds-valued OVERRIDE of the cast/trigger rate (cast rate = 1/interval)
    # for any skill triggered by a medium with an "every X s" cadence (Rhythm/Track/Instruction/Preparation).
    TRIGGER_INTERVAL = "trigger_interval"
    # Wind Rhythm: a tick-quantized cadence off a per-tier base cooldown, sped by CDR + a share of Cast Speed.
    WIND_RHYTHM_BASE_COOLDOWN = "wind_rhythm_base_cooldown"   # seconds (per-tier); presence = Wind Rhythm active
    WIND_RHYTHM_SHARE = "wind_rhythm_share"                   # fraction of Cast Speed applied to CDR (the roll)
    # Sentry Activation Medium: how many sentries are deployed at a time (surfaced; distinct from max quantity).
    SENTRY_DEPLOYED_COUNT_FLAT = "sentry_deployed_count_flat"
    AGILITY_BLESSING_DURATION_INC = "agility_blessing_duration_inc"
    FOCUS_BLESSING_DURATION_INC = "focus_blessing_duration_inc"
    TENACITY_BLESSING_DURATION_INC = "tenacity_blessing_duration_inc"
    BLESSING_DURATION_INC = "blessing_duration_inc"
    BLESSING_DURATION_ADDITIONAL = "blessing_duration_additional"
    FOCUS_DMG_ENHANCEMENT_ADDITIONAL = "focus_dmg_enhancement_additional"
    AILMENT_DMG_ENHANCEMENT_ADDITIONAL = "ailment_dmg_enhancement_additional"
    WARCRY_MIN_TARGETS_FLAT = "warcry_min_targets_flat"
    FOCUS_SKILL_LEVEL = "focus_skill_level"

    # ── Gear-Specific Stats ───────────────────────────────────────────────────
    PHYSICAL_DMG_GEAR_INC = "physical_dmg_gear_inc"
    ENERGY_SHIELD_GEAR_FLAT = "energy_shield_gear_flat"
    ENERGY_SHIELD_GEAR_INC = "energy_shield_gear_inc"
    WEAPON_ATTACK_SPEED = "weapon_attack_speed"
    WEAPON_DMG_ADDITIONAL = "weapon_dmg_additional"   # NOTE: confirm weapon-LOCAL scaling before wiring
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

    # ── Support modeling (roadmap #2) ─────────────────────────────────────────
    PROJECTILE_SPEED_ADDITIONAL = "projectile_speed_additional"
    AILMENT_DMG_ADDITIONAL = "ailment_dmg_additional"   # inert until ailment DPS modeled
    ATTACK_AILMENT_DMG_ADDITIONAL = "attack_ailment_dmg_additional"  # ailment dmg dealt by attacks
    DOT_DMG_ADDITIONAL = "dot_dmg_additional"           # inert until DoT modeled
    PARALYZE_CHANCE = "paralyze_chance"
    WAVE_INTERVAL_INC = "wave_interval_inc"
    EXTRA_BEAMS_FLAT = "extra_beams_flat"               # +N beams / refractions
    CANNOT_INFLICT_IGNITE = "cannot_inflict_ignite"
    CANNOT_INFLICT_FROSTBITE = "cannot_inflict_frostbite"
    CANNOT_INFLICT_NUMBED = "cannot_inflict_numbed"
    CANNOT_INFLICT_WILT = "cannot_inflict_wilt"
    ES_UNINTERRUPTIBLE = "es_uninterruptible"
    # % of Max Life added as flat Energy Shield (Tortoise Shell). Applied in derive.py AFTER Max Life is computed,
    # folded into the ES flat pool BEFORE max_energy_shield scales by ES inc/additional.
    MAX_LIFE_AS_ES_PCT = "max_life_as_es_pct"
    # % of damage taken that bypasses Energy Shield (Tortoise Shell). FLAG only today — surfaced, not yet applied
    # (waiting on the defensive damage-taken pass). Stored so it is never silently dropped.
    ES_BYPASS_PCT = "es_bypass_pct"
    IGNITE_STACKS_INFLICTED_FLAT = "ignite_stacks_inflicted_flat"   # +N stacks inflicted (≠ max)
    WILT_STACKS_INFLICTED_FLAT = "wilt_stacks_inflicted_flat"
    EXTRA_MAX_MINIONS_FLAT = "extra_max_minions_flat"
