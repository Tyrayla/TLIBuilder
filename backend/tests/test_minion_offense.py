"""Minion DPS engine (Phase A) — regression tests for engine.minion_offense.

Covers the building-block math (calculate_minion_offense → OffenseResult), the cooldown-capped rate, the NYI
gates, the count fold, and — most importantly — (a) that PLAYER stat pools never leak onto minion damage and
(b) that an UNMODELLED minion contributes NO damage through the engine (the registry gate).
"""
import pytest

from engine.models import BuildSource
from engine.minion_offense import calculate_minion_offense, _interp_level_table, _coefficient_at, MINION_MODULES


_BASE_STATS = {
    "constants": {"fire_res": 60, "cold_res": 60, "lightning_res": 60, "erosion_res": 60,
                  "crit_damage": 150, "crit_rating_flat": 500},
    "base_damage_by_level": {"1": 100, "16": 800, "17": 850, "20": 1000},
    "life_by_group": {"magus": {}, "synthetic_troop": {}},
}

_BASE_SKILL = {
    "name": "Blazing Dance",
    "skill_tags": ["Base Skill", "Spell", "Fire", "Area"],
    "base_damage_coefficient": 110.0,
    "effectiveness_of_added_damage": "110%",
    "cast_speed": "0.8 s",
    "cooldown": None,
}
_ULTIMATE = {
    "name": "Molten Rising",
    "skill_tags": ["Ultimate", "Spell", "Fire", "Area"],
    "base_damage_coefficient": 637.0,
    "effectiveness_of_added_damage": "637%",
    "cast_speed": "1.5 s",
    "cooldown": "8 s",
}


def _src_with_minion_mods():
    s = BuildSource()
    s.add("minion_dmg_inc", 1.5)          # +150% (generic minion)
    s.add("minion_fire_dmg_inc", 0.5)     # +50% fire
    s.add("minion_dmg_additional", 0.2)   # +20% additional
    s.add("minion_crit_rating_inc", 1.0)  # 1000 CSR = 10% crit
    s.add("minion_crit_dmg_inc", 0.3)     # x1.8 crit multiplier
    s.add("minion_cast_speed_inc", 0.2)   # +20% cast speed
    return s


def test_base_skill_pipeline_math():
    o = calculate_minion_offense(_src_with_minion_mods(), _BASE_SKILL, _BASE_STATS, level=20, minion_count=1)
    assert o.supported and o.skill_name == "Blazing Dance (Base)"
    assert "Spell" in o.skill_tags
    assert o.type_inc["fire"] == pytest.approx(2.0)     # 1.5 + 0.5
    assert o.generic_inc == pytest.approx(1.5)          # minion_dmg_inc only (generic, all-types)
    assert o.type_add["fire"] == pytest.approx(1.2)     # x(1+0.2)
    fire = o.hit_forms[0].hit_max_by_type["fire"]
    assert fire == pytest.approx(1100 * 3.0 * 1.2)      # base 1100 x (1+2.0) x 1.2 = 3960
    assert o.crit_chance == pytest.approx(0.10)
    assert o.crit_multiplier == pytest.approx(1.8)
    assert o.skills_per_second == pytest.approx(1.5)    # 1/0.8 x 1.2
    assert o.total_dps == pytest.approx(3960 * 1.08 * 1.5)
    assert o.total_dps_vs_target == pytest.approx(o.total_dps * 0.49)  # fire dummy mitigation


def test_ultimate_cooldown_caps_rate():
    o = calculate_minion_offense(_src_with_minion_mods(), _ULTIMATE, _BASE_STATS, level=20)
    assert o.skills_per_second == pytest.approx(0.125)  # 1/8 cooldown caps the cast rate


def test_minion_count_folds_into_totals_via_cast_multiplier():
    one = calculate_minion_offense(_src_with_minion_mods(), _BASE_SKILL, _BASE_STATS, 20, minion_count=1)
    three = calculate_minion_offense(_src_with_minion_mods(), _BASE_SKILL, _BASE_STATS, 20, minion_count=3)
    assert three.total_dps == pytest.approx(one.total_dps * 3)
    assert three.cast_multiplier == pytest.approx(3.0)
    # per-form figures stay per-minion (the table reconciles via cast_multiplier)
    assert three.hit_forms[0].dps_vs_target == pytest.approx(one.hit_forms[0].dps_vs_target)


def test_player_stats_do_not_leak_into_minions():
    base = calculate_minion_offense(_src_with_minion_mods(), _BASE_SKILL, _BASE_STATS, 20)
    s = _src_with_minion_mods()
    for k, v in [("dmg_inc", 5.0), ("fire_dmg_inc", 5.0), ("dmg_additional", 2.0), ("crit_rating_inc", 5.0),
                 ("crit_dmg_inc", 3.0), ("cast_speed_inc", 2.0), ("spell_dmg_inc", 5.0), ("elemental_dmg_inc", 5.0)]:
        s.add(k, v)
    polluted = calculate_minion_offense(s, _BASE_SKILL, _BASE_STATS, 20)
    assert polluted.total_dps == pytest.approx(base.total_dps)
    assert polluted.crit_chance == pytest.approx(base.crit_chance)
    assert polluted.skills_per_second == pytest.approx(base.skills_per_second)


def test_nyi_when_base_stats_unfilled():
    empty = {"constants": {}, "base_damage_by_level": {"1": 0, "20": 0}, "life_by_group": {}}
    o = calculate_minion_offense(BuildSource(), _BASE_SKILL, empty, 20)
    assert not o.supported and o.total_dps == 0.0 and o.nyi


def test_nyi_when_no_coefficient():
    buff = {"name": "Blazing Spin", "skill_tags": ["Empower", "Spell", "Fire"],
            "base_damage_coefficient": None, "cast_speed": "0.6 s", "cooldown": "10 s"}
    o = calculate_minion_offense(BuildSource(), buff, _BASE_STATS, 20)
    assert not o.supported


def test_per_level_coefficient_interpolation():
    assert _coefficient_at({"1": 185.0, "20": 278.0}, 20) == pytest.approx(278.0)
    assert _coefficient_at(110.0, 5) == pytest.approx(110.0)
    assert _interp_level_table({"1": 100, "20": 1000}, 16) == pytest.approx(100 + (1000 - 100) * 15 / 19)


def test_unmodelled_minion_contributes_no_damage_through_engine():
    """The registry gate: with no bespoke module for Summon Fire Magus, every nested ability comes back NYI
    (supported=false, 0 DPS) even though the base-stats table is filled — nothing is computed for it."""
    assert "summon_fire_magus" not in MINION_MODULES  # not modelled
    from tests.mock_build import make_request
    from server import engine_stats, EngineStatsRequest
    res = engine_stats(EngineStatsRequest(**make_request("summon_fire_magus", 20)))
    mo = res.get("minion_offense")
    assert mo and "summon_fire_magus" in mo
    abilities = mo["summon_fire_magus"]
    names = {a["skill_name"] for a in abilities}
    assert any("Blazing Dance" in n for n in names)     # abilities are still listed (surfaced, not dropped)
    assert all(a["supported"] is False and a["total_dps"] == 0.0 for a in abilities)  # but contribute nothing
