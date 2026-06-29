"""Penetration wiring into the calculation-target mitigation + the condition-cap consumption fix.

Before: the dummy mitigation was a hardcoded constant (phys 0.50, non-phys 0.49) that ignored the
attacker's penetration, so armor_pen / resistance pen resolved but sat unread (yellow). Now mitigation
deducts penetration from the target's effective armor/resist and may go negative -> amplify (Help DB).
With zero penetration it reproduces the old constants exactly, so DPS-vs-target is unchanged.

Also: cap-raising stats (max_*_blessing_stacks_flat, etc.) are now recorded as consumed so a node that
only raises a numeric-condition cap badges Consumed (green) instead of false Inactive.
"""
import pytest

from engine.offense import (_target_mitigation, TARGET_ARMOR_MITIGATION,
                            TARGET_NONPHYS_ARMOR_FACTOR, TARGET_ELEMENTAL_RESIST)
from engine.models import BuildSource


def _src(**stats):
    s = BuildSource()
    for k, v in stats.items():
        s.add(k, v)
    return s


class TestZeroPenIsUnchanged:
    def test_physical(self):
        assert _target_mitigation(_src(), "physical") == pytest.approx(0.50)

    @pytest.mark.parametrize("dtype", ["fire", "cold", "lightning", "erosion"])
    def test_nonphys_049(self, dtype):
        assert _target_mitigation(_src(), dtype) == pytest.approx(0.49)


class TestArmorPen:
    def test_physical_deducts(self):
        # 0.50 armor reduction - 0.25 pen = 0.25 -> mult 0.75
        assert _target_mitigation(_src(armor_pen=0.25), "physical") == pytest.approx(0.75)

    def test_physical_negative_amplifies(self):
        # 0.50 - 0.60 = -0.10 reduction -> mult 1.10 (amplified, Help DB: pen can go negative)
        assert _target_mitigation(_src(armor_pen=0.60), "physical") == pytest.approx(1.10)

    def test_nonphys_uses_60pct_armor_portion(self):
        # non-phys armor = 0.50*0.60 = 0.30; -0.25 pen = 0.05 -> (1-0.05)*(1-0.30 resist) = 0.665
        assert _target_mitigation(_src(armor_pen=0.25), "fire") == pytest.approx(0.665)


class TestResistancePen:
    def test_type_pen(self):
        # fire resist 0.30 - 0.30 fire_pen = 0 -> (1-0.30 armor)*(1-0) = 0.70
        assert _target_mitigation(_src(fire_pen=0.30), "fire") == pytest.approx(0.70)

    def test_elemental_pen_stacks_and_amplifies(self):
        # resist 0.30 - 0.40 elemental_pen = -0.10 -> (1-0.30)*(1+0.10) = 0.77
        assert _target_mitigation(_src(elemental_pen=0.40), "lightning") == pytest.approx(0.77)

    def test_elemental_pen_excludes_erosion(self):
        # elemental_pen must NOT touch erosion resist
        assert _target_mitigation(_src(elemental_pen=0.30), "erosion") == pytest.approx(0.49)

    def test_erosion_pen(self):
        assert _target_mitigation(_src(erosion_pen=0.30), "erosion") == pytest.approx(0.70)

    def test_all_resistance_reduction_signed_applies_to_all4(self):
        # stored negative; reduces resist 0.30 -> 0.20 -> (1-0.30)*(1-0.20) = 0.56 for both elem + erosion
        assert _target_mitigation(_src(all_resistance_reduction=-0.10), "cold") == pytest.approx(0.56)
        assert _target_mitigation(_src(all_resistance_reduction=-0.10), "erosion") == pytest.approx(0.56)


class TestScopedPenSurfacesOnTargetPanel:
    """REGRESSION: skill-scoped penetration (e.g. Awakening Skull's "Armor DMG Mitigation Penetration for Attack
    Skills") lives only in the active skill's MATERIALIZED source, so the target panel — which used the raw global
    source — showed 0 pen even while the displayed DPS applied it. target_stats now materializes the headline
    skill's source, so attack-scoped pen surfaces for an attack and stays 0 for a spell."""

    def _run(self, skill, dual=False):
        from server import engine_stats, EngineStatsRequest
        from tests.mock_build import make_request, DUAL_WEAPONS
        gear = DUAL_WEAPONS + [{"item_name": "Skull", "contributions": [
            {"stat": "life_consumed_pct_max_per_sec", "display_value": 0.40, "unit": "",
             "slot": "helmet", "item_name": "Skull", "text": "drain"}]}]
        conds = {"dual_wielding": True} if dual else {}
        req = make_request(skill, 20, gear=gear, extra_conditions=conds)
        req["custom_mods"] = ["+(20-25) % Armor DMG Mitigation Penetration for Attack Skills "
                              "if you have consumed more than 120 % of Max Life recently"]
        r = engine_stats(EngineStatsRequest(**req))
        return r if isinstance(r, dict) else r.model_dump()

    def test_attack_scoped_pen_shows_for_attack(self):
        ts = self._run("berserking_blade", dual=True)["target_stats"]
        a = ts["armor"]
        assert a["pen"] == pytest.approx(0.225)           # 20-25% midpoint, attack-scoped, gate met (160% recently)
        assert a["effective_phys"] == pytest.approx(0.275)  # 0.50 base - 0.225 pen
        # The scoped pen must also appear in the per-stat SOURCE breakdown (it's absent from the global stat_map,
        # so the panel reads it from target_stats.pen_sources). Without this the tooltip showed only the base.
        srcs = (ts.get("pen_sources") or {}).get("armor_pen") or []
        assert any(abs(s["amount"] - 0.225) < 1e-6 for s in srcs)

    def test_attack_scoped_pen_hidden_for_spell(self):
        a = self._run("chromatic_shot")["target_stats"]["armor"]
        assert a["pen"] == pytest.approx(0.0)             # attack-scoped pen does not apply to a spell


class TestConsumption:
    """Pen + cap stats are now actually READ, so they badge Consumed (green), not yellow/Inactive."""
    def test_pen_stats_in_universe(self):
        from engine.consumable_universe import consumable_universe
        u = consumable_universe()
        for k in ("armor_pen", "elemental_pen", "fire_pen", "cold_pen", "lightning_pen",
                  "erosion_pen", "all_resistance_reduction"):
            assert k in u, f"{k} should be a consumed (modeled) stat"

    def test_cap_stats_consumed_per_build(self):
        from server import engine_stats, EngineStatsRequest
        res = engine_stats(EngineStatsRequest(
            slots=[None, None, None, None],
            skills=[{"slot": 1, "skill_id": "chain_lightning", "level": 14}],
            main_skill={"skill_id": "chain_lightning", "level": 14}, characterLevel=100))
        # The Focus Blessing cap stat is read every build to set the focus_blessings cap -> Consumed.
        assert "max_focus_blessing_stacks_flat" in res["consumed_stats"]
