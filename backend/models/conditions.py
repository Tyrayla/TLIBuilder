from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class ConditionDef:
    key: str
    label: str
    category: str


ALL_CONDITIONS: list[ConditionDef] = [
    # ── Weapon ────────────────────────────────────────────────────────────────
    ConditionDef("holding_shield",              "Holding a Shield",                  "Weapon"),
    ConditionDef("holding_two_handed",          "Holding Two-Handed Weapon",         "Weapon"),
    ConditionDef("holding_one_handed",          "Holding One-Handed Weapon",         "Weapon"),
    ConditionDef("dual_wielding",               "Dual Wielding",                     "Weapon"),

    # ── Blessings ─────────────────────────────────────────────────────────────
    ConditionDef("tenacity_active",             "Tenacity Blessing Active",          "Blessings"),
    ConditionDef("focus_active",                "Focus Blessing Active",             "Blessings"),
    ConditionDef("agility_active",              "Agility Blessing Active",           "Blessings"),

    # ── Buffs ─────────────────────────────────────────────────────────────────
    ConditionDef("blur_active",                 "Blur Active",                       "Buffs"),
    ConditionDef("fervor_active",               "Fervor Active",                     "Buffs"),
    ConditionDef("elixir_active",               "Elixir Skill Active",               "Buffs"),

    # ── Positioning ───────────────────────────────────────────────────────────
    ConditionDef("standing_still",              "Standing Still",                    "Positioning"),
    ConditionDef("moving",                      "Moving",                            "Positioning"),
    ConditionDef("enemy_nearby",                "Enemy Nearby / In Proximity",       "Positioning"),
    ConditionDef("enemy_distant",               "Enemy Distant",                     "Positioning"),

    # ── Mana ──────────────────────────────────────────────────────────────────
    ConditionDef("at_full_mana",                "At Full Mana",                      "Mana"),
    ConditionDef("at_low_mana",                 "At Low Mana",                       "Mana"),
    ConditionDef("sealed_mana_and_life",        "Sealed Mana and Life",              "Mana"),

    # ── Enemy State ───────────────────────────────────────────────────────────
    ConditionDef("enemy_frozen",                "Enemy Frozen / Frostbitten",        "Enemy State"),
    ConditionDef("enemy_cursed",                "Enemy Cursed",                      "Enemy State"),
    ConditionDef("enemy_low_life",              "Enemy at Low Life",                 "Enemy State"),
    ConditionDef("enemy_blinded",               "Enemy Blinded",                     "Enemy State"),
    ConditionDef("enemy_ignited",               "Enemy Ignited",                     "Enemy State"),
    ConditionDef("enemy_has_ailment",           "Enemy has Ailment",                 "Enemy State"),
    ConditionDef("enemy_has_max_affliction",    "Enemy at Max Affliction",           "Enemy State"),

    # ── Recent Actions ────────────────────────────────────────────────────────
    ConditionDef("recently_defeated",           "Defeated Enemy Recently",           "Recent Actions"),
    ConditionDef("recently_regained",           "Recently Regained",                 "Recent Actions"),
    ConditionDef("recently_taken_damage",       "Recently Taken Damage",             "Recent Actions"),
    ConditionDef("recently_blocked",            "Recently Blocked",                  "Recent Actions"),
    ConditionDef("recently_crit",               "Dealt Critical Strike Recently",    "Recent Actions"),
    ConditionDef("recently_warcry",             "Used Warcry Skill Recently",        "Recent Actions"),
    ConditionDef("recently_life_regain",        "Triggered Life Regain Recently",    "Recent Actions"),
    ConditionDef("recently_shield_regain",      "Triggered Shield Regain Recently",  "Recent Actions"),
    ConditionDef("recently_lost_life",          "Lost Life Recently",                "Recent Actions"),
    ConditionDef("recently_synth_cast",         "Synthetic Troop Cast Recently",     "Recent Actions"),
    ConditionDef("recently_used_mobility",      "Used Mobility Skill Recently",      "Recent Actions"),

    # ── Skill State ───────────────────────────────────────────────────────────
    ConditionDef("sentry_not_used_recently",    "Sentry Not Used Recently",          "Skill State"),
    ConditionDef("main_skill_not_used_recently","Main Skill Not Used Recently",      "Skill State"),
    ConditionDef("channeled_not_capped",        "Channeled Stacks Not Capped",       "Skill State"),
]

# Fast lookup by key
CONDITIONS_BY_KEY: dict[str, ConditionDef] = {c.key: c for c in ALL_CONDITIONS}
