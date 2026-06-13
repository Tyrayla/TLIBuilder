"""Tests: engine/guards.py — the damage-taken immunity tripwire."""
import pytest
from engine.models import BuildSource
from engine.guards import check_damage_taken_immunity, ImmunityThresholdError


def test_no_violation_passes():
    s = BuildSource()
    s.add("dmg_taken_additional", -0.5)       # 50% reduction — fine
    s.add("attack_dmg_additional", 2.0)        # large offense — irrelevant
    check_damage_taken_immunity(s)             # must not raise


def test_additional_taken_at_minus_100_percent_raises():
    s = BuildSource()
    s.add("dmg_taken_additional", -0.6)
    s.add("dmg_taken_additional", -0.5)        # sums to -1.1 -> multiplier <= 0 -> immune
    with pytest.raises(ImmunityThresholdError) as e:
        check_damage_taken_immunity(s)
    assert "dmg_taken_additional" in str(e.value)


def test_just_under_threshold_passes():
    s = BuildSource()
    s.add("physical_dmg_taken_additional", -0.99)   # 99% reduction — still takes damage
    check_damage_taken_immunity(s)


def test_reduction_style_stat_at_100_percent_raises():
    # crit_dmg_taken_reduction is reduction-style: multiplier = 1 - total
    s = BuildSource()
    s.add("crit_dmg_taken_reduction", 1.0)
    with pytest.raises(ImmunityThresholdError):
        check_damage_taken_immunity(s)


def test_conversion_taken_stat_is_ignored():
    # 'taken_as' conversion stats are not magnitude reductions — never trip the guard.
    s = BuildSource()
    s.add("cold_taken_as_fire_inc", 5.0)
    check_damage_taken_immunity(s)
