"""Prism (Inverse Image) reflected-copy DPS resolution: a reflected cell copies the point-reflected source node's
effect, scaled by the prism's roll for the SOURCE node's tier × allocated points. Plan 2 (engine DPS)."""
import pytest
from engine.node_resolver import resolve_nodes
from server import _parse_custom_mod_text, _translate_condition_expr, engine_stats, EngineStatsRequest
from tests.mock_build import make_request, weapon

# Minimal tree (key = _tree_slug("Test Tree") = "test_tree") with one node of each tier at known positions.
_TREE = {"nodes": [
    {"id": "n_micro", "column": 0, "row": 0, "node_type": "Micro Talent", "effects": ["+10 % Attack Damage"]},
    {"id": "n_medium", "column": 1, "row": 0, "node_type": "Medium Talent", "effects": ["+20 % Spell Damage"]},
    {"id": "n_legend", "column": 0, "row": 1, "node_type": "Legendary Medium Talent", "effects": ["+5 % additional Attack Damage"]},
]}
_TREES = {"test_tree": _TREE}
# Reflected cell → source = mirror(cell) = (6-col, 4-row): micro(0,0)→cell(6,4); medium(1,0)→cell(5,4); legend(0,1)→cell(6,3)


def _resolve(prism):
    return resolve_nodes([], [], _TREES, _parse_custom_mod_text, _translate_condition_expr, prisms=[prism])[0]


def _amt(contribs, key):
    return sum(c["amount"] for c in contribs if c["stat_key"] == key)


def _prism(rolls, box):
    return {"kind": "inverse_image", "treeName": "Test Tree", "rolls": rolls, "boxAllocations": box}


def test_reflected_copy_scales_by_roll_and_points():
    c = _resolve(_prism({"micro": 70, "medium": -100, "legendary": -100}, {"6,4": 3}))
    assert _amt(c, "attack_dmg_inc") == pytest.approx(0.10 * 3 * 1.70)   # +10% × 3 pts × (1+0.70)


def test_tier_roll_applies_by_source_node_type():
    c = _resolve(_prism({"micro": -100, "medium": 50, "legendary": -100}, {"5,4": 2}))   # medium source → medium roll
    assert _amt(c, "spell_dmg_inc") == pytest.approx(0.20 * 2 * 1.50)


def test_legendary_roll():
    c = _resolve(_prism({"micro": -100, "medium": -100, "legendary": 50}, {"6,3": 1}))
    assert _amt(c, "attack_dmg_additional") == pytest.approx(0.05 * 1.50)


def test_roll_minus_100_zeroes_the_tier():
    assert _resolve(_prism({"micro": -100, "medium": -100, "legendary": -100}, {"6,4": 3})) == []


def test_distinct_pooling_id():
    c = _resolve(_prism({"micro": 0, "medium": -100, "legendary": -100}, {"6,4": 1}))   # +0% → ×1.0, still present
    assert any("::refl::6,4" in x["text"] for x in c)
    assert _amt(c, "attack_dmg_inc") == pytest.approx(0.10)


def test_missing_source_and_non_inverse_image_ignored():
    assert _resolve(_prism({"micro": 100}, {"0,0": 3})) == []           # cell (0,0) sources (6,4) = empty
    assert resolve_nodes([], [], _TREES, _parse_custom_mod_text, _translate_condition_expr,
                         prisms=[{"kind": "ethereal_prism", "treeName": "Test Tree", "rolls": {},
                                  "boxAllocations": {"6,4": 3}}])[0] == []


# ── Integration: a prism raises a real attack build's DPS; no prism = unchanged ──
def test_prism_raises_attack_dps():
    W = [weapon("weapon1", "Blade", 350, 350, 1.5, 500)]
    base = make_request("berserking_blade", 16, gear=W)
    d0 = engine_stats(EngineStatsRequest(**base))["offense"]["total_dps_vs_target"]
    # Bladerunner (0,0) = "+9% Attack Damage" (Micro); reflected cell (6,4); micro +100% → ×2.
    prism = {"kind": "inverse_image", "treeName": "Bladerunner",
             "rolls": {"micro": 100, "medium": -100, "legendary": -100}, "boxAllocations": {"6,4": 3}}
    d1 = engine_stats(EngineStatsRequest(**{**base, "prisms": [prism]}))["offense"]["total_dps_vs_target"]
    assert d1 > d0
