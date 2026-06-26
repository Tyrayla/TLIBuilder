"""Chromatic Shot (chromatic_shot) — a Spell with Compulsory Damage Type Conversion (each cast deals ONE random/
rotated element; ALL added flat folds into base BEFORE conversion; only the final element's increased/additional
apply) fired as 3 shotgunning projectiles. Plus its canvas supports Lightchaser + Splendor.

Owner-confirmed model: headline = expected average across Fire/Cold/Lightning; shotgun first 100% + each subsequent
30% (falloff 0.70) capped at "shots on target" (default 7, all under Lightchaser/tangle); added flat of EVERY type
folds in equally.
"""
import pytest
from engine.skill_resolver import resolve_skill
from server import engine_stats, EngineStatsRequest
from tests.mock_build import make_request

LC = "chromatic_shot_lightchaser_magnificent"
SP = "chromatic_shot_splendor_noble"


def _skill_data():
    import json, os
    d = json.load(open(os.path.join(os.path.dirname(__file__), "..", "..", "data", "seasons", "SS12", "_skills.json"), encoding="utf-8"))
    items = d if isinstance(d, list) else d.get("skills") or d.get("items") or []
    return next(x for x in items if x.get("item_id") == "chromatic_shot")


def _flat_item(name, pairs):
    """A gear item injecting arbitrary stat contributions (e.g. added spell flat, increased damage)."""
    return {"item_name": name, "contributions": [
        {"stat": k, "display_value": v, "unit": "", "slot": "ring1", "item_name": name, "text": f"{name}:{k}"}
        for k, v in pairs]}


def _resp(gear=None, supports=None, conds=None):
    req = make_request("chromatic_shot", 20, attached_supports=supports or [], gear=gear or [],
                       extra_conditions=conds or {})
    r = engine_stats(EngineStatsRequest(**req))
    return r if isinstance(r, dict) else r.model_dump()


def _off(gear=None, supports=None, conds=None):
    return _resp(gear=gear, supports=supports, conds=conds)["offense"]


# ── Resolver ──────────────────────────────────────────────────────────────────
def test_resolver_fields():
    r = resolve_skill(_skill_data())
    assert r.is_spell and r.supported
    assert r.compulsory_elements == ["fire", "cold", "lightning"]
    assert r.base_flat_by_level[1] == (8.0, 14.0) and r.base_flat_by_level[20] == (592.0, 1100.0)
    assert r.added_dmg_effectiveness == pytest.approx(1.57)
    assert r.base_cast_time == pytest.approx(0.65) and r.mana_cost == pytest.approx(8.0)
    assert r.main_stat == ["strength", "dexterity", "intelligence"]
    f = r.hit_forms_by_level[20][0]
    assert f.hit_count == 3 and f.shotgun_falloff == pytest.approx(0.70) and f.scales_with_projectiles


# ── Compulsory conversion ───────────────────────────────────────────────────────
def test_expected_is_average_of_three_elements():
    off = _off()
    cb = off["compulsory_breakdown"]
    assert set(cb) == {"fire", "cold", "lightning"}
    # No per-element mods/resist differences → all three identical, headline = that value.
    avgs = [cb[e]["avg_pre_crit"] for e in cb]
    assert max(avgs) == pytest.approx(min(avgs))


def test_all_added_flat_folds_in_regardless_of_type():
    """Added Fire / Cold / Lightning / Physical flat all raise the skill identically (folded before conversion)."""
    base = _off()["total_dps"]
    fire = _off(gear=[_flat_item("R", [("fire_spell_dmg_flat_min", 200), ("fire_spell_dmg_flat_max", 200)])])["total_dps"]
    cold = _off(gear=[_flat_item("R", [("cold_spell_dmg_flat_min", 200), ("cold_spell_dmg_flat_max", 200)])])["total_dps"]
    phys = _off(gear=[_flat_item("R", [("physical_spell_dmg_flat_min", 200), ("physical_spell_dmg_flat_max", 200)])])["total_dps"]
    assert fire > base
    assert fire == pytest.approx(cold) == pytest.approx(phys)   # type-agnostic fold


def test_per_element_uses_only_final_type_increased():
    """+increased Fire Damage raises ONLY the fire element, not cold/lightning."""
    off = _off(gear=[_flat_item("R", [("fire_dmg_inc", 1.0)])])  # +100% increased Fire
    cb = off["compulsory_breakdown"]
    assert cb["fire"]["avg_pre_crit"] > cb["cold"]["avg_pre_crit"]
    assert cb["cold"]["avg_pre_crit"] == pytest.approx(cb["lightning"]["avg_pre_crit"])


# ── Shotgun / shots-on-target ───────────────────────────────────────────────────
def test_shotgun_default_three_projectiles():
    """Base 3 projectiles, shots default 7 → all 3 land → mult 1 + 2×0.30 = 1.6."""
    f = _off()["hit_forms"][0]
    assert f["hits_per_fire"] == 3 and f["shotgun_mult"] == pytest.approx(1.6)


