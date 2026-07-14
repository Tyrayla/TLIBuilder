"""
Tests: engine/aggregator.py — stat collection from node states and slates.
Scope: aggregation logic only; uses synthetic season_trees and filter_data dicts
instead of real file I/O.
"""
import pytest
from engine.models import BuildInput, BuildSource, SkillConfig, EnemyConfig, SourceEntry
from engine.aggregator import aggregate, _tree_slug_from_node_id


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
# aggregate — talent slots
# ---------------------------------------------------------------------------

class TestAggregateSlots:
    def test_allocated_node_contributes_stat(self):
        # Node resolution moved server-side (resolve_nodes); the aggregator consumes node_contributions
        # (already points-scaled). 2 points × rank1 0.09 = 0.18.
        build = _build()
        build.node_contributions = [{"stat_key": "dmg_inc", "amount": 0.18,
                                     "text": "+9% damage |node|warrior_c0_r0", "label": "Warrior",
                                     "condition_expr": None}]
        assert aggregate(build, {}, {}).total("dmg_inc") == pytest.approx(0.18)

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
        build = _build()
        build.node_contributions = [
            {"stat_key": "dmg_inc", "amount": 0.09, "text": "a |node|warrior_c0_r0", "label": "", "condition_expr": None},
            {"stat_key": "dmg_inc", "amount": 0.09, "text": "b |node|ranger_c0_r0", "label": "", "condition_expr": None},
        ]
        assert aggregate(build, {}, {}).total("dmg_inc") == pytest.approx(0.18)


# ---------------------------------------------------------------------------
# aggregate — slate slots
# ---------------------------------------------------------------------------

class TestAggregateSlates:
    def test_slate_node_contributes_at_rank_1(self):
        # Slate contributions (text tagged |slate|) are consumed with source_type="slate".
        build = _build()
        build.node_contributions = [{"stat_key": "attack_dmg_inc", "amount": 0.18,
                                     "text": "x |slate|warrior_c2_r5", "label": "Slate", "condition_expr": None}]
        assert aggregate(build, {}, {}).total("attack_dmg_inc") == pytest.approx(0.18)

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

    def test_add_with_source_accumulates_total(self):
        s = BuildSource()
        entry = SourceEntry(stat="dmg_inc", amount=0.15, source_type="talent", label="Warrior Micro", text="+15% Damage")
        s.add_with_source("dmg_inc", 0.15, entry)
        assert s.total("dmg_inc") == pytest.approx(0.15)

    def test_add_with_source_populates_source_log(self):
        s = BuildSource()
        entry = SourceEntry(stat="dmg_inc", amount=0.15, source_type="talent", label="Warrior Micro", text="+15% Damage")
        s.add_with_source("dmg_inc", 0.15, entry)
        assert len(s.source_log) == 1
        assert s.source_log[0].label == "Warrior Micro"
        assert s.source_log[0].text == "+15% Damage"

    def test_plain_add_does_not_populate_source_log(self):
        s = BuildSource()
        s.add("dmg_inc", 0.15)
        assert s.source_log == []

    def test_source_log_accumulates_multiple_entries(self):
        s = BuildSource()
        e1 = SourceEntry(stat="dmg_inc", amount=0.10, source_type="talent", label="Warrior Micro", text="+10% Damage")
        e2 = SourceEntry(stat="dmg_inc", amount=0.20, source_type="slate", label="Slate — Warrior Medium", text="+20% Damage")
        s.add_with_source("dmg_inc", 0.10, e1)
        s.add_with_source("dmg_inc", 0.20, e2)
        assert s.total("dmg_inc") == pytest.approx(0.30)
        assert len(s.source_log) == 2
        assert s.source_log[1].source_type == "slate"


# ---------------------------------------------------------------------------
# Conditional node contributions are gated in the aggregator
# ---------------------------------------------------------------------------

class TestConditionalRecipes:
    def test_aggregate_passes_build_conditions_to_recipes(self):
        # Conditional node_contributions are GATED in the aggregator (the behavior change: was always-on).
        contrib = {"stat_key": "dmg_inc", "amount": 0.15, "text": "x |node|n", "label": "",
                   "condition_expr": "holding_shield"}
        off = _build(); off.node_contributions = [dict(contrib)]
        assert aggregate(off, {}, {}).total("dmg_inc") == 0.0          # condition off → not applied
        on = _build(); on.node_contributions = [dict(contrib)]
        on.condition_state = {"holding_shield": True}
        assert aggregate(on, {}, {}).total("dmg_inc") == pytest.approx(0.15)   # condition on → applied


# ---------------------------------------------------------------------------
# aggregate()'s own backward-compat condition derivation (active_booleans/numeric_vals left None, so
# aggregate() self-derives via models.conditions.condition_defaults() — engine/aggregator.py:346-362).
# Must respect the SAME explicit-wins/default-fallback invariants as engine.compute._derive_views,
# including the `active_booleans.discard(k)` branch.
# ---------------------------------------------------------------------------

class TestBackwardCompatConditionDefaultFallback:
    # within_gale (Howling Gale, data/conditions.json) catalog-defaults to True and carries no
    # trait_id restriction, so it's always present in condition_defaults()'s bool set.
    _CONTRIB = {"stat_key": "dmg_inc", "amount": 0.25, "text": "x |node|n", "label": "",
                "condition_expr": "within_gale"}

    def test_explicit_false_discards_a_default_true_condition(self):
        # An EXPLICIT False for a default-True condition must REMOVE it from the aggregator's
        # self-derived active_booleans, not leave it active because it was pre-seeded from the catalog
        # default before condition_state was overlaid — the discard branch.
        build = _build()
        build.node_contributions = [dict(self._CONTRIB)]
        build.condition_state = {"within_gale": False}
        # active_booleans/numeric_vals both left None (not passed) → aggregate() self-derives.
        source = aggregate(build, {}, {})
        assert source.total("dmg_inc") == 0.0

    def test_absent_key_still_falls_back_to_default_true(self):
        # Contrast: with NO explicit within_gale key at all, the same gated contribution DOES apply
        # (the catalog default of True), confirming the discard case above is genuinely about the
        # EXPLICIT False, not about within_gale failing to activate at all.
        build = _build()
        build.node_contributions = [dict(self._CONTRIB)]
        source = aggregate(build, {}, {})
        assert source.total("dmg_inc") == pytest.approx(0.25)
