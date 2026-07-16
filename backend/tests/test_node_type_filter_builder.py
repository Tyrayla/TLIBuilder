"""
Tests: tools/node_type_filter_builder.py
Scope: _is_conditional, _detect_condition, and _meta counter correctness.
"""
import pytest
from tools.node_type_filter_builder import (
    _is_conditional, _detect_condition, _detect_scaling, build_filter, build_node_recipes,
)


# ---------------------------------------------------------------------------
# _is_conditional
# ---------------------------------------------------------------------------

class TestIsConditional:
    def test_while_phrase_is_conditional(self):
        assert _is_conditional("+20% Damage while holding a Shield") is True

    def test_when_phrase_is_conditional(self):
        assert _is_conditional("+10% Attack Damage when Tenacity Blessing is active") is True

    def test_if_phrase_is_conditional(self):
        assert _is_conditional("+5% Speed if moving") is True

    def test_against_phrase_is_conditional(self):
        assert _is_conditional("+15% Damage against Ignited enemies") is True

    def test_recently_is_conditional(self):
        assert _is_conditional("+10% Damage if you have used a Mobility Skill recently") is True

    def test_on_hit_is_conditional(self):
        assert _is_conditional("Inflicts Trauma on Hit") is True

    def test_per_x_is_conditional(self):
        assert _is_conditional("+2% Damage per Sentry") is True

    def test_per_second_is_not_conditional(self):
        assert _is_conditional("+5% Life Regeneration per Second") is False

    def test_clean_text_is_not_conditional(self):
        assert _is_conditional("+15% Attack Damage") is False

    def test_plain_stat_is_not_conditional(self):
        assert _is_conditional("+100 Maximum Life") is False


# ---------------------------------------------------------------------------
# _detect_condition
# ---------------------------------------------------------------------------

class TestDetectCondition:
    def test_holding_shield(self):
        assert _detect_condition("while holding a shield") == "holding_shield"

    def test_tenacity_blessing(self):
        assert _detect_condition("+10% Crit while Tenacity Blessing is active") == "tenacity_active"

    def test_focus_blessing(self):
        assert _detect_condition("while Focus Blessing is active") == "focus_active"

    def test_agility_blessing(self):
        assert _detect_condition("when Agility Blessing is active") == "agility_active"

    def test_mobility_skill(self):
        assert _detect_condition("+30% Damage for 4s after using a Mobility Skill") == "recently_used_mobility"

    def test_low_mana(self):
        assert _detect_condition("+20% Spell Damage at Low Mana") == "at_low_mana"

    def test_dual_wield(self):
        assert _detect_condition("while dual wielding") == "dual_wielding"

    def test_two_handed(self):
        assert _detect_condition("with a two-handed weapon") == "holding_two_handed"

    def test_standing_still(self):
        assert _detect_condition("while standing still") == "standing_still"

    def test_enemy_frozen(self):
        assert _detect_condition("against Frozen enemies") == "enemy_frozen"

    def test_proximity_is_distinct_from_nearby(self):
        # "in proximity" and "nearby" are different in-game ranges — must not collapse.
        assert _detect_condition("+60% Projectile Damage against enemies in proximity") == "enemy_in_proximity"
        assert _detect_condition("+25% damage dealt to Nearby enemies") == "enemy_nearby"

    def test_unknown_pattern_returns_none(self):
        assert _detect_condition("while something completely unrecognised") is None

    def test_clean_text_returns_none(self):
        assert _detect_condition("+15% Attack Damage") is None


# ---------------------------------------------------------------------------
# _detect_scaling
# ---------------------------------------------------------------------------

class TestDetectScaling:
    def test_per_stack_of_blessing(self):
        assert _detect_scaling("+5% Spell Crit Damage per stack of Focus Blessing owned") == ("focus_blessings", 1.0, False)
        assert _detect_scaling("+6% Armor per stack of Tenacity Blessing owned") == ("tenacity_blessings", 1.0, False)
        assert _detect_scaling("+6% Evasion per stack of Agility Blessing owned") == ("agility_blessings", 1.0, False)

    def test_per_stack_of_any_blessing(self):
        # "any/a Blessing" scales by the summed any_blessings condition, not a single blessing.
        assert _detect_scaling("+3% additional damage per stack of any Blessing") == ("any_blessings", 1.0, False)
        assert _detect_scaling("+3% additional damage per stack of a Blessing owned") == ("any_blessings", 1.0, False)

    def test_per_fervor_rating(self):
        assert _detect_scaling("0.5% Critical Strike Damage per Fervor Rating") == ("fervor_rating", 1.0, False)

    def test_per_n_fervor_rating_reads_divisor(self):
        assert _detect_scaling("+1% Movement Speed per 10 Fervor Rating") == ("fervor_rating", 10.0, False)

    def test_for_each_regain_uses_regain_stacks(self):
        assert _detect_scaling("+2% additional Attack Speed for each time you have Regained in the last 8s") == ("regain_stacks", 1.0, False)

    def test_for_each_unique_weapon_keeps_gate(self):
        # keep_gate=True — the dual_wielding gate is a separate mechanic from the scaling number.
        assert _detect_scaling("+5% additional Attack Damage for each unique type of weapon equipped while Dual Wielding") == ("unique_weapon_types", 1.0, True)

    def test_non_scaling_text_returns_none(self):
        assert _detect_scaling("+15% Attack Damage while Dual Wielding") is None


