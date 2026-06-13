"""Triple/Quadruple damage (plan Part 2 / Test D): highest-tier-procs expected value, reducing to the prior
double-only behavior when only double chance is present. Plus resolver: 'chance for <X> Skills to deal
Triple Damage' → triple_dmg_chance + scope."""
import pytest

from engine.models import BuildSource
from engine.offense import calculate_offense
from engine.skill_resolver import ResolvedSkill, SkillHitForm
from server import _parse_custom_mod_text as pm

ALL = ("physical", "fire", "cold", "lightning", "erosion")


def _src(**stats):
    s = BuildSource(); s.add("weapon_attack_speed", 1.0)
    for t in ALL:
        s.add(f"{t}_dmg_gear_flat_min", 10.0); s.add(f"{t}_dmg_gear_flat_max", 10.0)
    for k, v in stats.items():
        s.add(k, v)
    return s


def _sk():
    return ResolvedSkill(skill_id="t", name="T", tags=["attack"], max_level=1,
                         hit_forms_by_level={1: [SkillHitForm(name="H", effectiveness_pct=100.0,
                                                              form_type="additive", proc_stat_key=None)]},
                         supported=True, base_steep_strike_chance=0.0, is_spell=False,
                         base_dmg_by_level={}, base_cast_time=1.0, added_dmg_effectiveness=1.0, main_stat=[])


def _dps(**stats):
    return calculate_offense(_src(**stats), _sk(), 1).total_dps


class TestTieredEV:
    def test_double_only_reduces_to_current(self):
        base = _dps()
        assert _dps(double_dmg_chance=0.5) == pytest.approx(base * 1.5)   # 1 + q2  (unchanged behavior)
        assert _dps(double_dmg_chance=2.0) == pytest.approx(base * 2.0)   # capped → ×2

    def test_triple_expected_value(self):
        base = _dps()
        # q3=0.5 → 0.5×3 + 0.5×1 = ×2.0
        assert _dps(triple_dmg_chance=0.5) == pytest.approx(base * 2.0)

    def test_quad_expected_value(self):
        base = _dps()
        # q4=0.5 → 0.5×4 + 0.5×1 = ×2.5
        assert _dps(quadruple_dmg_chance=0.5) == pytest.approx(base * 2.5)

    def test_highest_tier_only(self):
        base = _dps()
        # q4=q3=q2=1.0 → guaranteed quad → ×4 (only the highest procs, not stacked)
        assert _dps(quadruple_dmg_chance=1.0, triple_dmg_chance=1.0, double_dmg_chance=1.0) \
            == pytest.approx(base * 4.0)


class TestResolve:
    def test_triple_chance_scoped(self):
        e = pm("+5 % chance for Attack Skills to deal Triple Damage")[0]
        assert e["stat_key"] == "triple_dmg_chance" and e.get("scope") == "attack"

    def test_quadruple_chance_resolves(self):
        e = pm("+3 % Quadruple Damage Chance")[0]
        assert e["stat_key"] == "quadruple_dmg_chance"
