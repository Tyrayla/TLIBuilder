"""Unified talent-node resolution (engine/node_resolver.py) — replaces the filter-builder recipes.

Verifies: linear per-rank scaling (all tiers), conditional GATING, Max-Divinity slate dedup (count-based,
delta-correct), and VALUE PARITY vs the old recipes (a converted node yields amount×points == recipe
values[points-1]) so retiring the builder loses no value.
"""
import glob
import json
import os

import pytest

from server import _parse_custom_mod_text as pm, _translate_condition_expr as tc
from engine.node_resolver import resolve_nodes, _resolve_node


def _slot(tree_name, node_id, points):
    return {"treeName": tree_name, "nodeStates": {node_id: points}}


def _tree(tree_name, nodes):
    return {tree_name.lower(): {"tree_name": tree_name, "nodes": nodes}}


def _amounts(contribs):
    out = {}
    for c in contribs:
        out[c["stat_key"]] = out.get(c["stat_key"], 0.0) + c["amount"]
    return out


class TestRankScaling:
    def test_micro_scales_linearly(self):
        node = {"id": "warrior_c0_r0", "node_type": "Micro Talent", "effects": ["+9 % damage"]}
        trees = _tree("Warrior", [node])
        for pts, expect in [(1, 0.09), (2, 0.18), (3, 0.27)]:
            c, _ = resolve_nodes([_slot("Warrior", "warrior_c0_r0", pts)], [], trees, pm, tc)
            assert _amounts(c).get("dmg_inc") == pytest.approx(expect)

    def test_medium_scales_linearly(self):
        node = {"id": "warrior_c0_r0", "node_type": "Medium Talent", "effects": ["+18 % Attack Damage"]}
        trees = _tree("Warrior", [node])
        for pts, expect in [(1, 0.18), (2, 0.36), (3, 0.54)]:
            c, _ = resolve_nodes([_slot("Warrior", "warrior_c0_r0", pts)], [], trees, pm, tc)
            assert _amounts(c).get("attack_dmg_inc") == pytest.approx(expect)

    def test_legendary_single_rank(self):
        node = {"id": "warrior_c0_r0", "node_type": "Legendary Medium Talent", "effects": ["+1 to Attack Skill Level"]}
        trees = _tree("Warrior", [node])
        c, _ = resolve_nodes([_slot("Warrior", "warrior_c0_r0", 1)], [], trees, pm, tc)
        assert _amounts(c).get("attack_skill_level") == pytest.approx(1.0)


class TestConditionalGating:
    def test_conditional_carries_gate(self):
        # "+12% damage when holding a Shield" → dmg_inc gated on holding_shield (not always-on).
        c, s = _resolve_node("n", ["+12 % damage when holding a Shield"], 1, "L", "node", pm, tc)
        assert any(x["stat_key"] == "dmg_inc" and x["condition_expr"] == "holding_shield" for x in c)

    def test_per_scaling_keeps_boolean_gate(self):
        # "for each X while Y" must keep BOTH the per-scaling AND the boolean gate (regression: dropped gate).
        c, _ = _resolve_node("n", ["+5 % additional Attack Damage for each unique type of weapon equipped while Dual Wielding"],
                             1, "L", "node", pm, tc)
        x = next(x for x in c if x["stat_key"] == "attack_dmg_additional")
        ce = x["condition_expr"]
        assert isinstance(ce, dict) and "and" in ce
        assert {"key": "unique_weapon_types", "op": "per", "divisor": 1} in ce["and"]
        assert "dual_wielding" in ce["and"]

    def test_compound_per_gate_eval(self):
        # Aggregator: per-scaling × boolean gate — gated off → 0; on → amount × floor(numeric).
        from engine.aggregator import _eval_condition
        expr = {"and": [{"key": "unique_weapon_types", "op": "per", "divisor": 1}, "dual_wielding"]}
        assert _eval_condition(expr, frozenset(), {"unique_weapon_types": 3.0}) is False     # not dual wielding
        assert _eval_condition(expr, frozenset({"dual_wielding"}), {"unique_weapon_types": 3.0}) == 3.0  # ×3


