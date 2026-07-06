"""Minion modifier resolution guard — gear/talent minion affixes must resolve to `minion_*` (or `spirit_magi_*`)
stats and NEVER leak into the player's pools. The mod parser is shared by gear, talent nodes, and core talents,
so this one guard covers all three surfaces (a minion analogue of test_gear_badge_drift's intent)."""
import pytest

from engine.mod_parser import _parse_custom_mod_text as P


def _keys(text):
    return {d["stat_key"] for d in P(text)}


# (text, expected minion stat keys) — order-insensitive. Covers the families the pre-fix parser mis-handled.
CASES = [
    ("+20% Minion Attack and Cast Speed", {"minion_attack_speed_inc", "minion_cast_speed_inc"}),
    ("+15% additional Minion Attack and Cast Speed", {"minion_attack_speed_additional", "minion_cast_speed_additional"}),
    ("+22% Attack and Cast Speed for Minions summoned by the supported skill",
     {"minion_attack_speed_inc", "minion_cast_speed_inc"}),
    ("+18% Cooldown Recovery Speed for Minions", {"minion_cdr_speed_inc"}),
    ("+30% additional Damage Taken by Minions", {"minion_dmg_taken_additional"}),
    ("Adds 8-161 Lightning Damage to Minions", {"minion_lightning_dmg_flat_min", "minion_lightning_dmg_flat_max"}),
    ("Adds 113-140 Base Physical Damage to Minions", {"minion_physical_dmg_flat_min", "minion_physical_dmg_flat_max"}),
    ("Minion Damage penetrates 8% Elemental Resistance", {"minion_elemental_pen"}),
    ("Minion Damage penetrates 12% Cold Resistance", {"minion_cold_pen_inc"}),
    ("+25% chance for Minions to deal Double Damage", {"minion_double_dmg_chance"}),
    ("+30% Minion Damage", {"minion_dmg_inc"}),
    ("+25% additional Minion Damage", {"minion_dmg_additional"}),
    ("+120 Minion Critical Strike Rating", {"minion_crit_rating_flat"}),
    ("+30% additional Spell Damage for Minions", {"minion_spell_dmg_additional"}),
]


@pytest.mark.parametrize("text,expected", CASES)
def test_minion_affix_resolves_to_minion_stats(text, expected):
    keys = _keys(text)
    assert keys == expected, f"{text!r} -> {keys}, expected {expected}"
    for k in keys:                                   # never a bare player key
        assert k.startswith(("minion_", "spirit_magi_")), f"player leak: {text!r} -> {k}"


# A minion-scoped mod with NO minion equivalent must resolve to NOTHING (surfaced red), never leak to the player.
NO_LEAK = [
    "+18% additional Cooldown Recovery Speed for Minions summoned by the supported skill",  # no minion_cdr_additional
]


@pytest.mark.parametrize("text", NO_LEAK)
def test_unmapped_minion_mod_never_leaks_to_player(text):
    for k in _keys(text):
        assert k.startswith(("minion_", "spirit_magi_")), f"player leak: {text!r} -> {k}"


def test_isomorphic_arms_flag_parses():
    assert _keys("Minions gain the Main-Hand Weapon's bonuses") == {"minions_inherit_mainhand_weapon"}
