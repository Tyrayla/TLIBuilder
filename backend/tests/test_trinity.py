"""Trinity (SS14 legendary chest): Law/Edict of Trinity hit model + res-based elemental penetration.

Law of Trinity (glossary): hits deal ONLY Elemental Damage, 5x (Edict: 6x), one element picked per hit with
weight inverse to its share of flat damage; no conversion. Owner rulings 2026-11-27: P(e) ∝ 1/flat_e, a
zero-flat element is picked with certainty (and deals 0), multiplier applies to the picked element's final hit.
Penetration = min over fire/cold/lightning of min(res, max res)."""
import pytest
from engine.mod_parser import _parse_custom_mod_text as parse
from engine.offense import _trinity_pick_weights
from server import engine_stats, EngineStatsRequest
from tests.mock_build import make_request, DUAL_WEAPONS


def _gear(**stats):
    return DUAL_WEAPONS + [{"item_name": "X", "contributions": [
        {"stat": k, "display_value": v, "unit": "", "slot": "ring", "item_name": "X", "text": f"+{v} {k}"}
        for k, v in stats.items()]}]


def _off(gear=None):
    r = engine_stats(EngineStatsRequest(**make_request("berserking_blade", 20, gear=gear)))
    d = r if isinstance(r, dict) else r.model_dump()
    return d["offense"]


def _flat(**per_elem):
    out = {}
    for e, v in per_elem.items():
        out[f"{e}_attack_dmg_flat_min"] = v
        out[f"{e}_attack_dmg_flat_max"] = v
    return out


def _form_by_type(off):
    return off["hit_forms"][0]["damage_by_type"]


# ── parser ──────────────────────────────────────────────────────────────────────────────────────
def test_parser_law_and_edict():
    assert parse("Law of Trinity")[0]["stat_key"] == "trinity_hit_multiplier"
    assert parse("Law of Trinity")[0]["amount"] == 5.0
    assert parse("Edict of Trinity")[0]["amount"] == 6.0


def test_parser_penetration_line_plain_and_corroded():
    plain = parse("Gains Elemental Resistance Penetration equal to your minimum effective Elemental Resistance")
    assert [m["stat_key"] for m in plain] == ["elemental_pen_from_min_res"]
    corroded = parse("Gains Elemental Resistance Penetration equal to your minimum effective Elemental "
                     "Resistance +19% additional Elemental Damage")
    assert [(m["stat_key"], m["amount"]) for m in corroded] == [
        ("elemental_pen_from_min_res", 1.0), ("elemental_dmg_additional", pytest.approx(0.19))]


# ── pick weights (inverse to flat share) ────────────────────────────────────────────────────────
def test_weights_equal_flat_even_thirds():
    w = _trinity_pick_weights({e: (100.0, 100.0) for e in ("fire", "cold", "lightning")})
    assert w == {e: pytest.approx(1 / 3) for e in ("fire", "cold", "lightning")}


def test_weights_skewed_inverse_to_flat():
    # flat 100/200/400 → inverse 1/100:1/200:1/400 = 4:2:1 → 4/7, 2/7, 1/7
    w = _trinity_pick_weights({"fire": (100, 100), "cold": (200, 200), "lightning": (400, 400)})
    assert w["fire"] == pytest.approx(4 / 7)
    assert w["cold"] == pytest.approx(2 / 7)
    assert w["lightning"] == pytest.approx(1 / 7)


def test_weights_zero_flat_certain_and_ties_split():
    one = _trinity_pick_weights({"fire": (50, 50), "lightning": (80, 80)})   # cold absent = 0 flat
    assert one == {"fire": 0.0, "cold": 1.0, "lightning": 0.0}
    two = _trinity_pick_weights({"fire": (50, 50)})
    assert two == {"fire": 0.0, "cold": 0.5, "lightning": 0.5}