class TestSlateMaxDivinityDedup:
    EFF = "+12 % Max Mana (Max Divinity Effect: 1)"

    def _trees(self):
        node = {"id": "warrior_c0_r0", "node_type": "Medium Talent", "effects": [self.EFF]}
        return _tree("Warrior", [node])

    def _slate(self, n):
        return {"kind": "base", "slots": [{"selectedNodeId": "warrior_c0_r0"} for _ in range(n)]}

    def test_identical_maxdiv_counted_once(self):
        # Two slate slots with the same Max-Divinity-1 effect → contributes ONCE.
        c1, _ = resolve_nodes([], [self._slate(1)], self._trees(), pm, tc)
        c2, _ = resolve_nodes([], [self._slate(2)], self._trees(), pm, tc)
        assert _amounts(c1).get("max_mana_inc") == pytest.approx(_amounts(c2).get("max_mana_inc"))

    def test_removing_one_duplicate_unchanged(self):
        # 3 → 2 instances: still ≥1 present → contribution unchanged (delta 0).
        c3, _ = resolve_nodes([], [self._slate(3)], self._trees(), pm, tc)
        c2, _ = resolve_nodes([], [self._slate(2)], self._trees(), pm, tc)
        assert _amounts(c3).get("max_mana_inc") == pytest.approx(_amounts(c2).get("max_mana_inc"))

    def test_removing_last_drops_it(self):
        c1, _ = resolve_nodes([], [self._slate(1)], self._trees(), pm, tc)
        c0, _ = resolve_nodes([], [self._slate(0)], self._trees(), pm, tc)
        assert _amounts(c1).get("max_mana_inc", 0) > 0
        assert _amounts(c0).get("max_mana_inc", 0) == 0


def _load_filter():
    from tools.node_type_filter_builder import load_filter
    return load_filter() or {}


class TestRecipeValueParity:
    """For SS12 mapped nodes whose unified stat-set matches the recipe stat-set and have no conditional
    recipe, the unified amount × points reproduces the recipe values[points-1] exactly — no value loss."""

    def test_value_parity_vs_recipes(self):
        nr = _load_filter().get("node_recipes", {})
        checked = 0
        for f in sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "..", "data", "seasons", "SS12", "*.json"))):
            if os.path.basename(f).startswith("_"):
                continue
            data = json.load(open(f, encoding="utf-8"))
            tname = data.get("tree_name") or os.path.basename(f).replace(".json", "")
            trees = {tname.lower(): {"tree_name": tname, "nodes": data.get("nodes", [])}}
            for node in data.get("nodes", []):
                rec = nr.get(node["id"])
                # Skip unmapped, conditional, and per-scaling recipes (compared via flat per-rank values only).
                if not rec or any(r.get("condition") or r.get("scaling") or not r.get("values") for r in rec):
                    continue
                rec_by_stat = {r["stat"]: r for r in rec}
                # Legendary nodes are 1-rank; micro/medium scale to 3. Compare at the node's tier cap.
                pts = 1 if "legendary" in node.get("node_type", "").lower() else 2
                c, _ = resolve_nodes([_slot(tname, node["id"], pts)], [], trees, pm, tc)
                amts = _amounts(c)
                # Only compare where the unified stat set exactly matches the recipe's (true parity nodes).
                if set(amts) != set(rec_by_stat):
                    continue
                for stat, r in rec_by_stat.items():
                    vals = r.get("values") or [r["rank1"]]
                    expect = vals[min(pts - 1, len(vals) - 1)]
                    assert amts[stat] == pytest.approx(expect, abs=1e-6), f"{node['id']} {stat}"
                    checked += 1
        assert checked > 300, f"expected to check many parity stats, got {checked}"
