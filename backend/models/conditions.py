from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class ConditionDef:
    key: str
    label: str
    category: str
    value_type: Literal["boolean", "numeric"] = "boolean"
    numeric_min: float = 0
    # max derivation: if max_from_stat set, max = max_base + source.total(max_from_stat)
    # if numeric_max set and no max_from_stat, max is that static value; if neither, unbounded
    numeric_max: float | None = None
    max_base: float = 0
    max_from_stat: str | None = None
    unit: str = ""


ALL_CONDITIONS: list[ConditionDef] = [
    # ── Weapon ────────────────────────────────────────────────────────────────
    ConditionDef("holding_shield",              "Holding a Shield",                  "Weapon"),
    ConditionDef("holding_two_handed",          "Holding Two-Handed Weapon",         "Weapon"),
    ConditionDef("holding_one_handed",          "Holding One-Handed Weapon",         "Weapon"),
    ConditionDef("dual_wielding",               "Dual Wielding",                     "Weapon"),

    # ── Blessings — boolean active flags (auto-derived from stack count > 0) ─
    ConditionDef("tenacity_active",             "Tenacity Blessing Active",          "Blessings"),
    ConditionDef("focus_active",                "Focus Blessing Active",             "Blessings"),
    ConditionDef("agility_active",              "Agility Blessing Active",           "Blessings"),

    # ── Blessings — numeric stack counts ──────────────────────────────────────
    ConditionDef(
        key="tenacity_stacks", label="Tenacity Stacks", category="Blessings",
        value_type="numeric", numeric_min=0, max_base=4,
        max_from_stat="max_tenacity_blessing_stacks_flat", unit="stacks",
    ),
    ConditionDef(
        key="agility_stacks", label="Agility Stacks", category="Blessings",
        value_type="numeric", numeric_min=0, max_base=4,
        max_from_stat="max_agility_blessing_stacks_flat", unit="stacks",
    ),
    ConditionDef(
        key="focus_stacks", label="Focus Stacks", category="Blessings",
        value_type="numeric", numeric_min=0, max_base=4,
        max_from_stat="max_focus_blessing_stacks_flat", unit="stacks",
    ),

    # ── Channeled stacks ──────────────────────────────────────────────────────
    ConditionDef(
        key="channeled_stacks", label="Channeled Stacks", category="Skill State",
        value_type="numeric", numeric_min=0, max_base=0,
        max_from_stat="max_channeled_stacks_flat", unit="stacks",
    ),

    # ── Enemy numeric state ────────────────────────────────────────────────────
    ConditionDef(
        key="enemy_ailment_count", label="Enemy Ailment Count", category="Enemy State",
        value_type="numeric", numeric_min=0, numeric_max=8, unit="count",
    ),
    ConditionDef(
        key="enemy_wilt_stacks", label="Enemy Wilt Stacks", category="Enemy State",
        value_type="numeric", numeric_min=0, numeric_max=100, unit="stacks",
    ),
    ConditionDef(
        key="enemy_torment_stacks", label="Enemy Torment Stacks", category="Enemy State",
        value_type="numeric", numeric_min=0, numeric_max=50, unit="stacks",
    ),
    ConditionDef(
        key="trauma_stacks", label="Trauma Stacks", category="Buffs",
        value_type="numeric", numeric_min=0, unit="stacks",
    ),

    # ── Buffs ─────────────────────────────────────────────────────────────────
    ConditionDef("blur_active",                 "Blur Active",                       "Buffs"),
    ConditionDef("fervor_active",               "Fervor Active",                     "Buffs"),
    ConditionDef("elixir_active",               "Elixir Skill Active",               "Buffs"),
    ConditionDef("hasten_active",               "Hasten Active",                     "Buffs"),

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

    # ── Trigger ───────────────────────────────────────────────────────────────
    ConditionDef("on_hit",                      "On Hit",                            "Trigger"),
]

# Fast lookup by key
CONDITIONS_BY_KEY: dict[str, ConditionDef] = {c.key: c for c in ALL_CONDITIONS}

# Keys of conditions that are auto-derived from a numeric sibling (stacks > 0)
DERIVED_ACTIVE_KEYS: dict[str, str] = {
    "tenacity_active": "tenacity_stacks",
    "agility_active":  "agility_stacks",
    "focus_active":    "focus_stacks",
}
