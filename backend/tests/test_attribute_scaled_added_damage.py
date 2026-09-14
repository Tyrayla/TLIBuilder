"""Regression coverage for bug found 2026-09-10: Tower Sequence's "Adds A-B <Type> Damage to
Attacks per N <Attribute>" text was silently truncated by `_CUSTOM_ADDS_RE` (which has no
end-anchor and matched the "Adds A-B <Type> Damage to Attacks" prefix before the per-attribute
regex ever ran), producing a flat, non-scaling added-damage contribution instead of one that
scales with the attribute. Ralph's Burial / Magnus' Jealousy (armor, no "to Attacks/Spells" scope
word in the raw text) were unaffected because their text never matches `_CUSTOM_ADDS_RE`.

The fix moves the per-attribute regex ahead of `_CUSTOM_ADDS_RE` and extends it to accept an
optional "to Attacks/Spells/Attacks and Spells" scope clause, crediting only the scoped class
instead of both (Tower Sequence's weapon-local mod, unlike Ralph's Burial/Magnus' Jealousy's
unscoped armor mod, which owner-confirmed 2026-09-02 applies to BOTH Attacks and Spells)."""
import pytest

from engine.compute import compute
from engine.models import BuildInput
from engine.mod_parser import _parse_custom_mod_text
from server import _resolve_gear_affix_clauses


def _gear(text, slot="weapon1", item_name="Tower Sequence"):
    """Build the exact GearEngineItem contribution shape from raw affix text (mirrors
    test_warcry.py's _kragol_gear helper)."""
    contributions = []
    for resolved in _resolve_gear_affix_clauses(text):
        for entry in resolved["parsed"]:
            contributions.append({
                "stat": entry["stat_key"], "display_value": entry["amount"], "unit": "",
                "condition": resolved["cond_expr"], "text": resolved["clause"],
                "item_name": item_name, "slot": slot,
            })
    return [{"contributions": contributions}]


def test_scoped_text_parses_to_per_class_keys_not_swallowed_by_custom_adds_re():
    parsed = _parse_custom_mod_text("Adds 2 - 2 Fire Damage to Attacks per 10 Strength")
    keys = {p["stat_key"]: p["amount"] for p in parsed}
    assert keys == {
        "fire_attack_dmg_flat_min_per_strength": pytest.approx(0.2),
        "fire_attack_dmg_flat_max_per_strength": pytest.approx(0.2),
        "fire_attack_dmg_flat_per_strength_unit": 10.0,
    }


def test_unscoped_text_still_parses_to_the_original_unscoped_keys():
    """Regression guard for the reordering: Ralph's Burial / Magnus' Jealousy text (no "to
    Attacks/Spells" scope word) must still hit the unscoped branch unchanged."""
    parsed = _parse_custom_mod_text("Adds 2-5 Fire Damage per 10 Strength")
    keys = {p["stat_key"]: p["amount"] for p in parsed}
    assert keys == {
        "fire_dmg_flat_min_per_strength": pytest.approx(0.2),
        "fire_dmg_flat_max_per_strength": pytest.approx(0.5),
        "fire_dmg_flat_per_strength_unit": 10.0,
    }


def test_scoped_text_both_classes_via_attacks_and_spells():
    """"to Attacks and Spells" must credit BOTH classes, not just one — the alternation in the
    regex must try the longer "attacks and spells" phrase before the bare "attacks" one."""
    parsed = _parse_custom_mod_text("Adds 2 - 2 Fire Damage to Attacks and Spells per 10 Strength")
    keys = {p["stat_key"]: p["amount"] for p in parsed}
    assert keys == {
        "fire_attack_dmg_flat_min_per_strength": pytest.approx(0.2),
        "fire_attack_dmg_flat_max_per_strength": pytest.approx(0.2),
        "fire_attack_dmg_flat_per_strength_unit": 10.0,
        "fire_spell_dmg_flat_min_per_strength": pytest.approx(0.2),
        "fire_spell_dmg_flat_max_per_strength": pytest.approx(0.2),
        "fire_spell_dmg_flat_per_strength_unit": 10.0,
    }


def test_scoped_text_with_doubly_ranged_amount():
    """A doubly-ranged roll ("(2-3) - (4-5)") combined with the new scope clause must still
    collapse via the shared _tc range-midpoint substitution before the regex runs."""
    parsed = _parse_custom_mod_text("Adds (2-3) - (4-5) Fire Damage to Attacks per 10 Strength")
    keys = {p["stat_key"]: p["amount"] for p in parsed}
    assert keys == {
        "fire_attack_dmg_flat_min_per_strength": pytest.approx(0.25),   # (2+3)/2 / 10
        "fire_attack_dmg_flat_max_per_strength": pytest.approx(0.45),   # (4+5)/2 / 10
        "fire_attack_dmg_flat_per_strength_unit": 10.0,
    }


