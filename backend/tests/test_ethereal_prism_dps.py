"""Ethereal Prism engine DPS (Plan B): area-bonus per-point + Phantasmagoria scaled value (node_resolver), and
core-talent replace/add resolution (prism_core_talents): all-or-nothing, 24-pt gate, the 3 modeled talents, NYI."""
import pytest
from engine.node_resolver import resolve_nodes
from engine.prism_core_talents import resolve_prism_core_talents, CORE_TALENT_THRESHOLD
from server import _parse_custom_mod_text as parse, _translate_condition_expr as tcond

_TREE = {"nodes": [
    {"id": "mic", "column": 1, "row": 1, "node_type": "Micro Talent", "effects": ["+5 % Attack Damage"]},
    {"id": "med", "column": 1, "row": 2, "node_type": "Medium Talent", "effects": ["+10 % Spell Damage"]},
]}
_TREES = {"test_tree": _TREE}


def _amt(contribs, key, only_area=False):
    return round(sum(c["amount"] for c in contribs
                     if c["stat_key"] == key and (("::ether::" in c["text"]) or not only_area)), 6)


def _eth_prism(middle, **eth):
    return {"kind": "ethereal_prism", "treeName": "Test Tree", "anchorCol": 1, "anchorRow": 1,
            "ethereal": {"shortName": "Foo", "boxCols": 3, "boxRows": 3, "middle": middle, **eth}}


# ── Area bonus (per point, by tier) ──────────────────────────────────────────
def test_area_bonus_scales_per_point_for_matching_tier():
    slot = {"treeName": "Test Tree", "nodeStates": {"mic": 3, "med": 2}}
    p = _eth_prism("All Micro Talent within the area also gain: +6 % Attack Damage")
    c, _ = resolve_nodes([slot], [], _TREES, parse, tcond, prisms=[p])
    assert _amt(c, "attack_dmg_inc", only_area=True) == pytest.approx(0.06 * 3)   # per point: 3/3 micro → +18%


def test_area_bonus_only_hits_its_tier():
    slot = {"treeName": "Test Tree", "nodeStates": {"mic": 3, "med": 2}}
    p = _eth_prism("All Medium Talent within the area also gain: +6 % Attack Damage")
    c, _ = resolve_nodes([slot], [], _TREES, parse, tcond, prisms=[p])
    assert _amt(c, "attack_dmg_inc", only_area=True) == pytest.approx(0.06 * 2)   # only the 2-pt medium node


def test_area_bonus_unallocated_node_contributes_nothing():
    slot = {"treeName": "Test Tree", "nodeStates": {"med": 2}}                    # mic not allocated
    p = _eth_prism("All Micro Talent within the area also gain: +6 % Attack Damage")
    c, _ = resolve_nodes([slot], [], _TREES, parse, tcond, prisms=[p])
    assert _amt(c, "attack_dmg_inc", only_area=True) == 0.0


def test_phantasmagoria_scaled_value_flows():
    slot = {"treeName": "Test Tree", "nodeStates": {"mic": 1}}
    p = _eth_prism("All Micro Talent within the area also gain: 10.5 % Aura Effect")  # ×1.75 baked value
    c, _ = resolve_nodes([slot], [], _TREES, parse, tcond, prisms=[p])
    assert _amt(c, "aura_effect_inc", only_area=True) == pytest.approx(0.105)


# ── Core-talent replace / add ────────────────────────────────────────────────
def _slot(points):  # a tree with `points` total allocated
    return {"treeName": "Test Tree", "nodeStates": {"a": points}}


def _replace(short, advanced=None):
    return {"kind": "ethereal_prism", "treeName": "Test Tree", "anchorCol": 0, "anchorRow": 0,
            "ethereal": {"shortName": short, "implicit": f"Replaces the Core Talent on the X Advanced Talent Panel with {short}",
                         "advanced": advanced}}


_DESC = {"Effortless Command": "+1000 Max Energy",
         "Circle of Life": "Gains Growth equal to 80% of the nearest Spirit Magus every 1s"}


def test_effortless_command_models_and_is_threshold_gated():
    # < 24 pts → locked, no contribution
    c, _, st, _ = resolve_prism_core_talents([_replace("Effortless Command")], [_slot(10)], _DESC, parse, tcond)
    assert c == [] and any(s["kind"] == "locked" for s in st)
    # >= 24 pts → +1000 Max Energy
    c, _, st, repl = resolve_prism_core_talents([_replace("Effortless Command")], [_slot(24)], _DESC, parse, tcond)
    assert sum(x["amount"] for x in c if x["stat_key"] == "max_energy_flat") == pytest.approx(1000)
    assert "test_tree" in repl                                     # pure replace supersedes native core


def test_unmatched_valor_sets_condition():
    c, cond, st, _ = resolve_prism_core_talents([_replace("Unmatched Valor")], [_slot(24)], _DESC, parse, tcond)
    assert cond.get("unmatched_valor") is True
    assert any(s["resolved"] for s in st)


def test_spell_ripple_emits_fraction():
    c, _, _, _ = resolve_prism_core_talents([_replace("Spell Ripple")], [_slot(24)], _DESC, parse, tcond)
    assert sum(x["amount"] for x in c if x["stat_key"] == "spell_ripple_fraction") == pytest.approx(0.75)


def test_unmodeled_talent_is_nyi_with_zero_contribution():
    c, cond, st, repl = resolve_prism_core_talents([_replace("Circle of Life")], [_slot(24)], _DESC, parse, tcond)
    assert c == [] and cond == {}                                  # all-or-nothing: nothing emitted
    assert repl == set()                                          # NYI does NOT suppress native core
    assert any(s["kind"] == "unresolved" for s in st)             # badged NYI
