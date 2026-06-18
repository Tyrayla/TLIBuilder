"""Tangles — a Spell turned into a Tangle (via the Spell Tangle activator) is cast by N attached tangles, not
the player. Tangle DPS = single-cast offense × attached_count × (1 + Σ Tangle Damage Enhancement), with the
tangle damage / additional / crit pools applying via the "tangle" tag. See the approved plan.

Model (owner-confirmed): each tangle is a full caster; attached_count = min(1 + extra_tangle_applied_flat,
2 + max_tangle_quantity_flat) (default 1); active_tangles condition can lower it (never raise); Tangle Damage
Enhancement is its OWN multiplier that stacks additively with itself; Dormant Entanglement = +40% additional
Tangle Damage per inactivated tangle (placeable − active), gated on has_dormant_entanglement.
"""
import pytest

from tests.mock_build import make_request, DUAL_WEAPONS
from server import engine_stats, EngineStatsRequest
from engine import mod_parser as mp

_SPELL = "chain_lightning"   # a Spell skill → eligible for Tangle
_ACTIVATOR = [{"slot": 1, "item_id": "spell_tangle", "level": 20, "enabled": True}]


def _offense(supports=None, gear=None, conds=None):
    r = engine_stats(EngineStatsRequest(**make_request(
        _SPELL, 20, attached_supports=supports, gear=gear, extra_conditions=conds)))
    d = r.model_dump() if hasattr(r, "model_dump") else r
    return d["offense"]


def _gear_with(**stats):
    """DUAL_WEAPONS plus one item carrying the given engine stats (gear contribution format)."""
    return DUAL_WEAPONS + [{"item_name": "TangleItem", "contributions": [
        {"stat": k, "display_value": v, "unit": "", "slot": "ring", "item_name": "TangleItem",
         "text": f"+{v} {k}"} for k, v in stats.items()]}]


class TestActivation:
    def test_no_activator_not_tangled(self):
        assert _offense()["tangle_count"] == 0

    def test_spell_tangle_activates(self):
        assert _offense(supports=_ACTIVATOR)["tangle_count"] == 1

    def test_manifold_is_not_an_activator(self):
        # Manifold Entanglement is a normal damage support, NOT a tangle activator.
        o = _offense(supports=[{"slot": 1, "item_id": "manifold_entanglement", "level": 20, "enabled": True}])
        assert o["tangle_count"] == 0


class TestCountScaling:
    def test_count_doubles_dps(self):
        c1 = _offense(supports=_ACTIVATOR)
        c2 = _offense(supports=_ACTIVATOR, gear=_gear_with(extra_tangle_applied_flat=1))
        assert c2["tangle_count"] == 2
        assert c2["total_dps_vs_target"] == pytest.approx(2 * c1["total_dps_vs_target"])

    def test_attached_capped_by_placeable(self):
        # +5 apply but only base 2 placeable → attached capped at 2.
        o = _offense(supports=_ACTIVATOR, gear=_gear_with(extra_tangle_applied_flat=5))
        assert o["tangle_count"] == 2

    def test_active_tangles_condition_lowers_only(self):
        cap2 = _gear_with(extra_tangle_applied_flat=1)
        c1 = _offense(supports=_ACTIVATOR)                              # count 1
        lowered = _offense(supports=_ACTIVATOR, gear=cap2, conds={"active_tangles": 1})
        assert lowered["tangle_count"] == 1
        assert lowered["total_dps_vs_target"] == pytest.approx(c1["total_dps_vs_target"])
        # cannot raise above the cap (cap here is 2)
        raised = _offense(supports=_ACTIVATOR, gear=cap2, conds={"active_tangles": 9})
        assert raised["tangle_count"] == 2


class TestEnhancement:
    def test_enhancement_separate_multiplier(self):
        base = _offense(supports=_ACTIVATOR)
        enh = _offense(supports=_ACTIVATOR, gear=_gear_with(tangle_dmg_enhancement_additional=0.50))
        assert enh["tangle_enhancement"] == pytest.approx(1.50)
        assert enh["total_dps_vs_target"] == pytest.approx(1.5 * base["total_dps_vs_target"])

    def test_enhancement_additive_within_itself(self):
        # Two 0.56 enhancement sources sum to 1.12 → ×2.12 (additive within itself, NOT multiplicative).
        enh = _offense(supports=_ACTIVATOR, gear=DUAL_WEAPONS + [
            {"item_name": "A", "contributions": [{"stat": "tangle_dmg_enhancement_additional", "display_value": 0.56,
                                                  "unit": "", "slot": "ring", "item_name": "A", "text": "+0.56 a"}]},
            {"item_name": "B", "contributions": [{"stat": "tangle_dmg_enhancement_additional", "display_value": 0.56,
                                                  "unit": "", "slot": "amulet", "item_name": "B", "text": "+0.56 b"}]},
        ])
        assert enh["tangle_enhancement"] == pytest.approx(2.12)


class TestDormantEntanglement:
    def test_dormant_adds_per_inactivated(self):
        # placeable 2, active 1 → 1 inactivated → +40% additional Tangle Damage when Dormant is enabled.
        cap2 = _gear_with(extra_tangle_applied_flat=1)
        base = _offense(supports=_ACTIVATOR, gear=cap2, conds={"active_tangles": 1})           # count 1, no dormant
        dorm = _offense(supports=_ACTIVATOR, gear=cap2,
                        conds={"active_tangles": 1, "has_dormant_entanglement": True})          # 1 inactivated
        assert base["tangle_count"] == 1 and dorm["tangle_count"] == 1
        assert dorm["total_dps_vs_target"] == pytest.approx(1.40 * base["total_dps_vs_target"])

    def test_dormant_inert_without_flag(self):
        cap2 = _gear_with(extra_tangle_applied_flat=1)
        no = _offense(supports=_ACTIVATOR, gear=cap2, conds={"active_tangles": 1})
        # no flag → no inactivated bonus even though 1 tangle is inactivated
        assert no["tangle_enhancement"] == pytest.approx(1.0)


class TestParserRegression:
    def test_enhancement_maps_to_enhancement_not_inc(self):
        assert mp._parse_custom_mod_text("140 % Tangle Damage Enhancement")[0]["stat_key"] == "tangle_dmg_enhancement_additional"

    def test_tangle_pools_map(self):
        m = lambda t: mp._parse_custom_mod_text(t)[0]["stat_key"]
        assert m("9 % Tangle Damage") == "tangle_dmg_inc"
        assert m("40 % additional Tangle Damage") == "tangle_dmg_additional"
        assert m("120 Tangle Critical Strike Rating") == "tangle_crit_rating_flat"
        assert m("91 % Tangle Attach Range") == "tangle_attach_range_inc"
