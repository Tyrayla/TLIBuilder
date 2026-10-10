"""Ring of Blades behavior through the public engine_stats path.

Owner measurements (2026-10-08) and SS13 data are recorded in
.claude/plans/ring-of-blades-engine-brief.md. L16 base midpoint is 174.5;
with 5% spell crit at 150%, the expected hit is 174.5 * 1.025 = 178.8625.
At 0% speed, five blades hit at 5 * (1 / 2.0) = 2.5 hits/s, so naked DPS
is 178.8625 * 2.5 = 447.15625 before target mitigation.
"""
import pytest

from engine.affix_identity import affix_identity
from server import EngineStatsRequest, _get_skills_data, engine_stats
from persistence import season_manager
from tests.mock_build import make_request


_SKILL = "ring_of_blades"
_BLADE_FORMATION = "ring_of_blades_blade_formation_magnificent"
_RAZOR_EDGE = "ring_of_blades_razor_edge_noble"
_STRENGTH_IN_NUMBERS = "ring_of_blades_strength_in_numbers_noble"
_RAZOR_LINE = "+(4.6-4.8) % additional Projectile Speed for every channeled stack of the supported skill"
_RAZOR_ROLL = {affix_identity(_RAZOR_LINE): 0.046}


def _gear_with(**stats):
    return [{"item_name": "Ring of Blades test item", "contributions": [
        {"stat": key, "display_value": value, "unit": "", "slot": "ring",
         "item_name": "Ring of Blades test item", "text": f"+{value} {key}"}
        for key, value in stats.items()
    ]}]


def _support(item_id, *, rank=5, level=1, slot=1, **extra):
    skills = _get_skills_data(season_manager.get_active_season())
    return {"item_id": item_id, "skill_type": skills[item_id]["skill_type"],
            "rank": rank, "level": level, "slot": slot, "enabled": True, **extra}


def _offense(*, level=16, gear=None, supports=None, **extra):
    request = make_request(_SKILL, level, attached_supports=supports, gear=gear or [], **extra)
    response = engine_stats(EngineStatsRequest(**request))
    return response.model_dump() if hasattr(response, "model_dump") else response


def test_ring_of_blades_naked_rate_and_dps():
    result = _offense()
    offense = result["offense"]
    assert offense["supported"] is True
    assert offense["channeled_behavior"] == "refresh"
    assert offense["channeled_max_stacks"] == 5
    assert offense["skills_per_second"] == pytest.approx(1 / 0.333, rel=1e-3)
    form = offense["hit_forms"][0]
    assert form["avg_hit_pre_crit"] == pytest.approx(174.5)
    assert form["fires_per_sec"] == pytest.approx(2.5)
    assert form["hits_per_fire"] == 1
    assert form["shotgun_mult"] == pytest.approx(1.0)
    assert offense["total_dps"] == pytest.approx(447.15625, abs=0.01)


def test_added_flat_damage_uses_93_percent_effectiveness():
    offense = _offense(gear=_gear_with(
        physical_spell_dmg_flat_min=100.0, physical_spell_dmg_flat_max=100.0
    ))["offense"]
    # 100 added flat ? 93% effectiveness adds 93 to the 174.5 base midpoint.
    assert offense["hit_forms"][0]["avg_hit_pre_crit"] == pytest.approx(267.5)
    assert offense["total_dps"] == pytest.approx(685.46875, abs=0.01)


@pytest.mark.parametrize(("speed", "expected_rate", "expected_dps"), [
    (1.07, 5.175, 925.61),
    (0.53, 3.825, 684.15),
])
def test_projectile_speed_changes_orbit_rate_not_cast_rate(speed, expected_rate, expected_dps):
    offense = _offense(gear=_gear_with(projectile_speed_inc=speed))["offense"]
    form = offense["hit_forms"][0]
    assert offense["skills_per_second"] == pytest.approx(1 / 0.333, rel=1e-3)
    assert form["fires_per_sec"] == pytest.approx(expected_rate)
    assert offense["total_dps"] == pytest.approx(expected_dps, abs=0.01)


def test_area_and_cast_speed_do_not_change_orbit_rate():
    base = _offense()["offense"]
    changed = _offense(gear=_gear_with(skill_area_inc=0.54, area_dmg_inc=5.0, cast_speed_inc=5.0))["offense"]
    assert changed["skills_per_second"] == pytest.approx(base["skills_per_second"] * 6.0, rel=1e-3)
    assert changed["hit_forms"][0]["fires_per_sec"] == pytest.approx(2.5)
    assert changed["total_dps"] == pytest.approx(447.15625, abs=0.01)