# ── hit model ───────────────────────────────────────────────────────────────────────────────────
def test_equal_flat_is_multiplier_times_average_of_elements():
    flat = _flat(fire=100, cold=100, lightning=100)
    base = _form_by_type(_off(_gear(**flat)))
    law = _off(_gear(**flat, trinity_hit_multiplier=5.0))
    total_base = sum(base[e] for e in ("fire", "cold", "lightning"))
    # Per-element damage is identical when flat is equal and no type-specific mods → average = total/3.
    assert sum(_form_by_type(law).values()) == pytest.approx(5.0 * total_base / 3.0, rel=1e-6)
    assert set(k for k, v in _form_by_type(law).items() if v) == {"fire", "cold", "lightning"}


def test_zero_flat_element_deals_zero():
    flat = _flat(fire=100, lightning=100)           # no cold flat → cold is picked every hit → 0 damage
    law = _off(_gear(**flat, trinity_hit_multiplier=5.0))
    assert law["total_dps"] == pytest.approx(0.0)


def test_skewed_flat_follows_inverse_weights():
    flat = _flat(fire=100, cold=200, lightning=400)
    base = _form_by_type(_off(_gear(**flat)))
    law = _form_by_type(_off(_gear(**flat, trinity_hit_multiplier=5.0)))
    for e, p in (("fire", 4 / 7), ("cold", 2 / 7), ("lightning", 1 / 7)):
        assert law[e] == pytest.approx(5.0 * p * base[e], rel=1e-6)


def test_edict_uses_six_and_drops_non_elemental():
    flat = {**_flat(fire=100, cold=100, lightning=100), "physical_attack_dmg_flat_min": 500,
            "physical_attack_dmg_flat_max": 500}
    edict = _form_by_type(_off(_gear(**flat, trinity_hit_multiplier=6.0)))
    law = _form_by_type(_off(_gear(**flat, trinity_hit_multiplier=5.0)))
    assert edict.get("physical", 0.0) == 0.0
    assert sum(edict.values()) == pytest.approx(sum(law.values()) * 6.0 / 5.0, rel=1e-6)


def test_no_conversion_under_trinity():
    flat = _flat(fire=100, cold=100, lightning=100)
    plain = _off(_gear(**flat, trinity_hit_multiplier=5.0))
    conv = _off(_gear(**flat, trinity_hit_multiplier=5.0, fire_convert_to_cold=1.0))
    assert conv["total_dps"] == pytest.approx(plain["total_dps"], rel=1e-9)


# ── resistance-based penetration ────────────────────────────────────────────────────────────────
def _elemental_pen(gear):
    r = engine_stats(EngineStatsRequest(**make_request("berserking_blade", 20, gear=gear)))
    d = r if isinstance(r, dict) else r.model_dump()
    return d["target_stats"]["pen"]["elemental"]


def test_pen_equals_min_effective_resistance():
    g = _gear(elemental_pen_from_min_res=1.0, fire_resistance=0.6, cold_resistance=0.6, lightning_resistance=0.6,
              max_elemental_resistance_inc=0.15)
    assert _elemental_pen(g) == pytest.approx(0.60)


def test_pen_takes_the_minimum_element():
    g = _gear(elemental_pen_from_min_res=1.0, fire_resistance=0.6, cold_resistance=0.4, lightning_resistance=0.6)
    assert _elemental_pen(g) == pytest.approx(0.40)


def test_pen_capped_by_max_resistance():
    # 80% resistance but the default 60% max → effective 60%
    g = _gear(elemental_pen_from_min_res=1.0, fire_resistance=0.8, cold_resistance=0.8, lightning_resistance=0.8)
    assert _elemental_pen(g) == pytest.approx(0.60)


def test_pen_raises_damage_vs_target():
    res = dict(fire_resistance=0.6, cold_resistance=0.6, lightning_resistance=0.6)
    flat = _flat(fire=100, cold=100, lightning=100)
    without = _off(_gear(**flat, **res, trinity_hit_multiplier=5.0))["total_dps_vs_target"]
    with_pen = _off(_gear(**flat, **res, trinity_hit_multiplier=5.0, elemental_pen_from_min_res=1.0))["total_dps_vs_target"]
    # dummy 30% res → 70% taken; 60% pen → 30% res − 60% = −30% → 130% taken. Ratio 1.3/0.7.
    assert with_pen / without == pytest.approx(1.3 / 0.7, rel=1e-3)


