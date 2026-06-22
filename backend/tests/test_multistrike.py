"""Multistrike system (attack skills) — the offense DPS multiplier from auto-repeats with increasing damage.

Model (owner-validated vs an in-game lvl-85 dummy test: ×1.65 model vs ×1.73 measured, ~5% noise):
  multiplier = E[chain damage] / (aps × E[chain time]) = E[f(L)] / (1 + chance/s)
where f(L) = L + inc·(init·L + L(L-1)/2) (+ Cat-Dive boost), inc = base × (1 + additional), and repeats get
+20% INCREASED attack speed (s). Worked example (1.16 chance, 0.82 increment, no other AS): ×1.6487.
"""
import pytest
from server import engine_stats, EngineStatsRequest
from tests.mock_build import make_request, weapon

WEAPON = [weapon("weapon1", "Blade", 350, 350, 1.5, 500)]   # 350-350 phys, 1.5 aps, 5% crit
MS_SUP = [{"item_id": "multistrike", "slot": 1, "level": 16, "rank": 1, "enabled": True}]


def _gear(**stats):
    return WEAPON + [{"item_name": "X", "contributions": [
        {"stat": k, "display_value": v, "unit": "", "slot": "ring", "item_name": "X", "text": f"+{v} {k}"}
        for k, v in stats.items()]}]


def _off(skill="berserking_blade", gear=None, sups=None):
    r = engine_stats(EngineStatsRequest(**make_request(skill, 16, gear=gear or WEAPON, attached_supports=sups)))
    return (r if isinstance(r, dict) else r.model_dump())["offense"]


def test_support_grants_chance_and_increment():
    o = _off(sups=MS_SUP)
    assert o["multistrike_chance"] == pytest.approx(1.16, abs=0.001)      # L16 progression (101→116)
    assert o["multistrike_increment"] == pytest.approx(0.27, abs=0.001)   # support base increasing damage
    assert o["multistrike_max_count"] == 3                                # 1 + 1 guaranteed + 1 possible


def test_multiplier_matches_worked_example():
    # inc 0.82 = support 0.27 + 0.55 (Quick Advancement, here via gear), chance 1.16, no other AS → ×1.6487.
    o = _off(gear=_gear(multistrike_increasing_dmg_inc=0.55), sups=MS_SUP)
    assert o["multistrike_increment"] == pytest.approx(0.82, abs=0.001)
    assert o["multistrike_mult"] == pytest.approx(1.6487, rel=0.005)


def test_multiplier_scales_total_dps():
    base, ms = _off(), _off(sups=MS_SUP)
    assert ms["total_dps_vs_target"] == pytest.approx(base["total_dps_vs_target"] * ms["multistrike_mult"], rel=1e-6)
    assert base["multistrike_mult"] == 1.0                                # no chance → no multistrike


def test_initial_count_prestacks_without_extra_attacks():
    a = _off(sups=MS_SUP)
    b = _off(gear=_gear(initial_multistrike_count_flat=2), sups=MS_SUP)
    assert b["multistrike_chance"] == a["multistrike_chance"]             # no extra attacks
    assert b["multistrike_max_count"] == a["multistrike_max_count"]
    assert b["multistrike_mult"] > a["multistrike_mult"] * 1.3            # pre-stacked increment → big jump


def test_additional_increment_multiplies_base():
    a = _off(sups=MS_SUP)
    b = _off(gear=_gear(multistrike_increasing_dmg_additional=1.0), sups=MS_SUP)   # +100% additional → ×2 increment
    assert b["multistrike_increment"] == pytest.approx(a["multistrike_increment"] * 2.0, rel=0.01)
    assert b["multistrike_mult"] > a["multistrike_mult"]


def test_cat_dive_max_count_proc_raises_mult():
    a = _off(sups=MS_SUP)
    b = _off(gear=_gear(multistrike_max_count_proc_chance=0.5), sups=MS_SUP)
    assert b["multistrike_mult"] > a["multistrike_mult"]                  # boosts pre-max hits toward max count


def test_spell_skill_ignores_multistrike():
    o = _off(skill="chain_lightning", gear=_gear(multistrike_chance=2.0))
    assert o["multistrike_mult"] == 1.0
    assert o["multistrike_chance"] == 0.0
