"""
Tests: tools/node_type_filter_builder.py
Scope: _is_conditional, _detect_condition, and _meta counter correctness.
"""
import pytest
from tools.node_type_filter_builder import _is_conditional, _detect_condition, build_filter


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

    def test_unknown_pattern_returns_none(self):
        assert _detect_condition("while something completely unrecognised") is None

    def test_clean_text_returns_none(self):
        assert _detect_condition("+15% Attack Damage") is None


# ---------------------------------------------------------------------------
# build_filter — _meta counter correctness
# ---------------------------------------------------------------------------

def _minimal_snapshot(texts: list[str], node_type: str = "micro") -> dict:
    """Build a minimal snapshot dict with one tree and one node per text."""
    nodes = []
    for i, text in enumerate(texts):
        nodes.append({
            "id": f"test_c{i}_r0",
            "node_type": node_type,
            "max_points": 1,
            "stats": [{"text": text, "value": 0.15}],
        })
    return {
        "source_file": "test",
        "trees": {"Test Tree": {"tree_name": "Test Tree", "nodes": nodes}},
    }


class TestMetaCounters:
    def test_matched_text_increments_matched_not_unmatched(self):
        snap = _minimal_snapshot(["+15% Attack Damage"])
        result = build_filter(snap)
        assert result["_meta"]["unmatched"] == 0
        assert result["_meta"]["matched"] >= 1

    def test_conditional_text_increments_conditional_not_unmatched(self):
        # "for every" is conditional but not in _CONDITION_MAP → no cond_key → conditional_count
        snap = _minimal_snapshot(["+2% Damage for every Stack"])
        result = build_filter(snap)
        assert result["_meta"]["unmatched"] == 0
        assert result["_meta"]["conditional"] >= 1

    def test_unrecognised_text_increments_unmatched(self):
        snap = _minimal_snapshot(["zzzxxx totally unknown modifier qqq"])
        result = build_filter(snap)
        assert result["_meta"]["unmatched"] >= 1

    def test_conditional_with_known_condition_produces_conditional_recipe(self):
        snap = _minimal_snapshot(["+15% Attack Damage while holding a Shield"])
        result = build_filter(snap)
        tree_recipes = result.get("recipes", {}).get("Test Tree", {})
        all_recipes = [r for recipes in tree_recipes.values() for r in recipes]
        cond_recipes = [r for r in all_recipes if r.get("condition")]
        assert len(cond_recipes) >= 1
        assert cond_recipes[0]["condition"] == "holding_shield"
