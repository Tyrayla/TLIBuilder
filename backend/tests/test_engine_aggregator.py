"""
Tests: engine/aggregator.py — stat collection from node states and slates.
Scope: aggregation logic only; uses synthetic season_trees and filter_data dicts
instead of real file I/O.
"""
import pytest
from engine.models import BuildInput, BuildSource, SkillConfig, EnemyConfig
from engine.aggregator import aggregate, _apply_node_recipes, _tree_slug_from_node_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build(slots=None, slates=None, season="test") -> BuildInput:
    return BuildInput(
        slots=slots or [],
        slates=slates or [],
        skill=SkillConfig("t", "attack", ["attack"], ["physical"], 1),
        enemy=EnemyConfig(),
        season=season,
    )


def _season_tree(tree_name: str, nodes: list) -> dict:
    return {"tree_name": tree_name, "nodes": nodes}


def _node(node_id: str, node_type: str, max_points: int = 3) -> dict:
    return {"id": node_id, "node_type": node_type, "max_points": max_points}


def _filter(tree_name: str, node_type: str, stat: str, values: list) -> dict:
    return {
        "recipes": {
            tree_name: {
                node_type: [{"stat": stat, "rank1": values[0], "values": values}]
            }
        }
    }


# ---------------------------------------------------------------------------
# _tree_slug_from_node_id
# ---------------------------------------------------------------------------

class TestSlugExtraction:
    def test_valid_node_id(self):
        assert _tree_slug_from_node_id("warrior_c2_r5") == "warrior"

    def test_multi_segment_slug(self):
        assert _tree_slug_from_node_id("god_of_war_c1_r3") == "god_of_war"

    def test_invalid_format_returns_none(self):
        assert _tree_slug_from_node_id("invalid") is None
        assert _tree_slug_from_node_id("") is None


# ---------------------------------------------------------------------------
# _apply_node_recipes
# ---------------------------------------------------------------------------

class TestApplyNodeRecipes:
    def test_rank_1_applies_first_value(self):
        source = BuildSource()
        recipes = {"Warrior": {"micro": [{"stat": "dmg_inc", "rank1": 0.09, "values": [0.09, 0.18, 0.27]}]}}
        _apply_node_recipes(source, "Warrior", "w_c0_r0", 1, 3, "micro", recipes)
        assert source.total("dmg_inc") == pytest.approx(0.09)

    def test_rank_2_applies_second_value(self):
        source = BuildSource()
        recipes = {"Warrior": {"micro": [{"stat": "dmg_inc", "rank1": 0.09, "values": [0.09, 0.18, 0.27]}]}}
        _apply_node_recipes(source, "Warrior", "w_c0_r0", 2, 3, "micro", recipes)
        assert source.total("dmg_inc") == pytest.approx(0.18)

    def test_rank_clamped_to_values_length(self):
        source = BuildSource()
        recipes = {"Warrior": {"micro": [{"stat": "dmg_inc", "rank1": 0.09, "values": [0.09, 0.18, 0.27]}]}}
        _apply_node_recipes(source, "Warrior", "w_c0_r0", 99, 3, "micro", recipes)
        assert source.total("dmg_inc") == pytest.approx(0.27)

    def test_missing_tree_is_skipped(self):
        source = BuildSource()
        recipes = {}
        _apply_node_recipes(source, "Warrior", "w_c0_r0", 1, 1, "micro", recipes)
        assert source.total("dmg_inc") == 0.0

    def test_missing_node_type_is_skipped(self):
        source = BuildSource()
        recipes = {"Warrior": {}}
        _apply_node_recipes(source, "Warrior", "w_c0_r0", 1, 1, "legendary_medium", recipes)
        assert source.total("dmg_inc") == 0.0

    def test_multiple_stats_from_same_node(self):
        source = BuildSource()
        recipes = {
            "Warrior": {
                "micro": [
                    {"stat": "dmg_inc", "rank1": 0.09, "values": [0.09, 0.18, 0.27]},
                    {"stat": "strength", "rank1": 5.0, "values": [5.0, 10.0, 15.0]},
                ]
            }
        }
        _apply_node_recipes(source, "Warrior", "w_c0_r0", 1, 3, "micro", recipes)
        assert source.total("dmg_inc") == pytest.approx(0.09)
        assert source.total("strength") == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# aggregate — talent slots
# ---------------------------------------------------------------------------

