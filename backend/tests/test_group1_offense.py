"""Group-1 yellow-badge wirings in engine/offense.py:
  • spell/projectile Critical Strike RATING gate on the skill's tag (like the crit-damage pool)
  • double-damage chance → expected-value (1 + Σchance, capped at 1.0) multiplier on DPS, tag-gated
(Elemental split + its conversion interaction live in test_elemental_conversion.py.)
"""
import pytest

from engine.models import BuildSource
from engine.offense import calculate_offense
from engine.skill_resolver import ResolvedSkill, SkillHitForm

ALL = ("physical", "fire", "cold", "lightning", "erosion")


def _source(**stats):
    s = BuildSource()
    for k, v in stats.items():
        s.add(k, v)
    return s


def _flat_attack_source(**extra):
    """Attack source with 10–10 weapon flat in every damage type so every type is in calc_types."""
    s = _source(weapon_attack_speed=1.0, **extra)
    for t in ALL:
        s.add(f"{t}_dmg_gear_flat_min", 10.0)
        s.add(f"{t}_dmg_gear_flat_max", 10.0)
    return s


def _skill(tags=("attack",), is_spell=False):
    return ResolvedSkill(
        skill_id="t", name="T", tags=list(tags), max_level=1,
        hit_forms_by_level={1: [SkillHitForm(name="H", effectiveness_pct=100.0,
                                             form_type="additive", proc_stat_key=None)]},
        supported=True, base_steep_strike_chance=0.0, is_spell=is_spell,
        base_dmg_by_level=({1: {t: (10.0, 10.0) for t in ALL}} if is_spell else {}),
        base_cast_time=1.0, added_dmg_effectiveness=1.0, main_stat=[],
    )


class TestCritRatingPerTag:
    def test_spell_crit_rating_inc_gates_on_spell(self):
        # spell_crit_rating_inc scales CSR only for a spell skill, not an attack skill.
        spell = calculate_offense(
            _source(spell_crit_rating_inc=1.0), _skill(tags=("spell",), is_spell=True), 1)
        atk = calculate_offense(
            _flat_attack_source(weapon_crit_rating_flat=500.0, spell_crit_rating_inc=1.0), _skill(), 1)
        # Spell base 500 CSR × (1+1.0) = 1000 → 10%.
        assert spell.crit_chance == pytest.approx(0.10)
        # Attack: 500 weapon CSR, spell inc must NOT apply → stays 5%.
        assert atk.crit_chance == pytest.approx(0.05)

    def test_spell_crit_rating_flat_gates_on_spell(self):
        spell = calculate_offense(_source(spell_crit_rating_flat=500.0), _skill(tags=("spell",), is_spell=True), 1)
        atk = calculate_offense(_flat_attack_source(spell_crit_rating_flat=500.0), _skill(), 1)
        assert spell.crit_chance == pytest.approx(0.10)  # 500 base + 500 flat = 1000 → 10%
        assert atk.crit_chance == pytest.approx(0.0)      # spell flat ignored on attack

    def test_projectile_crit_rating_inc_gates_on_projectile(self):
        proj = calculate_offense(
            _flat_attack_source(weapon_crit_rating_flat=500.0, projectile_crit_rating_inc=1.0),
            _skill(tags=("attack", "projectile")), 1)
        melee = calculate_offense(
            _flat_attack_source(weapon_crit_rating_flat=500.0, projectile_crit_rating_inc=1.0), _skill(), 1)
        assert proj.crit_chance == pytest.approx(0.10)   # 500 × (1+1.0) = 1000
        assert melee.crit_chance == pytest.approx(0.05)  # projectile inc ignored on non-projectile


class TestDoubleDamage:
    def test_generic_double_chance_lifts_dps(self):
        base = calculate_offense(_flat_attack_source(), _skill(), 1)
        dbl = calculate_offense(_flat_attack_source(double_dmg_chance=0.5), _skill(), 1)
        assert dbl.total_dps == pytest.approx(base.total_dps * 1.5)

    def test_double_chance_capped_at_one(self):
        base = calculate_offense(_flat_attack_source(), _skill(), 1)
        dbl = calculate_offense(_flat_attack_source(double_dmg_chance=2.0), _skill(), 1)
        assert dbl.total_dps == pytest.approx(base.total_dps * 2.0)  # capped → ×2, not ×3

    def test_spell_double_chance_gates_on_spell(self):
        base = calculate_offense(_flat_attack_source(), _skill(), 1)
        atk = calculate_offense(_flat_attack_source(spell_double_dmg_chance=0.5), _skill(), 1)
        assert atk.total_dps == pytest.approx(base.total_dps)  # spell double ignored on attack