def test_scoped_text_with_ranged_divisor():
    """A ranged divisor ("per (7-8) Strength") combined with the scope clause must also
    collapse via _tc before the regex runs."""
    parsed = _parse_custom_mod_text("Adds 2 - 2 Fire Damage to Attacks per (7-8) Strength")
    keys = {p["stat_key"]: p["amount"] for p in parsed}
    assert keys == {
        "fire_attack_dmg_flat_min_per_strength": pytest.approx(2.0 / 7.5),
        "fire_attack_dmg_flat_max_per_strength": pytest.approx(2.0 / 7.5),
        "fire_attack_dmg_flat_per_strength_unit": 7.5,
    }


def _calc(strength, text, *additional_texts):
    gear = []
    for index, candidate in enumerate((text, *additional_texts)):
        gear.extend(_gear(candidate, slot="weapon1" if index == 0 else "weapon2"))
    return compute(
        BuildInput(slots=[], slates=[], season="test", gear=gear,
                   character=[{"stat": "strength", "amount": strength, "label": "test"}]),
        {}, {})


def test_tower_sequence_scoped_text_scales_with_strength_and_only_credits_attacks():
    result = _calc(55, "Adds 2 - 2 Fire Damage to Attacks per 10 Strength")
    # floor(55/10) = 5 whole units x 2 per unit = 10, both min and max (2-2 is a flat, non-ranged roll).
    assert result.stat_map["fire_attack_dmg_flat_min"]["total"] == pytest.approx(10.0)
    assert result.stat_map["fire_attack_dmg_flat_max"]["total"] == pytest.approx(10.0)
    # Scoped to Attacks only — must NOT leak into the Spell pool.
    assert "fire_spell_dmg_flat_min" not in result.stat_map
    assert "fire_spell_dmg_flat_max" not in result.stat_map


def test_tower_sequence_scoped_text_zero_below_first_breakpoint():
    result = _calc(9, "Adds 2 - 2 Fire Damage to Attacks per 10 Strength")
    assert "fire_attack_dmg_flat_min" not in result.stat_map


def test_identical_scoped_attribute_lines_round_per_equipped_source():
    text = "Adds 2 - 2 Fire Damage to Attacks per 10 Strength"
    result = _calc(55, text, text)
    # Each weapon has floor(55 / 10) = 5 chunks, so the two sources contribute
    # 10 + 10. Pooling before rounding would incorrectly use floor(55 / 20) = 2.
    assert result.stat_map["fire_attack_dmg_flat_min"]["total"] == pytest.approx(20.0)
    assert result.stat_map["fire_attack_dmg_flat_max"]["total"] == pytest.approx(20.0)


def test_unscoped_text_still_credits_both_attacks_and_spells():
    """Regression guard: the reordering must not change Ralph's Burial / Magnus' Jealousy's
    owner-confirmed both-Attacks-and-Spells behavior."""
    result = _calc(55, "Adds 2-5 Fire Damage per 10 Strength")
    assert result.stat_map["fire_attack_dmg_flat_min"]["total"] == pytest.approx(10.0)
    assert result.stat_map["fire_attack_dmg_flat_max"]["total"] == pytest.approx(25.0)
    assert result.stat_map["fire_spell_dmg_flat_min"]["total"] == pytest.approx(10.0)
    assert result.stat_map["fire_spell_dmg_flat_max"]["total"] == pytest.approx(25.0)


def test_identical_unscoped_attribute_lines_round_per_equipped_source():
    text = "Adds 2-5 Fire Damage per 10 Strength"
    result = _calc(55, text, text)
    # The unscoped sibling keeps the same independent-breakpoint rule and then
    # contributes each source once to both attack and spell pools.
    assert result.stat_map["fire_attack_dmg_flat_min"]["total"] == pytest.approx(20.0)
    assert result.stat_map["fire_attack_dmg_flat_max"]["total"] == pytest.approx(50.0)
    assert result.stat_map["fire_spell_dmg_flat_min"]["total"] == pytest.approx(20.0)
    assert result.stat_map["fire_spell_dmg_flat_max"]["total"] == pytest.approx(50.0)


def test_scoped_text_to_attacks_and_spells_credits_each_class_once_not_doubled():
    """Highest-risk path this diff's fold restructuring protects against: ONE raw affix line
    scoped to "Attacks and Spells" must credit each class exactly once — not double-credit either
    class, and not cross-contaminate a same-text Attacks-only line's grouping."""
    result = _calc(55, "Adds 2 - 2 Fire Damage to Attacks and Spells per 10 Strength")
    assert result.stat_map["fire_attack_dmg_flat_min"]["total"] == pytest.approx(10.0)
    assert result.stat_map["fire_attack_dmg_flat_max"]["total"] == pytest.approx(10.0)
    assert result.stat_map["fire_spell_dmg_flat_min"]["total"] == pytest.approx(10.0)
    assert result.stat_map["fire_spell_dmg_flat_max"]["total"] == pytest.approx(10.0)