class TestAggregateSlots:
    def test_allocated_node_contributes_stat(self):
        season_trees = {
            "warrior": _season_tree("Warrior", [_node("warrior_c0_r0", "micro", 3)])
        }
        filter_data = _filter("Warrior", "micro", "dmg_inc", [0.09, 0.18, 0.27])
        build = _build(
            slots=[{"treeName": "Warrior", "nodeStates": {"warrior_c0_r0": 2}}]
        )
        source = aggregate(build, season_trees, filter_data)
        assert source.total("dmg_inc") == pytest.approx(0.18)

    def test_zero_point_node_is_skipped(self):
        season_trees = {
            "warrior": _season_tree("Warrior", [_node("warrior_c0_r0", "micro", 3)])
        }
        filter_data = _filter("Warrior", "micro", "dmg_inc", [0.09, 0.18, 0.27])
        build = _build(
            slots=[{"treeName": "Warrior", "nodeStates": {"warrior_c0_r0": 0}}]
        )
        source = aggregate(build, season_trees, filter_data)
        assert source.total("dmg_inc") == 0.0

    def test_node_not_in_season_tree_is_skipped(self):
        season_trees = {"warrior": _season_tree("Warrior", [])}
        filter_data = _filter("Warrior", "micro", "dmg_inc", [0.09, 0.18, 0.27])
        build = _build(
            slots=[{"treeName": "Warrior", "nodeStates": {"warrior_c0_r0": 1}}]
        )
        source = aggregate(build, season_trees, filter_data)
        assert source.total("dmg_inc") == 0.0

    def test_none_slot_is_skipped(self):
        season_trees = {}
        filter_data = {}
        build = _build(slots=[None])
        source = aggregate(build, season_trees, filter_data)
        assert source.total("dmg_inc") == 0.0

    def test_multiple_slots_accumulate(self):
        season_trees = {
            "warrior": _season_tree("Warrior", [_node("warrior_c0_r0", "micro", 3)]),
            "ranger": _season_tree("Ranger", [_node("ranger_c0_r0", "micro", 3)]),
        }
        filter_data = {
            "recipes": {
                "Warrior": {"micro": [{"stat": "dmg_inc", "rank1": 0.09, "values": [0.09, 0.18, 0.27]}]},
                "Ranger": {"micro": [{"stat": "dmg_inc", "rank1": 0.09, "values": [0.09, 0.18, 0.27]}]},
            }
        }
        build = _build(slots=[
            {"treeName": "Warrior", "nodeStates": {"warrior_c0_r0": 1}},
            {"treeName": "Ranger", "nodeStates": {"ranger_c0_r0": 1}},
        ])
        source = aggregate(build, season_trees, filter_data)
        assert source.total("dmg_inc") == pytest.approx(0.18)


# ---------------------------------------------------------------------------
# aggregate — slate slots
# ---------------------------------------------------------------------------

class TestAggregateSlates:
    def test_slate_node_contributes_at_rank_1(self):
        season_trees = {
            "warrior": _season_tree("Warrior", [_node("warrior_c2_r5", "medium", 3)])
        }
        filter_data = _filter("Warrior", "medium", "attack_dmg_inc", [0.18, 0.36, 0.54])
        slate = {
            "slots": [{"selectedNodeId": "warrior_c2_r5", "isCore": False}]
        }
        build = _build(slates=[slate])
        source = aggregate(build, season_trees, filter_data)
        assert source.total("attack_dmg_inc") == pytest.approx(0.18)

    def test_slate_slot_without_node_id_is_skipped(self):
        season_trees = {}
        filter_data = {}
        slate = {"slots": [{"selectedNodeId": None}]}
        build = _build(slates=[slate])
        source = aggregate(build, season_trees, filter_data)
        assert source.total("attack_dmg_inc") == 0.0

    def test_slate_node_not_in_season_tree_is_skipped(self):
        season_trees = {"warrior": _season_tree("Warrior", [])}
        filter_data = _filter("Warrior", "medium", "attack_dmg_inc", [0.18, 0.36, 0.54])
        slate = {"slots": [{"selectedNodeId": "warrior_c2_r5"}]}
        build = _build(slates=[slate])
        source = aggregate(build, season_trees, filter_data)
        assert source.total("attack_dmg_inc") == 0.0


# ---------------------------------------------------------------------------
# BuildSource accumulation
# ---------------------------------------------------------------------------

class TestBuildSource:
    def test_total_sums_all_entries_for_stat(self):
        s = BuildSource()
        s.add("dmg_inc", 0.10)
        s.add("dmg_inc", 0.20)
        assert s.total("dmg_inc") == pytest.approx(0.30)

    def test_total_returns_zero_for_missing_stat(self):
        s = BuildSource()
        assert s.total("nonexistent_stat") == 0.0

    def test_different_stats_do_not_cross_contaminate(self):
        s = BuildSource()
        s.add("dmg_inc", 0.50)
        s.add("attack_dmg_inc", 0.30)
        assert s.total("dmg_inc") == pytest.approx(0.50)
        assert s.total("attack_dmg_inc") == pytest.approx(0.30)
