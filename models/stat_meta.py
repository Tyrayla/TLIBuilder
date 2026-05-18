# ── MANUAL COMPLETION REQUIRED ────────────────────────────────────────────────
# Every stat added to models/stat.py needs a matching entry in STAT_META below.
# This dict powers display names, grouping, and search in any UI that lists stats.
# Fields:
#   display_name   →  human-readable label shown in UI
#   category       →  group for filtering/searching (must match existing categories
#                     or add a new one to CATEGORIES at the bottom of this file)
#   modifier_type  →  "flat" | "increased" | "more"  (mirrors the stat naming convention)
#   unit           →  "" for raw numbers, "%" for percentages displayed to user
# ──────────────────────────────────────────────────────────────────────────────
from dataclasses import dataclass, field
from models.stat import Stat


@dataclass(frozen=True)
class StatMeta:
    display_name:  str
    category:      str
    modifier_type: str
    unit:          str = ""


STAT_META: dict[Stat, StatMeta] = {
    # ── Attributes ────────────────────────────────────────────────────────────
    Stat.INTELLIGENCE: StatMeta("Intelligence", "Attributes", "flat"),
    Stat.STRENGTH:     StatMeta("Strength",     "Attributes", "flat"),
    Stat.AGILITY:      StatMeta("Agility",      "Attributes", "flat"),

    # ── Physical Damage ───────────────────────────────────────────────────────
    Stat.PHYS_DAMAGE_FLAT_MIN:  StatMeta("Min Physical Damage",        "Physical Damage", "flat"),
    Stat.PHYS_DAMAGE_FLAT_MAX:  StatMeta("Max Physical Damage",        "Physical Damage", "flat"),
    Stat.PHYS_DAMAGE_INCREASED: StatMeta("Increased Physical Damage",  "Physical Damage", "increased", "%"),
    Stat.PHYS_DAMAGE_MORE:      StatMeta("More Physical Damage",       "Physical Damage", "more",      "%"),

    # ── Spell Damage ──────────────────────────────────────────────────────────
    Stat.SPELL_DAMAGE_FLAT_MIN:  StatMeta("Min Spell Damage",          "Spell Damage",    "flat"),
    Stat.SPELL_DAMAGE_FLAT_MAX:  StatMeta("Max Spell Damage",          "Spell Damage",    "flat"),
    Stat.SPELL_DAMAGE_INCREASED: StatMeta("Increased Spell Damage",    "Spell Damage",    "increased", "%"),
    Stat.SPELL_DAMAGE_MORE:      StatMeta("More Spell Damage",         "Spell Damage",    "more",      "%"),

    # ── Cast Speed ────────────────────────────────────────────────────────────
    Stat.CASTS_PER_SECOND:     StatMeta("Casts per Second",           "Cast Speed",      "flat"),
    Stat.CAST_SPEED_INCREASED: StatMeta("Increased Cast Speed",       "Cast Speed",      "increased", "%"),

    # ── Attack Speed ──────────────────────────────────────────────────────────
    Stat.ATTACKS_PER_SECOND:    StatMeta("Attacks per Second",        "Attack Speed",    "flat"),
    Stat.ATTACK_SPEED_INCREASED: StatMeta("Increased Attack Speed",   "Attack Speed",    "increased", "%"),

    # ── Critical Strike ───────────────────────────────────────────────────────
    Stat.CRIT_CHANCE:     StatMeta("Critical Strike Chance",          "Critical Strike", "flat",      "%"),
    Stat.CRIT_MULTIPLIER: StatMeta("Critical Strike Multiplier",      "Critical Strike", "increased", "%"),

    # ── Life ──────────────────────────────────────────────────────────────────
    Stat.MAX_LIFE:             StatMeta("Maximum Life",               "Life",            "flat"),
    Stat.LIFE_REGEN_FLAT:      StatMeta("Life Regeneration",          "Life",            "flat"),
    Stat.LIFE_REGEN_INCREASED: StatMeta("Increased Life Regeneration","Life",            "increased", "%"),

    # ── Mana ──────────────────────────────────────────────────────────────────
    Stat.MAX_MANA:            StatMeta("Maximum Mana",                "Mana",            "flat"),
    Stat.MANA_REGEN_FLAT:     StatMeta("Mana Regeneration",           "Mana",            "flat"),
    Stat.MANA_COST_REDUCTION: StatMeta("Mana Cost Reduction",         "Mana",            "increased", "%"),

    # ── Defense ───────────────────────────────────────────────────────────────
    Stat.ARMOR:                StatMeta("Armor",                      "Defense",         "flat"),
    Stat.ALL_RESISTANCE:       StatMeta("All Resistance",             "Defense",         "flat"),
    Stat.PHYS_RESISTANCE:      StatMeta("Physical Resistance",        "Defense",         "flat"),
    Stat.FIRE_RESISTANCE:      StatMeta("Fire Resistance",            "Defense",         "flat"),
    Stat.COLD_RESISTANCE:      StatMeta("Cold Resistance",            "Defense",         "flat"),
    Stat.LIGHTNING_RESISTANCE: StatMeta("Lightning Resistance",       "Defense",         "flat"),

    # ── Utility ───────────────────────────────────────────────────────────────
    Stat.MOVEMENT_SPEED:     StatMeta("Movement Speed",               "Utility",         "flat"),
    Stat.AREA_OF_EFFECT:     StatMeta("Area of Effect",               "Utility",         "increased", "%"),
    Stat.COOLDOWN_REDUCTION: StatMeta("Cooldown Reduction",           "Utility",         "flat",      "%"),
}

# All valid category names — update this when adding a new category above.
CATEGORIES: list[str] = [
    "Attributes",
    "Physical Damage",
    "Spell Damage",
    "Cast Speed",
    "Attack Speed",
    "Critical Strike",
    "Life",
    "Mana",
    "Defense",
    "Utility",
]