# ---------------------------------------------------------------------------
# build_node_recipes — conditional matching + scaling emission
# ---------------------------------------------------------------------------

def _node_snapshot(node_id: str, effects: list[str], node_type: str = "legendary_medium") -> dict:
    return {"test": {"tree_name": "Test", "nodes": [
        {"id": node_id, "node_type": node_type, "effects": effects},
    ]}}


class TestBuildNodeRecipesConditional:
    def test_conditional_effect_resolves_stat_and_condition(self):
        # Previously dropped (un-stripped Jaccard failed); now strips clause then matches.
        nr = build_node_recipes(_node_snapshot("n_c0_r0", ["+9% Attack Damage while Dual Wielding"]))
        r = nr["n_c0_r0"][0]
        assert r["stat"] == "attack_dmg_inc"
        assert r["condition"] == "dual_wielding"
        assert "scaling" not in r

    def test_per_stack_emits_scaling_and_drops_redundant_gate(self):
        nr = build_node_recipes(_node_snapshot("n_c0_r0", ["+6% Armor per stack of Tenacity Blessing owned"]))
        r = nr["n_c0_r0"][0]
        assert r["stat"] == "armor_inc"
        assert r["scaling"] == {"key": "tenacity_blessings", "per": 0.06}
        assert r["values"] == []
        assert "condition" not in r  # same-mechanic gate dropped

    def test_per_n_emits_per_n_divisor(self):
        nr = build_node_recipes(_node_snapshot("n_c0_r0", ["+1% Movement Speed per 10 Fervor Rating"]))
        r = nr["n_c0_r0"][0]
        assert r["scaling"]["key"] == "fervor_rating"
        assert r["scaling"]["per_n"] == 10.0

    def test_unique_weapon_keeps_separate_gate(self):
        nr = build_node_recipes(_node_snapshot(
            "n_c0_r0", ["+5% additional Attack Damage for each unique type of weapon equipped while Dual Wielding"]))
        r = nr["n_c0_r0"][0]
        assert r["scaling"]["key"] == "unique_weapon_types"
        assert r["condition"] == "dual_wielding"  # separate-mechanic gate kept


# ---------------------------------------------------------------------------
# build_filter — _meta counter correctness (tree-driven; the PDF snapshot path is retired)
# ---------------------------------------------------------------------------

def _minimal_trees(texts: list[str], node_type: str = "Micro Talent") -> dict:
    """Build minimal season-tree data with one tree and one node per text."""
    nodes = []
    for i, text in enumerate(texts):
        nodes.append({
            "id": f"test_c{i}_r0",
            "node_type": node_type,
            "max_rank": 1,
            "effects": [text],
        })
    return {"test_tree": {"tree_name": "Test Tree", "nodes": nodes}}


class TestMetaCounters:
    def test_matched_text_increments_matched_not_unmatched(self):
        result = build_filter(_minimal_trees(["+15% Attack Damage"]))
        assert result["_meta"]["unmatched"] == 0
        assert result["_meta"]["matched"] >= 1

    def test_conditional_text_increments_conditional_not_unmatched(self):
        # "for every" is conditional but not in _CONDITION_MAP → no cond_key → conditional_count
        result = build_filter(_minimal_trees(["+2% Damage for every Stack"]))
        assert result["_meta"]["unmatched"] == 0
        assert result["_meta"]["conditional"] >= 1

    def test_unrecognised_text_increments_unmatched(self):
        result = build_filter(_minimal_trees(["zzzxxx totally unknown modifier qqq"]))
        assert result["_meta"]["unmatched"] >= 1

    def test_conditional_with_known_condition_produces_conditional_recipe(self):
        result = build_filter(_minimal_trees(["+15% Attack Damage while holding a Shield"]))
        tree_recipes = result.get("recipes", {}).get("Test Tree", {})
        all_recipes = [r for recipes in tree_recipes.values() for r in recipes]
        cond_recipes = [r for r in all_recipes if r.get("condition")]
        assert len(cond_recipes) >= 1
        assert cond_recipes[0]["condition"] == "holding_shield"

    def test_raw_node_type_names_are_normalized(self):
        # Season trees carry "Legendary Medium Talent" etc. — must normalize to legendary_medium.
        result = build_filter(_minimal_trees(["+15% Attack Damage"], node_type="Legendary Medium Talent"))
        recipes = result["recipes"]["Test Tree"]
        assert list(recipes.keys()) == ["legendary_medium"]
        # legendary_medium nodes have a single rank
        assert len(recipes["legendary_medium"][0]["values"]) == 1