def test_projectile_quantity_adds_blades_only_with_blade_formation():
    plain = _offense(gear=_gear_with(projectile_quantity_flat=2))["offense"]
    formed = _offense(gear=_gear_with(projectile_quantity_flat=2),
                      supports=[_support(_BLADE_FORMATION)])["offense"]
    assert plain["hit_forms"][0]["fires_per_sec"] == pytest.approx(2.5)
    assert plain["total_dps"] == pytest.approx(447.15625, abs=0.01)
    # Blade Formation rank 5 adds its separate 20% rank factor and its 29% tier-1 roll.
    assert formed["hit_forms"][0]["fires_per_sec"] == pytest.approx(3.5)
    assert formed["total_dps"] == pytest.approx(626.01875 * 1.2 * 1.29, abs=0.01)


def test_blade_formation_quantity_cap_is_seven_extra_blades():
    offense = _offense(gear=_gear_with(projectile_quantity_flat=10),
                       supports=[_support(_BLADE_FORMATION)])["offense"]
    assert offense["hit_forms"][0]["fires_per_sec"] == pytest.approx(6.0)
    assert offense["total_dps"] == pytest.approx(1073.175 * 1.2 * 1.29, abs=0.02)


def test_projectile_speed_hit_gate_caps_each_blade_at_four_hits_per_second():
    offense = _offense(gear=_gear_with(projectile_speed_inc=8.0))["offense"]
    assert offense["hit_forms"][0]["fires_per_sec"] == pytest.approx(20.0)
    assert offense["total_dps"] == pytest.approx(3577.25, abs=0.02)


def test_razor_edge_speed_is_summed_within_one_slot_local_source():
    offense = _offense(supports=[_support(_RAZOR_EDGE, specific_rolls=_RAZOR_ROLL)])["offense"]
    assert offense["hit_forms"][0]["fires_per_sec"] == pytest.approx(3.075)
    assert offense["total_dps"] == pytest.approx(447.15625 * 1.23 * 1.2, abs=0.01)


def test_razor_edge_projectile_speed_does_not_leak_to_another_skill_slot():
    razor = _support(_RAZOR_EDGE, specific_rolls=_RAZOR_ROLL)
    request = make_request(_SKILL, 16, attached_supports=[razor], gear=[])
    request["skills"] = [
        {"slot": 1, "skill_id": _SKILL, "level": 16},
        {"slot": 2, "skill_id": "chain_lightning", "level": 14},
    ]
    response = engine_stats(EngineStatsRequest(**request))
    result = response.model_dump() if hasattr(response, "model_dump") else response
    control = engine_stats(EngineStatsRequest(**make_request("chain_lightning", 14)))
    control = control.model_dump() if hasattr(control, "model_dump") else control
    assert result["slot_offense"]["1"]["hit_forms"][0]["fires_per_sec"] == pytest.approx(3.075)
    assert result["slot_offense"]["2"]["total_dps"] == pytest.approx(control["offense"]["total_dps"])


def test_razor_edge_and_additional_max_stacks_scale_rate_and_damage_but_not_blades():
    offense = _offense(gear=_gear_with(max_channeled_stacks_flat=5),
                       supports=[_support(_RAZOR_EDGE, specific_rolls=_RAZOR_ROLL)])["offense"]
    assert offense["channeled_max_stacks"] == 10
    assert offense["hit_forms"][0]["fires_per_sec"] == pytest.approx(3.65)
    assert offense["total_dps"] == pytest.approx(1625.59, abs=0.02)


def test_one_extra_max_channeled_stack_adds_damage_without_adding_blades():
    base = _offense()["offense"]
    extra = _offense(gear=_gear_with(max_channeled_stacks_flat=1))["offense"]
    assert extra["channeled_max_stacks"] == 6
    assert extra["hit_forms"][0]["fires_per_sec"] == pytest.approx(2.5)
    assert extra["total_dps"] == pytest.approx(base["total_dps"] * 1.215, abs=0.01)


def test_strength_in_numbers_damage_lines_apply_and_minion_line_stays_nyi():
    base = _offense()["offense"]["total_dps"]
    supported = _offense(supports=[_support(_STRENGTH_IN_NUMBERS)])
    # Its separate +20% rank line and -33.5% tier-1 line multiply. Minion projectiles do not affect this hit rate.
    assert supported["offense"]["total_dps"] == pytest.approx(base * 1.2 * 0.665, abs=0.01)
    assert supported["offense"]["hit_forms"][0]["fires_per_sec"] == pytest.approx(2.5)
    from engine.coverage import skill_coverage
    data = _get_skills_data(season_manager.get_active_season())[_STRENGTH_IN_NUMBERS]
    coverage, detail = skill_coverage(data)
    assert coverage == "partial"
    assert any("Minions" in line and "Projectiles" in line for line in detail)