# ── review follow-ups ───────────────────────────────────────────────────────────────────────────
def test_parsed_item_text_end_to_end():
    """Real item text → parser stat keys → engine damage number (no hand-written Trinity stat keys)."""
    flat = _flat(fire=100, cold=100, lightning=100)
    plain = _form_by_type(_off(_gear(**flat)))
    gear = _gear(**flat)
    contribs = gear[-1]["contributions"]
    for text in ("Law of Trinity",
                 "Gains Elemental Resistance Penetration equal to your minimum effective Elemental Resistance"):
        for m in parse(text):
            contribs.append({"stat": m["stat_key"], "display_value": m["amount"], "unit": "", "slot": "ring",
                             "item_name": "X", "text": text})
    law = _form_by_type(_off(gear))
    assert sum(law.values()) == pytest.approx(5.0 * sum(plain[e] for e in ("fire", "cold", "lightning")) / 3.0,
                                              rel=1e-6)


def test_conversion_positive_control_and_ignored_under_trinity():
    flat = _flat(fire=100, cold=100, lightning=100)
    no_conv = _off(_gear(**flat))["total_dps_vs_target"]
    conv = _off(_gear(**flat, physical_convert_to_fire=1.0))["total_dps_vs_target"]
    assert conv != pytest.approx(no_conv, rel=1e-6)           # the key is real: conversion changes DPS normally
    a = _off(_gear(**flat, trinity_hit_multiplier=5.0))["total_dps_vs_target"]
    b = _off(_gear(**flat, trinity_hit_multiplier=5.0, physical_convert_to_fire=1.0))["total_dps_vs_target"]
    assert b == pytest.approx(a, rel=1e-9)


def test_zero_flat_zeroes_every_element_with_positive_control():
    flat = _flat(fire=100, lightning=100)
    assert _off(_gear(**flat))["total_dps"] > 0
    by = _form_by_type(_off(_gear(**flat, trinity_hit_multiplier=5.0)))
    assert by.get("fire", 0.0) == 0.0 and by.get("lightning", 0.0) == 0.0 and by.get("cold", 0.0) == 0.0


def test_multiplier_does_not_stack_past_edict():
    flat = _flat(fire=100, cold=100, lightning=100)
    a = _off(_gear(**flat, trinity_hit_multiplier=6.0))["total_dps"]
    b = _off(_gear(**flat, trinity_hit_multiplier=11.0))["total_dps"]
    assert b == pytest.approx(a, rel=1e-9)


def test_only_deal_type_loses_other_picks():
    flat = _flat(fire=100, cold=100, lightning=100)
    both = _form_by_type(_off(_gear(**flat, trinity_hit_multiplier=5.0)))
    only = _form_by_type(_off(_gear(**flat, trinity_hit_multiplier=5.0, can_only_deal_fire=1.0)))
    assert only["fire"] == pytest.approx(both["fire"], rel=1e-9)     # fire keeps just its own 1/3 share
    assert only.get("cold", 0.0) == 0.0 and only.get("lightning", 0.0) == 0.0


def test_hit_min_max_are_roll_if_picked():
    flat = _flat(fire=100, cold=100, lightning=100)
    base = _off(_gear(**flat))["hit_forms"][0]["hit_min_by_type"]["fire"]
    law = _off(_gear(**flat, trinity_hit_multiplier=5.0))["hit_forms"][0]["hit_min_by_type"]["fire"]
    assert law == pytest.approx(5.0 * base, rel=1e-6)


def test_pen_negative_floors_at_zero_and_raised_cap_counts():
    g = _gear(elemental_pen_from_min_res=1.0, fire_resistance=-0.2, cold_resistance=0.6, lightning_resistance=0.6)
    assert _elemental_pen(g) == pytest.approx(0.0)
    g2 = _gear(elemental_pen_from_min_res=1.0, fire_resistance=0.8, cold_resistance=0.8, lightning_resistance=0.8,
               max_elemental_resistance_inc=0.15)
    assert _elemental_pen(g2) == pytest.approx(0.75)
    g3 = _gear(elemental_pen_from_min_res=1.0, fire_resistance=0.8, cold_resistance=0.8, lightning_resistance=0.8,
               cold_resistance_max_inc=-0.1)
    assert _elemental_pen(g3) == pytest.approx(0.50)
