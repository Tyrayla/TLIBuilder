"""
Tests: Moon Strike support — the Slash-Strike resolver, its two baseline quirks (Spell Damage
mods apply to its Attack Damage; +1% additional damage per 100 Max Mana capped at +70%).
"""
import pytest
from engine.models import BuildSource
from engine.skill_resolver import (
    resolve_skill, _REGISTRY, ResolvedSkill, SkillHitForm, IntrinsicAdditional,
)
from engine.offense import calculate_offense
from engine.compute import _eval_intrinsic_additional


def _ms_data():
    return {
        "item_id": "moon_strike", "name": "Moon Strike",
        "skill_tags": ["Attack", "Area", "Physical", "Melee", "Slash-Strike"], "max_level": 20,
        "raw_text": "... +1 % additional damage for the skill for every 100 Max Mana, up to +70 % "
                    "This skill +20 % Steep Strike chance.",
        "progression": [{"level": 1, "values": {"Descript":
            "Sweep Slash: Deals 185% Weapon Attack Damage. Steep Strike: Deals 370% Weapon Attack Damage."}}],
    }


class TestResolution:
    def test_registered(self):
        assert "moon_strike" in _REGISTRY

    def test_resolves(self):
        sk = resolve_skill(_ms_data())
        assert sk.supported
        assert [f.effectiveness_pct for f in sk.hit_forms_by_level[1]] == [185.0, 370.0]
        assert sk.base_steep_strike_chance == pytest.approx(0.2)

    def test_borrows_spell_damage_tag(self):
        sk = resolve_skill(_ms_data())
        assert sk.extra_damage_mod_tags == ["spell"]

    def test_mana_intrinsic(self):
        ia = resolve_skill(_ms_data()).intrinsic_additional
        assert len(ia) == 1
        assert ia[0].rating_key == "max_mana" and ia[0].rating_source == "stat"
        assert ia[0].per == pytest.approx(0.01) and ia[0].per_n == pytest.approx(100.0)
        assert ia[0].cap == pytest.approx(0.70)


class TestManaIntrinsicEval:
    def _skill(self):
        return ResolvedSkill("moon_strike", "MS", [], 20, {}, intrinsic_additional=[
            IntrinsicAdditional(per=0.01, rating_key="max_mana", rating_source="stat", per_n=100.0, cap=0.70)])

    def test_scales_per_100_max_mana(self):
        s = BuildSource(); s.add("max_mana", 3500.0)
        assert _eval_intrinsic_additional(self._skill(), s, {}) == pytest.approx(0.35)  # 0.01 * 35

    def test_capped_at_70(self):
        s = BuildSource(); s.add("max_mana", 10000.0)
        assert _eval_intrinsic_additional(self._skill(), s, {}) == pytest.approx(0.70)  # 100% -> cap

    def test_zero_mana(self):
        assert _eval_intrinsic_additional(self._skill(), BuildSource(), {}) == 0.0


class TestSpellDamageBorrowing:
    def _src(self):
        s = BuildSource()
        s.add("weapon_attack_speed", 1.0)
        s.add("physical_attack_dmg_flat_min", 100.0)
        s.add("physical_attack_dmg_flat_max", 100.0)
        return s

    def _skill(self, extra=("spell",)):
        return ResolvedSkill("ms", "MS", ["attack"], 1,
                            {1: [SkillHitForm("Hit", 100.0, "additive", None)]}, supported=True,
                            extra_damage_mod_tags=list(extra))

    def test_spell_inc_applies_when_borrowed(self):
        src = self._src(); src.add("spell_dmg_inc", 0.5)  # +50% increased spell damage
        borrowed = calculate_offense(src, self._skill(), 1)
        control = calculate_offense(self._src(), self._skill(extra=()), 1)
        # spell_dmg_inc only applies to the borrowing skill -> 1.5x.
        assert borrowed.total_dps == pytest.approx(control.total_dps * 1.5)

    def test_spell_additional_applies_when_borrowed(self):
        src = self._src(); src.add("spell_dmg_additional", 0.3)  # +30% additional spell damage
        borrowed = calculate_offense(src, self._skill(), 1)
        control = calculate_offense(self._src(), self._skill(extra=()), 1)
        assert borrowed.total_dps == pytest.approx(control.total_dps * 1.3)

    def test_attack_skill_ignores_spell_without_borrow(self):
        # Plain attack skill (no borrow) must NOT pick up spell damage.
        src = self._src(); src.add("spell_dmg_inc", 0.5)
        with_spell = calculate_offense(src, self._skill(extra=()), 1)
        without = calculate_offense(self._src(), self._skill(extra=()), 1)
        assert with_spell.total_dps == pytest.approx(without.total_dps)
