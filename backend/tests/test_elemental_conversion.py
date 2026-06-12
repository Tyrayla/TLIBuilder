"""Elemental damage split + its interaction with multi-hop conversion (engine/offense.py):
  • elemental_dmg_inc / elemental_dmg_additional apply to Fire/Cold/Lightning only (NOT Erosion/Physical);
  • a multi-type "Elemental" modifier counts ONCE across an elemental→elemental conversion hop — verified
    in-game (Berserking Blade + Oathkeeper, phys→Lightning vs phys→Lightning→Cold). Type-specific mods
    still SUM once per distinct type in the conversion path.
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


class TestElementalSplit:
    def test_elemental_inc_hits_three_elements_only(self):
        r = calculate_offense(_flat_attack_source(elemental_dmg_inc=0.5), _skill(), 1)
        assert r.type_inc["fire"] == pytest.approx(0.5)
        assert r.type_inc["cold"] == pytest.approx(0.5)
        assert r.type_inc["lightning"] == pytest.approx(0.5)
        assert r.type_inc["erosion"] == pytest.approx(0.0)   # Erosion is NOT elemental
        assert r.type_inc["physical"] == pytest.approx(0.0)  # Physical is NOT elemental

    def test_elemental_inc_not_in_generic_pool(self):
        # Must be type-specific (the "elemental" pseudo-tag is in _DTYPE_TAG_SET), not a uniform multiplier.
        r = calculate_offense(_flat_attack_source(elemental_dmg_inc=0.5), _skill(), 1)
        assert r.generic_inc == pytest.approx(0.0)

    def test_elemental_additional_hits_three_elements_only(self):
        r = calculate_offense(_flat_attack_source(elemental_dmg_additional=0.5), _skill(), 1)
        assert r.type_add["fire"] == pytest.approx(1.5)
        assert r.type_add["lightning"] == pytest.approx(1.5)
        assert r.type_add["erosion"] == pytest.approx(1.0)   # no elemental additional on Erosion
        assert r.type_add["physical"] == pytest.approx(1.0)


class TestElementalThroughConversion:
    """A multi-type "Elemental" modifier applies ONCE regardless of how many elemental types the damage
    converts through — it must NOT compound per elemental hop. Type-specific mods still SUM once per type."""

    def _convsrc(self, convert, **mods):
        s = _source(weapon_attack_speed=1.0, **mods)
        s.add("physical_dmg_gear_flat_min", 100.0)
        s.add("physical_dmg_gear_flat_max", 100.0)
        for k, v in convert.items():
            s.add(k, v)
        return s

    def test_elemental_mods_count_once_across_elemental_hops(self):
        one = calculate_offense(self._convsrc({"physical_convert_to_lightning": 1.0},
                                              elemental_dmg_inc=0.4, elemental_dmg_additional=0.2), _skill(), 1)
        two = calculate_offense(self._convsrc({"physical_convert_to_lightning": 1.0,
                                               "lightning_convert_to_cold": 1.0},
                                              elemental_dmg_inc=0.4, elemental_dmg_additional=0.2), _skill(), 1)
        assert two.total_dps == pytest.approx(one.total_dps)  # NOT compounded by the extra Lightning→Cold hop

    def test_type_specific_mods_still_sum_over_path(self):
        # Distinct per-type mods DO each apply once: phys→light→cold picks up both light inc and cold inc.
        base = calculate_offense(self._convsrc({"physical_convert_to_lightning": 1.0,
                                                "lightning_convert_to_cold": 1.0}), _skill(), 1)
        both = calculate_offense(self._convsrc({"physical_convert_to_lightning": 1.0,
                                                "lightning_convert_to_cold": 1.0},
                                               lightning_dmg_inc=0.5, cold_dmg_inc=0.3), _skill(), 1)
        assert both.total_dps == pytest.approx(base.total_dps * (1 + 0.5 + 0.3))
