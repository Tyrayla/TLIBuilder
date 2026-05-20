# ── MANUAL COMPLETION REQUIRED ────────────────────────────────────────────────
# Add every stat that exists in the game as an enum member below.
# Convention:  CATEGORY_STAT_MODIFIER
#   e.g.  PHYS_DAMAGE_FLAT_MIN, SPELL_DAMAGE_INCREASED, CRIT_CHANCE
# Modifier suffix rules:
#   _FLAT_MIN / _FLAT_MAX  →  raw additive value (lowest/highest of a range)
#   _INCREASED             →  additive % pool  (store as decimal: 0.40 = 40%)
#   _MORE                  →  multiplicative % (store as decimal: 0.12 = 12%)
#   no suffix              →  flat with no range (attributes, speeds, etc.)
# After adding a stat here, add its entry in models/stat_meta.py.
# ──────────────────────────────────────────────────────────────────────────────
from enum import Enum


class Stat(Enum):

    # ── Base Stat/Attribute ─────────────────────────────────────────────────────────────
    STRENGTH = "strength"
    DEXTERITY = "dexterity"
    INTELLIGENCE = "intelligence"

    # ── Generic ──────────────────────────────────────────────────────────────
    ARMOR_PEN = "armor_pen"
    DOUBLE_DMG_CHANCE = "double_dmg_chance"
    DMG_INC = "dmg_inc"
    DMG_ADDITIONAL = "dmg_additional"
    ALL_SKILL_LEVEL = "all_skill_level"
    ACTIVE_SKILL_LEVEL = "active_skill_level"
    SUPPORT_SKILL_LEVEL = "support_skill_level"

    # ── Attack ─────────────────────────────────────────────────────────
    ATTACK_DMG_INC = "attack_dmg_inc"
    ATTACK_DMG_ADDITIONAL = "attack_dmg_additional"
    ATTACK_DOUBLE_DMG_CHANCE = "attack_double_dmg_chance"
    ATTACK_SKILL_LEVEL = "attack_skill_level"

    # ── Spell ──────────────────────────────────────────────────────────
    SPELL_DMG_INC = "spell_dmg_inc"
    SPELL_DMG_ADDITIONAL = "spell_dmg_additional"
    SPELL_DOUBLE_DMG_CHANCE = "spell_double_dmg_chance"
    SPELL_SKILL_LEVEL = "spell_skill_level"

    # ── Melee ─────────────────────────────────────────────────────────
    MELEE_DMG_INC = "melee_dmg_inc"
    MELEE_DMG_ADDITIONAL = "melee_dmg_additional"
    MELEE_SKILL_LEVEL = "melee_skill_level"

    # ── Area ─────────────────────────────────────────────────────────
    AREA_DMG_INC = "area_dmg_inc"
    AREA_DMG_ADDITIONAL = "area_dmg_additional"

    # ── Projectile ─────────────────────────────────────────────────────────
    PROJECTILE_DMG_INC = "projectile_dmg_inc"
    PROJECTILE_DMG_ADDITIONAL = "projectile_dmg_additional"
    PROJECTILE_SPEED_INC = "projectile_speed_inc"
    PROJECTILE_SKILL_LEVEL = "projectile_skill_level"

    # ── Minion ─────────────────────────────────────────────────────────
    MINION_DMG_INC = "minion_dmg_inc"
    MINION_DMG_ADDITIONAL = "minion_dmg_additional"
    MINION_DOUBLE_DMG_CHANCE = "minion_double_dmg_chance"
    MINION_SKILL_LEVEL = "minion_skill_level"
    
    # Synthetic Troops
    SYNTH_DOUBLE_DMG_CHANCE = "synth_double_dmg_chance"
    SYNTH_SKILL_LEVEL = "synth_skill_level"

    # Spirit Magi

    # ── Sentry ─────────────────────────────────────────────────────────
    SENTRY_DMG_ADDITIONAL = "sentry_dmg_additional"
    SENTRY_SKILL_CAST_FREQUENCY_INC = "sentry_skill_cast_frequency_inc"
    SENTRY_SKILL_CAST_FREQUENCY_ADDITIONAL = "sentry_skill_cast_frequency_additional"

    # ── Physical ───────────────────────────────────────────────────────
    PHYSICAL_DMG_INC = "physical_dmg_inc"
    PHYSICAL_DMG_ADDITIONAL = "physical_dmg_additional"
    PHYSICAL_AS_LIGHTNING = "physical_as_lightning"
    PHYSICAL_AS_COLD = "physical_as_cold"
    PHYSICAL_AS_FIRE = "physical_as_fire"
    PHYSICAL_AS_EROSION = "physical_as_erosion"
    PHYSICAL_SKILL_LEVEL = "physical_skill_level"
    

    # ── Lightning ──────────────────────────────────────────────────────
    LIGHTNING_DMG_INC = "lightning_dmg_inc"
    LIGHTNING_DMG_ADDITIONAL = "lightning_dmg_additional"
    LIGHTNING_PEN = "lightning_pen"
    LIGHTNING_ATTACK_DMG_FLAT_MIN = "lightning_attack_dmg_flat_min"
    LIGHTNING_ATTACK_DMG_FLAT_MAX = "lightning_attack_dmg_flat_max"
    LIGHTNING_SPELL_DMG_FLAT_MIN = "lightning_spell_dmg_flat_min"
    LIGHTNING_SPELL_DMG_FLAT_MAX = "lightning_spell_dmg_flat_max"
    LIGHTNING_SKILL_LEVEL = "lightning_skill_level"

    # ── Cold ───────────────────────────────────────────────────────────
    COLD_DMG_INC = "cold_dmg_inc"
    COLD_DMG_ADDITIONAL = "cold_dmg_additional"
    COLD_PEN = "cold_pen"
    COLD_ATTACK_DMG_FLAT_MIN = "cold_attack_dmg_flat_min"
    COLD_ATTACK_DMG_FLAT_MAX = "cold_attack_dmg_flat_max"
    COLD_SPELL_DMG_FLAT_MIN = "cold_spell_dmg_flat_min"
    COLD_SPELL_DMG_FLAT_MAX = "cold_spell_dmg_flat_max"
    COLD_SKILL_LEVEL = "cold_skill_level"

    # ── Fire ───────────────────────────────────────────────────────────
    FIRE_DMG_INC = "fire_dmg_inc"
    FIRE_DMG_ADDITIONAL = "fire_dmg_additional"
    FIRE_PEN = "fire_pen"
    FIRE_ATTACK_DMG_FLAT_MIN = "fire_attack_dmg_flat_min"
    FIRE_ATTACK_DMG_FLAT_MAX = "fire_attack_dmg_flat_max"
    FIRE_SPELL_DMG_FLAT_MIN = "fire_spell_dmg_flat_min"
    FIRE_SPELL_DMG_FLAT_MAX = "fire_spell_dmg_flat_max"
    FIRE_SKILL_LEVEL = "fire_skill_level"

    # ── Erosion ────────────────────────────────────────────────────────
    EROSION_DMG_INC = "erosion_dmg_inc"
    EROSION_DMG_ADDITIONAL = "erosion_dmg_additional"
    EROSION_PEN = "erosion_pen"
    EROSION_ATTACK_DMG_FLAT_MIN = "erosion_attack_dmg_flat_min"
    EROSION_ATTACK_DMG_FLAT_MAX = "erosion_attack_dmg_flat_max"
    EROSION_SPELL_DMG_FLAT_MIN = "erosion_spell_dmg_flat_min"
    EROSION_SPELL_DMG_FLAT_MAX = "erosion_spell_dmg_flat_max"
    EROSION_SKILL_LEVEL = "erosion_skill_level"

    # ── Elemental ───────────────────────────────────────────────────────────
    ELEMENTAL_DMG_INC = "elemental_dmg_inc"
    ELEMENTAL_DMG_ADDITIONAL = "elemental_dmg_additional"
    ELEMENTAL_PEN = "elemental_pen"

    # ── Steep Strike ───────────────────────────────────────────────────────────
    STEEP_STRIKE_CHANCE = "steep_strike_chance"
    STEEP_STRIKE_ADDITIONAL_DMG = "steep_strike_additional_dmg"
    SWEEP_SLASH_ADDITIONAL_DMG = "sweep_slash_additional_dmg"

    # ── Cast Speed ────────────────────────────────────────────────────────────
    CAST_SPEED_INC = "cast_speed_inc"
    CAST_SPEED_ADDITIONAL = "cast_speed_additional"

    # ── Attack Speed ──────────────────────────────────────────────────────────
    ATTACK_SPEED_GEAR = "attack_speed_gear"
    ATTACK_SPEED_MH = "attack_speed_mh"
    ATTACK_SPEED_INC = "attack_speed_inc"
    ATTACK_SPEED_ADDITIONAL = "attack_speed_additional"


    # ── Critical Strike ───────────────────────────────────────────────────────
    # Inc Critical Strike Rating
    ATTACK_CRIT_RATING_GEAR   = "attack_crit_rating_gear" # affects weapon base crit chance
    ATTACK_CRIT_RATING_MH    = "attack_crit_rating_mh" # affects main hand weapon base crit chance
    ATTACK_CRIT_RATING_INC   = "attack_crit_rating_inc"
    SPELL_CRIT_RATING_INC    = "spell_crit_rating_inc"
    MINION_CRIT_RATING_INC    = "minion_crit_rating_inc"

    # Flat Critical Strike Rating
    ATTACK_CRIT_RATING_FLAT   = "attack_crit_rating_flat"
    SPELL_CRIT_RATING_FLAT    = "spell_crit_rating_flat"
    MINION_CRIT_RATING_FLAT    = "minion_crit_rating_flat"
    SPIRIT_MAGI_CRIT_RATING_FLAT    = "spirit_magi_crit_rating_flat"

    # Crit Damage
    CRIT_DMG  = "crit_dmg"
    ATTACK_CRIT_DMG = "attack_crit_dmg"
    SPELL_CRIT_DMG = "spell_crit_dmg"
    MINION_CRIT_DMG = "minion_crit_dmg"
    PHYS_CRIT_DMG = "phys_crit_dmg"
    LIGHTNING_CRIT_DMG = "lightning_crit_dmg"
    COLD_CRIT_DMG = "cold_crit_dmg"
    FIRE_CRIT_DMG = "fire_crit_dmg"
    EROSION_CRIT_DMG = "erosion_crit_dmg"

    # ── Life ──────────────────────────────────────────────────────────────────
    MAX_LIFE            = "max_life"
    MAX_LIFE_INC        = "max_life_inc"
    LIFE_REGEN_FLAT     = "life_regen_flat"
    LIFE_REGEN_INC      = "life_regen_inc"
    LIFE_LEECH_RATE     = "life_leech_rate"

    # ── Mana ──────────────────────────────────────────────────────────────────
    MAX_MANA            = "max_mana"
    MAX_MANA_INC        = "max_mana_inc"
    MANA_REGEN_FLAT     = "mana_regen_flat"
    MANA_REGEN_INC      = "mana_regen_inc"
    SKILL_COST_REDUCTION = "skill_cost_reduction"

    # ── Defense ───────────────────────────────────────────────────────────────
    ARMOR                 = "armor"
    ELEMENTAL_RESISTANCE        = "elemental_resistance"
    FIRE_RESISTANCE       = "fire_resistance"
    COLD_RESISTANCE       = "cold_resistance"
    LIGHTNING_RESISTANCE  = "lightning_resistance"
    EROSION_RESISTANCE    = "erosion_resistance"

    # ── Utility ───────────────────────────────────────────────────────────────
    MOVEMENT_SPEED_INC      = "movement_speed_inc"
    COOLDOWN_REDUCTION_INC  = "cooldown_reduction_inc"


    # ── Blessings ─────────────────────────────────────────────────────────────
    TENACITY_BLESSING = "tenacity_blessing"
    AGILITY_BLESSING = "agility_blessing"
    FOCUS_BLESSING = "focus_blessing"