def test_shots_on_target_caps_the_shotgun():
    """+6 Projectile Quantity → 9 fired, but only 'shots on target' (default 7) land → 1 + 6×0.30 = 2.8."""
    off = _off(gear=[_flat_item("R", [("projectile_quantity_flat", 6)])])
    f = off["hit_forms"][0]
    assert off["projectile_count"] == 9 and f["hits_per_fire"] == 7
    assert f["shotgun_mult"] == pytest.approx(1.0 + 6 * 0.30)


# ── Lightchaser ──────────────────────────────────────────────────────────────────
def _sup(item_id, rank=5):
    return [{"item_id": item_id, "slot": 1, "level": 20, "rank": rank, "enabled": True}]


def test_lightchaser_raises_dps_and_all_projectiles_land():
    base = _off(gear=[_flat_item("R", [("projectile_quantity_flat", 6)])])               # 9 fired, 7 land
    lc = _off(gear=[_flat_item("R", [("projectile_quantity_flat", 6)])], supports=_sup(LC))  # homing → all 9 land
    assert lc["hit_forms"][0]["hits_per_fire"] == 9
    assert lc["total_dps"] > base["total_dps"]


def test_lightchaser_main_stat_ratio_boost():
    """Lightchaser raises the main-attribute damage ratio ×1.25 (0.5%/pt → 0.625%/pt). With 500 attributes the
    reported bonus goes +250% (×3.5) → +312.5% (×4.125), and the source line then matches the total."""
    attrs = [_flat_item("A", [("dexterity", 500)])]
    base = _off(gear=attrs)
    lc = _off(gear=attrs, supports=_sup(LC))
    assert base["main_stat_damage_bonus"] == pytest.approx(2.5)
    assert lc["main_stat_damage_bonus"] == pytest.approx(3.125)   # 2.5 × 1.25


def test_zero_main_stat_gives_no_ratio_damage():
    """With no attributes the main-stat bonus is 0 even with Lightchaser (the ratio multiplies a 0 bonus)."""
    assert _off()["main_stat_damage_bonus"] == 0.0
    assert _off(supports=_sup(LC))["main_stat_damage_bonus"] == 0.0


def test_per_type_increased_shows_in_breakdown():
    """A +Fire Damage mod surfaces in the Fire column's increased (not cold/lightning) for the breakdown table."""
    off = _off(gear=[_flat_item("R", [("fire_dmg_inc", 0.5)])])
    assert off["type_inc"]["fire"] == pytest.approx(0.5)
    assert off["type_inc"]["cold"] == pytest.approx(0.0) == off["type_inc"]["lightning"]


# ── Splendor ──────────────────────────────────────────────────────────────────
def test_projectile_hits_max_tracks_projectile_count():
    """Projectile Hits (shots-on-target) caps at the build's projectile count — 3 by default, more with
    +Projectile Quantity — not an artificial constant."""
    base = _resp()["condition_maximums"]["chromatic_shots_on_target"]
    more = _resp(gear=[_flat_item("R", [("projectile_quantity_flat", 6)])])["condition_maximums"]["chromatic_shots_on_target"]
    assert base == pytest.approx(3.0)
    assert more == pytest.approx(9.0)


def test_splendor_surfaces_auto_conditions_with_source():
    """Splendor's auto-inflicted ailments come back as auto_conditions (so the Config UI can show them
    checked + locked with the source named), including the engine-derived Frostbite Rating of 10."""
    none = _resp().get("auto_conditions") or {}
    assert not none                                              # no auto conditions without an inflict source
    auto = _resp(supports=_sup(SP))["auto_conditions"]
    assert set(auto) == {"enemy_numbed", "enemy_frostbitten", "enemy_ignited", "frostbite_rating", "numbed_stacks"}
    assert all(auto[k]["source"] == "Chromatic Shot: Splendor" for k in auto)
    assert auto["enemy_numbed"]["value"] is True
    assert auto["frostbite_rating"]["value"] == pytest.approx(10.0)
    assert auto["numbed_stacks"]["value"] == pytest.approx(1.0)   # inflicting Numbed applies ≥1 stack


def test_numbed_stacks_zero_opts_out_of_numbed():
    """A user-set numbed_stacks=0 overrides Splendor's inflict: Numbed turns off (dropping the all-three-ailment
    Hit Damage gate → lower DPS), but the auto intent (1) is still reported so the cleared field can restore it."""
    base = _resp(supports=_sup(SP))
    off = _resp(supports=_sup(SP), conds={"numbed_stacks": 0})
    assert "enemy_numbed" not in off["auto_conditions"]            # opted out → not auto-active
    assert off["auto_conditions"]["numbed_stacks"]["value"] == pytest.approx(1.0)  # intent still reported
    assert off["offense"]["total_dps"] < base["offense"]["total_dps"]              # Splendor gate dropped


def test_splendor_auto_inflicts_three_ailments_and_adds_hit_damage():
    base = _off()
    sp = _off(supports=_sup(SP))
    assert sp["total_dps"] > base["total_dps"]                       # universal +20% + ailment vuln + gated hit dmg
    # Splendor's +hit damage is gated on all three ailments, which it auto-applies → per-element differs from base.
    assert sp["compulsory_breakdown"]["cold"]["avg_pre_crit"] > base["compulsory_breakdown"]["cold"]["avg_pre_crit"]
