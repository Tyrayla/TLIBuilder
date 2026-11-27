"""Cicada Shell (SS14 legendary chest): "Adds Elemental Damage equal to N % of Max Energy Shield to Attacks and
Spells" is flat Fire AND Cold AND Lightning damage, each = N% x FINAL Max ES (min = max, not split across the
elements), credited to both attacks and spells. Owner ruling 2026-11-27."""
import pytest

from engine.compute import compute
from engine.models import BuildInput
from engine.mod_parser import _parse_custom_mod_text
from server import _resolve_gear_affix_clauses

BASE_LINE = ("-80 % Energy Shield Charge Speed -5 % Energy Shield Regain "
             "Adds Elemental Damage equal to {pct} % of Max Energy Shield to Attacks and Spells")
CORRODED_LINE = ("(-40-40) % Energy Shield Charge Speed "
                 "Adds Elemental Damage equal to {pct} % of Max Energy Shield to Attacks and Spells")


def _gear(text, slot="chest", item_name="Cicada Shell"):
    contributions = []
    for resolved in _resolve_gear_affix_clauses(text):
        for entry in resolved["parsed"]:
            contributions.append({
                "stat": entry["stat_key"], "display_value": entry["amount"], "unit": "",
                "condition": resolved["cond_expr"], "text": resolved["clause"],
                "item_name": item_name, "slot": slot,
            })
    return [{"contributions": contributions}]


def _calc(text, es_flat=8000.0, es_inc=0.0):
    character = [{"stat": "max_energy_shield_flat", "amount": es_flat, "label": "test"}]
    if es_inc:
        character.append({"stat": "max_energy_shield_inc", "amount": es_inc, "label": "test"})
    return compute(BuildInput(slots=[], slates=[], season="test", gear=_gear(text), character=character), {}, {})


def test_base_line_parses_to_es_charge_regain_and_damage_stat():
    parsed = _parse_custom_mod_text(BASE_LINE.format(pct=1.2))
    keys = {p["stat_key"]: p["amount"] for p in parsed}
    assert keys == {
        "energy_shield_charge_speed_inc": pytest.approx(-0.80),
        "energy_shield_regain_inc": pytest.approx(-0.05),
        "max_es_as_elemental_dmg_pct": pytest.approx(0.012),
    }


def test_corroded_line_parses_and_ranges_collapse_to_midpoints():
    keys = {p["stat_key"]: p["amount"]
            for p in _parse_custom_mod_text(CORRODED_LINE.format(pct="(1.3–1.6)"))}
    assert keys["max_es_as_elemental_dmg_pct"] == pytest.approx(0.0145)
    # "(-40-40)" collapses to its midpoint, 0.
    assert keys["energy_shield_charge_speed_inc"] == pytest.approx(0.0)


def test_two_copies_sum():
    gear = _gear(BASE_LINE.format(pct=1.0)) + _gear(BASE_LINE.format(pct=1.0), slot="chest2")
    result = compute(BuildInput(slots=[], slates=[], season="test", gear=gear, character=[
        {"stat": "max_energy_shield_flat", "amount": 8000.0, "label": "test"}]), {}, {})
    assert result.stat_map["fire_attack_dmg_flat_min"]["total"] == pytest.approx(160.0)


def test_line_is_resolved_for_the_gear_loop_and_badge():
    clauses = _resolve_gear_affix_clauses(BASE_LINE.format(pct=1.1))
    assert all(c["resolved"] for c in clauses)


def test_one_percent_of_8000_es_is_80_of_each_element_for_attacks_and_spells():
    result = _calc(BASE_LINE.format(pct=1.0), es_flat=8000.0)
    assert result.stat_map["max_energy_shield"]["total"] == pytest.approx(8000.0)
    for dtype in ("fire", "cold", "lightning"):
        for cls in ("attack", "spell"):
            for mm in ("min", "max"):
                assert result.stat_map[f"{dtype}_{cls}_dmg_flat_{mm}"]["total"] == pytest.approx(80.0)
    # Only the three elements — never physical/erosion.
    assert "physical_attack_dmg_flat_min" not in result.stat_map
    assert "erosion_spell_dmg_flat_min" not in result.stat_map


def test_damage_follows_final_max_es_after_increases():
    # 8000 flat x (1 + 50% inc) = 12000 final ES; 1.5% of that = 180 per element.
    result = _calc(BASE_LINE.format(pct=1.5), es_flat=8000.0, es_inc=0.5)
    assert result.stat_map["max_energy_shield"]["total"] == pytest.approx(12000.0)
    assert result.stat_map["fire_attack_dmg_flat_min"]["total"] == pytest.approx(180.0)
    assert result.stat_map["lightning_spell_dmg_flat_max"]["total"] == pytest.approx(180.0)


def test_more_es_means_more_damage():
    low = _calc(BASE_LINE.format(pct=1.0), es_flat=4000.0)
    high = _calc(BASE_LINE.format(pct=1.0), es_flat=8000.0)
    assert low.stat_map["cold_attack_dmg_flat_min"]["total"] == pytest.approx(40.0)
    assert high.stat_map["cold_attack_dmg_flat_min"]["total"] == pytest.approx(80.0)


def test_corroded_variant_end_to_end():
    result = _calc(CORRODED_LINE.format(pct=1.6), es_flat=5000.0)
    assert result.stat_map["fire_spell_dmg_flat_min"]["total"] == pytest.approx(80.0)
