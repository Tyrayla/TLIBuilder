# ── MANUAL COMPLETION REQUIRED ────────────────────────────────────────────────
# Every stat added to models/stat.py needs a matching entry in STAT_META below.
# This dict powers display names, grouping, and search in any UI that lists stats.
# Fields:
#   display_name   →  human-readable label shown in UI (match in-game text exactly)
#   category       →  group for filtering/searching (must be in CATEGORIES list below)
#   modifier_type  →  one of: "base stat" | "flat" | "increased" | "additional" |
#                             "chance" | "skill level" | "penetration"
#   unit           →  "" for raw numbers, "%" for percentages displayed to user
# ──────────────────────────────────────────────────────────────────────────────
from dataclasses import dataclass
from models.stat import Stat


@dataclass(frozen=True)
class StatMeta:
    display_name:  str
    category:      str
    modifier_type: str
    unit:          str = ""


STAT_META: dict[Stat, StatMeta] = {

    # ── Attributes ────────────────────────────────────────────────────────────
    Stat.STRENGTH:     StatMeta("Strength",     "Attributes", "base stat"),
    Stat.DEXTERITY:    StatMeta("Dexterity",    "Attributes", "base stat"),
    Stat.INTELLIGENCE: StatMeta("Intelligence", "Attributes", "base stat"),

    # ── Generic  ──────────────────────────────────────────────────────────────
    Stat.ARMOR_PEN:           StatMeta("Armor Penetration",       "Generic", "penetration", "%"),
    Stat.DOUBLE_DMG_CHANCE:   StatMeta("Double Damage Chance",    "Generic", "chance",      "%"),
    Stat.DMG_INC:             StatMeta("Increased Damage",        "Generic", "increased",   "%"),
    Stat.DMG_ADDITIONAL:      StatMeta("Additional Damage",       "Generic", "additional",  "%"),
    Stat.ALL_SKILL_LEVEL:     StatMeta("All Skill Level",         "Generic", "skill level"),
    Stat.ACTIVE_SKILL_LEVEL:  StatMeta("Active Skill Level",      "Generic", "skill level"),
    Stat.SUPPORT_SKILL_LEVEL: StatMeta("Support Skill Level",     "Generic", "skill level"),

    # ── Attack ────────────────────────────────────────────────────────────────
    Stat.ATTACK_DMG_INC:          StatMeta("Increased Attack Damage",        "Attack", "increased",  "%"),
    Stat.ATTACK_DMG_ADDITIONAL:   StatMeta("Additional Attack Damage",       "Attack", "additional", "%"),
    Stat.ATTACK_DOUBLE_DMG_CHANCE:StatMeta("Attack Double Damage Chance",    "Attack", "chance",     "%"),
    Stat.ATTACK_SKILL_LEVEL:      StatMeta("Attack Skill Level",             "Attack", "skill level"),

    # ── Spell ─────────────────────────────────────────────────────────────────
    Stat.SPELL_DMG_INC:          StatMeta("Increased Spell Damage",         "Spell", "increased",  "%"),
    Stat.SPELL_DMG_ADDITIONAL:   StatMeta("Additional Spell Damage",        "Spell", "additional", "%"),
    Stat.SPELL_DOUBLE_DMG_CHANCE:StatMeta("Spell Double Damage Chance",     "Spell", "chance",     "%"),
    Stat.SPELL_SKILL_LEVEL:      StatMeta("Spell Skill Level",              "Spell", "skill level"),

    # ── Melee ─────────────────────────────────────────────────────────────────
    Stat.MELEE_DMG_INC:        StatMeta("Increased Melee Damage",           "Melee", "increased",  "%"),
    Stat.MELEE_DMG_ADDITIONAL: StatMeta("Additional Melee Damage",          "Melee", "additional", "%"),
    Stat.MELEE_SKILL_LEVEL:    StatMeta("Melee Skill Level",                "Melee", "skill level"),

    # ── Area ──────────────────────────────────────────────────────────────────
    Stat.AREA_DMG_INC:        StatMeta("Increased Area Damage",             "Area", "increased",  "%"),
    Stat.AREA_DMG_ADDITIONAL: StatMeta("Additional Area Damage",            "Area", "additional", "%"),

    # ── Projectile ────────────────────────────────────────────────────────────
    Stat.PROJECTILE_DMG_INC:        StatMeta("Increased Projectile Damage",  "Projectile", "increased",  "%"),
    Stat.PROJECTILE_DMG_ADDITIONAL: StatMeta("Additional Projectile Damage", "Projectile", "additional", "%"),
    Stat.PROJECTILE_SPEED_INC:      StatMeta("Increased Projectile Speed",   "Projectile", "increased",  "%"),
    Stat.PROJECTILE_SKILL_LEVEL:    StatMeta("Projectile Skill Level",       "Projectile", "skill level"),

    # ── Minion ────────────────────────────────────────────────────────────────
    Stat.MINION_DMG_INC:          StatMeta("Increased Minion Damage",            "Minion", "increased",  "%"),
    Stat.MINION_DMG_ADDITIONAL:   StatMeta("Additional Minion Damage",           "Minion", "additional", "%"),
    Stat.MINION_DOUBLE_DMG_CHANCE:StatMeta("Minion Double Damage Chance",        "Minion", "chance",     "%"),
    Stat.MINION_SKILL_LEVEL:      StatMeta("Minion Skill Level",                 "Minion", "skill level"),
    Stat.SYNTH_DOUBLE_DMG_CHANCE: StatMeta("Synthetic Troop Double Damage Chance","Minion","chance",     "%"),
    Stat.SYNTH_SKILL_LEVEL:       StatMeta("Synthetic Troop Skill Level",        "Minion", "skill level"),

    # ── Sentry ────────────────────────────────────────────────────────────────
    Stat.SENTRY_DMG_ADDITIONAL:           StatMeta("Additional Sentry Damage",          "Sentry", "additional", "%"),
    Stat.SENTRY_SKILL_CAST_FREQUENCY_INC: StatMeta("Increased Sentry Cast Frequency",   "Sentry", "increased",  "%"),
    Stat.SENTRY_SKILL_CAST_FREQUENCY_ADDITIONAL:StatMeta("Additional Sentry Cast Frequency", "Sentry", "additional", "%"),

    # ── Physical ──────────────────────────────────────────────────────────────
    Stat.PHYSICAL_DMG_INC:        StatMeta("Increased Physical Damage",     "Physical", "increased",  "%"),
    Stat.PHYSICAL_DMG_ADDITIONAL: StatMeta("Additional Physical Damage",    "Physical", "additional", "%"),
    Stat.PHYSICAL_AS_LIGHTNING:   StatMeta("Physical as Lightning",         "Physical", "flat",       "%"), # unsure if these should be flat category
    Stat.PHYSICAL_AS_COLD:        StatMeta("Physical as Cold",              "Physical", "flat",       "%"),
    Stat.PHYSICAL_AS_FIRE:        StatMeta("Physical as Fire",              "Physical", "flat",       "%"),
    Stat.PHYSICAL_AS_EROSION:     StatMeta("Physical as Erosion",           "Physical", "flat",       "%"),
    Stat.PHYSICAL_SKILL_LEVEL:    StatMeta("Physical Skill Level",          "Physical", "skill level"),

    # ── Lightning ─────────────────────────────────────────────────────────────
    Stat.LIGHTNING_DMG_INC:           StatMeta("Increased Lightning Damage",     "Lightning", "increased",  "%"),
    Stat.LIGHTNING_DMG_ADDITIONAL:    StatMeta("Additional Lightning Damage",    "Lightning", "additional", "%"),
    Stat.LIGHTNING_PEN:               StatMeta("Lightning Penetration",          "Lightning", "penetration","%"),
    Stat.LIGHTNING_ATTACK_DMG_FLAT_MIN:StatMeta("Min Lightning Attack Damage",   "Lightning", "flat"),
    Stat.LIGHTNING_ATTACK_DMG_FLAT_MAX:StatMeta("Max Lightning Attack Damage",   "Lightning", "flat"),
    Stat.LIGHTNING_SPELL_DMG_FLAT_MIN: StatMeta("Min Lightning Spell Damage",    "Lightning", "flat"),
    Stat.LIGHTNING_SPELL_DMG_FLAT_MAX: StatMeta("Max Lightning Spell Damage",    "Lightning", "flat"),
    Stat.LIGHTNING_SKILL_LEVEL:        StatMeta("Lightning Skill Level",         "Lightning", "skill level"),

    # ── Cold ──────────────────────────────────────────────────────────────────
    Stat.COLD_DMG_INC:           StatMeta("Increased Cold Damage",          "Cold", "increased",  "%"),
    Stat.COLD_DMG_ADDITIONAL:    StatMeta("Additional Cold Damage",         "Cold", "additional", "%"),
    Stat.COLD_PEN:               StatMeta("Cold Penetration",               "Cold", "penetration","%"),
    Stat.COLD_ATTACK_DMG_FLAT_MIN:StatMeta("Min Cold Attack Damage",        "Cold", "flat"),
    Stat.COLD_ATTACK_DMG_FLAT_MAX:StatMeta("Max Cold Attack Damage",        "Cold", "flat"),
    Stat.COLD_SPELL_DMG_FLAT_MIN: StatMeta("Min Cold Spell Damage",         "Cold", "flat"),
    Stat.COLD_SPELL_DMG_FLAT_MAX: StatMeta("Max Cold Spell Damage",         "Cold", "flat"),
    Stat.COLD_SKILL_LEVEL:        StatMeta("Cold Skill Level",              "Cold", "skill level"),

    # ── Fire ──────────────────────────────────────────────────────────────────
    Stat.FIRE_DMG_INC:           StatMeta("Increased Fire Damage",          "Fire", "increased",  "%"),
    Stat.FIRE_DMG_ADDITIONAL:    StatMeta("Additional Fire Damage",         "Fire", "additional", "%"),
    Stat.FIRE_PEN:               StatMeta("Fire Penetration",               "Fire", "penetration","%"),
    Stat.FIRE_ATTACK_DMG_FLAT_MIN:StatMeta("Min Fire Attack Damage",        "Fire", "flat"),
    Stat.FIRE_ATTACK_DMG_FLAT_MAX:StatMeta("Max Fire Attack Damage",        "Fire", "flat"),
    Stat.FIRE_SPELL_DMG_FLAT_MIN: StatMeta("Min Fire Spell Damage",         "Fire", "flat"),
    Stat.FIRE_SPELL_DMG_FLAT_MAX: StatMeta("Max Fire Spell Damage",         "Fire", "flat"),
    Stat.FIRE_SKILL_LEVEL:        StatMeta("Fire Skill Level",              "Fire", "skill level"),

    # ── Erosion ───────────────────────────────────────────────────────────────
    Stat.EROSION_DMG_INC:           StatMeta("Increased Erosion Damage",    "Erosion", "increased",  "%"),
    Stat.EROSION_DMG_ADDITIONAL:    StatMeta("Additional Erosion Damage",   "Erosion", "additional", "%"),
    Stat.EROSION_PEN:               StatMeta("Erosion Penetration",         "Erosion", "penetration","%"),
    Stat.EROSION_ATTACK_DMG_FLAT_MIN:StatMeta("Min Erosion Attack Damage",  "Erosion", "flat"),
    Stat.EROSION_ATTACK_DMG_FLAT_MAX:StatMeta("Max Erosion Attack Damage",  "Erosion", "flat"),
    Stat.EROSION_SPELL_DMG_FLAT_MIN: StatMeta("Min Erosion Spell Damage",   "Erosion", "flat"),
    Stat.EROSION_SPELL_DMG_FLAT_MAX: StatMeta("Max Erosion Spell Damage",   "Erosion", "flat"),
    Stat.EROSION_SKILL_LEVEL:        StatMeta("Erosion Skill Level",        "Erosion", "skill level"),

    # ── Elemental ─────────────────────────────────────────────────────────────
    Stat.ELEMENTAL_DMG_INC:        StatMeta("Increased Elemental Damage",   "Elemental", "increased",  "%"),
    Stat.ELEMENTAL_DMG_ADDITIONAL: StatMeta("Additional Elemental Damage",  "Elemental", "additional", "%"),
    Stat.ELEMENETAL_PEN:           StatMeta("Elemental Penetration",        "Elemental", "penetration","%"),

    # ── Steep Strike ──────────────────────────────────────────────────────────
    Stat.STEEP_STRIKE_CHANCE:        StatMeta("Steep Strike Chance",             "Steep Strike", "chance",     "%"),
    Stat.STEEP_STRIKE_ADDITIONAL_DMG:StatMeta("Steep Strike Additional Damage",  "Steep Strike", "additional", "%"),
    Stat.SWEEP_SLASH_ADDITIONAL_DMG: StatMeta("Sweep Slash Additional Damage",   "Steep Strike", "additional", "%"),

    # ── Cast Speed ────────────────────────────────────────────────────────────
    Stat.CAST_SPEED_INC:        StatMeta("Increased Cast Speed",            "Cast Speed", "increased",  "%"),
    Stat.CAST_SPEED_ADDITIONAL: StatMeta("Additional Cast Speed",           "Cast Speed", "additional", "%"),

    # ── Attack Speed ──────────────────────────────────────────────────────────
    Stat.ATTACK_SPEED_GEAR:       StatMeta("Attack Speed (Gear)",           "Attack Speed", "increased",  "%"),
    Stat.ATTACK_SPEED_MH:         StatMeta("Attack Speed (Main Hand)",      "Attack Speed", "increased",  "%"),
    Stat.ATTACK_SPEED_INC:        StatMeta("Increased Attack Speed",        "Attack Speed", "increased",  "%"),
    Stat.ATTACK_SPEED_ADDITIONAL: StatMeta("Additional Attack Speed",       "Attack Speed", "additional", "%"),

    # ── Critical Strike ───────────────────────────────────────────────────────
    # Rating
    Stat.ATTACK_CRIT_RATING_GEAR:  StatMeta("Attack Crit Rating (Gear)",          "Critical Strike", "increased", "%"),
    Stat.ATTACK_CRIT_RATING_MH:    StatMeta("Attack Crit Rating (Main Hand)",     "Critical Strike", "increased", "%"),
    Stat.ATTACK_CRIT_RATING_INC:   StatMeta("Increased Attack Crit Rating",       "Critical Strike", "increased", "%"),
    Stat.SPELL_CRIT_RATING_INC:    StatMeta("Increased Spell Crit Rating",        "Critical Strike", "increased", "%"),
    Stat.MINION_CRIT_RATING_INC:   StatMeta("Increased Minion Crit Rating",       "Critical Strike", "increased", "%"),
    Stat.ATTACK_CRIT_RATING_FLAT:  StatMeta("Attack Critical Strike Rating",      "Critical Strike", "flat"),
    Stat.SPELL_CRIT_RATING_FLAT:   StatMeta("Spell Critical Strike Rating",       "Critical Strike", "flat"),
    Stat.MINION_CRIT_RATING_FLAT:  StatMeta("Minion Critical Strike Rating",      "Critical Strike", "flat"),
    Stat.SPIRIT_MAGI_CRIT_RATING_FLAT: StatMeta("Spirit Magi Crit Rating",        "Critical Strike", "flat"),
    # Crit Damage
    Stat.CRIT_DMG:          StatMeta("Critical Strike Damage",              "Critical Strike", "increased", "%"),
    Stat.ATTACK_CRIT_DMG:   StatMeta("Attack Critical Strike Damage",       "Critical Strike", "increased", "%"),
    Stat.SPELL_CRIT_DMG:    StatMeta("Spell Critical Strike Damage",        "Critical Strike", "increased", "%"),
    Stat.MINION_CRIT_DMG:   StatMeta("Minion Critical Strike Damage",       "Critical Strike", "increased", "%"),
    Stat.PHYS_CRIT_DMG:     StatMeta("Physical Critical Strike Damage",     "Critical Strike", "increased", "%"),
    Stat.LIGHTNING_CRIT_DMG:StatMeta("Lightning Critical Strike Damage",    "Critical Strike", "increased", "%"),
    Stat.COLD_CRIT_DMG:     StatMeta("Cold Critical Strike Damage",         "Critical Strike", "increased", "%"),
    Stat.FIRE_CRIT_DMG:     StatMeta("Fire Critical Strike Damage",         "Critical Strike", "increased", "%"),
    Stat.EROSION_CRIT_DMG:  StatMeta("Erosion Critical Strike Damage",      "Critical Strike", "increased", "%"),

    # ── Defense ───────────────────────────────────────────────────────────────
    Stat.ARMOR:                StatMeta("Armor",                "Defense", "flat"),
    Stat.ELEMENTAL_RESISTANCE: StatMeta("Elemental Resistance", "Defense", "flat"),
    Stat.FIRE_RESISTANCE:      StatMeta("Fire Resistance",      "Defense", "flat"),
    Stat.COLD_RESISTANCE:      StatMeta("Cold Resistance",      "Defense", "flat"),
    Stat.LIGHTNING_RESISTANCE: StatMeta("Lightning Resistance", "Defense", "flat"),
    Stat.EROSION_RESISTANCE:   StatMeta("Erosion Resistance",   "Defense", "flat"),

    # ── Blessings ─────────────────────────────────────────────────────────────
    Stat.TENACITY_BLESSING: StatMeta("Tenacity Blessing", "Blessings", "flat"),
    Stat.AGILITY_BLESSING:  StatMeta("Agility Blessing",  "Blessings", "flat"),
    Stat.FOCUS_BLESSING:    StatMeta("Focus Blessing",    "Blessings", "flat"),
}

# All valid category names — update when adding a new category above.
CATEGORIES: list[str] = [
    "Attributes",
    "Baseline",
    "Attack",
    "Spell",
    "Melee",
    "Area",
    "Projectile",
    "Minion",
    "Sentry",
    "Physical",
    "Lightning",
    "Cold",
    "Fire",
    "Erosion",
    "Elemental",
    "Steep Strike",
    "Cast Speed",
    "Attack Speed",
    "Critical Strike",
    "Defense",
    "Blessings",
]
