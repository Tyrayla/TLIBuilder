"""
Tests: Focused Slash support — the regex now handling the "Deals" form text, the shared
slash-skill resolver, and the skill-intrinsic Fervor additional-damage bonus end to end.
"""
import pytest
from engine.models import BuildSource
from engine.skill_resolver import (
    resolve_skill, _REGISTRY, ResolvedSkill, SkillHitForm, IntrinsicAdditional,
)
from engine.offense import calculate_offense
from engine.compute import _eval_intrinsic_additional


def _slash_data(item_id, descript, raw_text):
    return {
        "item_id": item_id, "name": item_id.replace("_", " ").title(),
        "skill_tags": ["Attack", "Melee", "Physical"], "max_level": 20, "raw_text": raw_text,
        "progression": [{"level": 1, "values": {"Descript": descript}}],
    }


_FS = _slash_data(
    "focused_slash",
    "Sweep Slash: Deals 154% Weapon Attack Damage. Steep Strike: Deals 308% Weapon Attack Damage.",
    "Gains Fervor ... This skill +20 % Steep Strike chance.",
)
_BB = _slash_data(
    "berserking_blade",
    "Sweep Slash: 210% Weapon Attack Damage Steep Strike: 421% Weapon Attack Damage",
    "This skill +20 % Steep Strike chance",
)


class TestResolution:
    def test_focused_slash_registered(self):
        assert "focused_slash" in _REGISTRY

    def test_focused_slash_deals_format(self):
        sk = resolve_skill(_FS)
        assert sk.supported
        forms = sk.hit_forms_by_level[1]
        assert [f.name for f in forms] == ["Sweep Slash", "Steep Strike"]
        assert [f.effectiveness_pct for f in forms] == [154.0, 308.0]
        assert forms[0].proc_stat_key == "_complement_steep_strike_chance"
        assert forms[1].proc_stat_key == "steep_strike_chance"
        assert sk.base_steep_strike_chance == pytest.approx(0.2)

    def test_focused_slash_has_fervor_intrinsic(self):
        ia = resolve_skill(_FS).intrinsic_additional
        assert len(ia) == 1
        assert ia[0].per == pytest.approx(0.004)
        assert ia[0].rating_key == "fervor_rating"
        assert ia[0].effect_key == "fervor_effect_inc"

    def test_berserking_blade_unchanged(self):
        sk = resolve_skill(_BB)
        assert [f.effectiveness_pct for f in sk.hit_forms_by_level[1]] == [210.0, 421.0]
        assert sk.intrinsic_additional == []  # no Fervor bonus


class TestIntrinsicEval:
    def _fs_skill(self):
        return ResolvedSkill("focused_slash", "FS", [], 20, {},
                             intrinsic_additional=[IntrinsicAdditional(0.004, "fervor_rating", effect_key="fervor_effect_inc")])

    def test_fervor_bonus_scales_with_rating_and_effect(self):
        s = BuildSource(); s.add("fervor_effect_inc", 0.5)  # +50% Fervor Effect
        # 0.004 * 100 rating * (1 + 0.5) = 0.6
        assert _eval_intrinsic_additional(self._fs_skill(), s, {"fervor_rating": 100.0}) == pytest.approx(0.6)

    def test_zero_rating_no_bonus(self):
        assert _eval_intrinsic_additional(self._fs_skill(), BuildSource(), {}) == 0.0

    def test_skill_without_intrinsic(self):
        bb = ResolvedSkill("bb", "BB", [], 20, {})
        assert _eval_intrinsic_additional(bb, BuildSource(), {"fervor_rating": 100.0}) == 0.0


class TestOffenseExtraAdditional:
    def _src(self):
        s = BuildSource()
        s.add("weapon_attack_speed", 1.0)
        s.add("physical_attack_dmg_flat_min", 100.0)
        s.add("physical_attack_dmg_flat_max", 100.0)
        return s

    def _skill(self):
        return ResolvedSkill("t", "T", ["attack"], 1,
                            {1: [SkillHitForm("Hit", 100.0, "additive", None)]}, supported=True)

    def test_extra_additional_multiplies_dps(self):
        base = calculate_offense(self._src(), self._skill(), 1)
        boosted = calculate_offense(self._src(), self._skill(), 1, extra_additional=0.5)
        assert base.total_dps > 0
        assert boosted.total_dps == pytest.approx(base.total_dps * 1.5)

    def test_default_extra_additional_is_noop(self):
        a = calculate_offense(self._src(), self._skill(), 1)
        b = calculate_offense(self._src(), self._skill(), 1, extra_additional=0.0)
        assert a.total_dps == pytest.approx(b.total_dps)
