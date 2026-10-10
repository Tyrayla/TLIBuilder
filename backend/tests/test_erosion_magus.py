"""Erosion Magus forms and source-backed damage delivery."""
import json

import pytest

from engine.models import BuildSource, SourceEntry
from engine.minion_offense import MINION_MODULES
from persistence import season_manager


def _owner():
    skills = json.load(open(season_manager._season_dir("SS14") + "/_skills.json", encoding="utf-8"))["skills"]
    return next(skill for skill in skills if skill["item_id"] == "summon_erosion_magus")


def _forms(result):
    return {form.name.split(" (")[0]: form for form in result.hit_forms}


def test_erosion_magus_reports_default_damage_and_separate_ultimate():
    import engine.minion_effects  # noqa: F401 -- populate MINION_MODULES

    owner = _owner()
    base_stats = season_manager.load_minion_base_stats("SS14")
    result = MINION_MODULES[owner["item_id"]](BuildSource(), owner, base_stats, 20, 1)
    forms = {form.name.split(" (")[0]: form for form in result.hit_forms}

    # Canonical SS14 shared Base Damage is 300; Scattered Mud is 100% per cast.
    assert forms["Scattered Mud"].avg_hit_pre_crit == pytest.approx(300.0)
    # World of Thorns is 2298% = 300 * 22.98 = 6894 per cast, one hit per enemy.
    assert forms["World of Thorns"].avg_hit_pre_crit == pytest.approx(6894.0)
    assert forms["World of Thorns"].hits_per_fire == 1
    assert forms["World of Thorns"].fires_per_sec == 0.0
    assert forms["World of Thorns"].base_cast_time == pytest.approx(1.5)
    assert forms["World of Thorns"].base_cooldown == pytest.approx(8.0)
    assert forms["World of Thorns"].effective_cast_time == pytest.approx(1.5)
    assert forms["World of Thorns"].effective_cooldown == pytest.approx(8.0)
    assert forms["Scattered Mud"].effective_cast_time == pytest.approx(0.8)
    assert forms["Bleak Grass"].base_cast_time == pytest.approx(0.8)
    assert forms["Withering Payback"].effective_cast_time == pytest.approx(0.6)
    assert forms["Withering Payback"].effective_cooldown == pytest.approx(10.0)
    assert result.total_dps == pytest.approx(forms["Scattered Mud"].dps_contribution)


def test_bleak_grass_uses_level_effectiveness_and_owner_hit_counts():
    import engine.minion_effects  # noqa: F401 -- populate MINION_MODULES

    owner = _owner()
    source = BuildSource()
    source.add("spirit_magi_initial_growth_flat", 100.0)  # Stage 2: +30% Enhanced replacement chance.
    source.add("minion_physical_dmg_flat_min", 100.0)
    source.add("minion_physical_dmg_flat_max", 100.0)
    result = MINION_MODULES[owner["item_id"]](
        source, owner, season_manager.load_minion_base_stats("SS14"), 1, 1,
        condition_state={"enemy_count_weight": 1.0})
    forms = {form.name.split(" (")[0]: form for form in result.hit_forms}

    # L1 Bleak Grass is 108%; added physical flat follows that same per-level effectiveness,
    # then its 100% owner conversion routes the flat to Erosion. Base hit is 10*108%.
    assert forms["Bleak Grass"].avg_hit_pre_crit == pytest.approx((10.0 + 100.0) * 1.08)
    assert forms["Bleak Grass"].hits_per_fire == 2  # spike + explosion; full damage, zero falloff.
    assert forms["Bleak Grass"].shotgun_mult == pytest.approx(2.0)
    assert forms["Bleak Grass"].shotgun_falloff == 0.0
    # Thunder's owner-confirmed Empower cast-slot pattern applies its calibrated half-cast efficiency.
    assert forms["Bleak Grass"].fires_per_sec == pytest.approx(0.30 / 0.8 * (1.0 - 0.5 * 0.6 / 10.0))


def test_gold_rush_empower_effect_uses_enemy_type_weight_and_uptime():
    import engine.minion_effects  # noqa: F401 -- populate MINION_MODULES

    owner = _owner()
    base_stats = season_manager.load_minion_base_stats("SS14")
    module = MINION_MODULES[owner["item_id"]]
    normal = module(BuildSource(), owner, base_stats, 20, 1, condition_state={"enemy_count_weight": 1.0})
    boss = module(BuildSource(), owner, base_stats, 20, 1, condition_state={"enemy_count_weight": 5.0})

    assert normal.minion_empower["uptime"] == pytest.approx(0.6)  # six seconds / ten seconds
    assert normal.minion_empower["empower_effect"] == pytest.approx(1.0)
    # Stage 1 does not unlock Gold Rush; confirm the boss branch remains inactive below Stage 4.
    assert boss.minion_empower["empower_effect"] == pytest.approx(1.0)
    stage4_source = BuildSource()
    stage4_source.add("spirit_magi_initial_growth_flat", 300.0)
    stage4 = module(stage4_source, owner, base_stats, 20, 1, condition_state={"enemy_count_weight": 5.0})
    assert stage4.minion_empower["empower_effect"] == pytest.approx(2.2)
    assert stage4.minion_empower["buffs"][0]["value"] == pytest.approx(0.20 * 2.2 * 0.6)
    assert _forms(stage4)["Bleak Grass"].hits_per_fire == 4  # Stage 4 extra spike assumption, no extra cast.


def test_harvest_time_makes_empower_cast_instant():
    import engine.minion_effects  # noqa: F401 -- populate MINION_MODULES

    owner = _owner()
    source = BuildSource()
    source.source_log.append(SourceEntry(stat="minion_cast_speed_inc", amount=0.0,
                                         source_type="support", label="Harvest Time",
                                         source_name="Harvest Time", text="Harvest Time"))
    result = MINION_MODULES[owner["item_id"]](
        source, owner, season_manager.load_minion_base_stats("SS14"), 20, 1)
    empower = _forms(result)["Withering Payback"]
    assert empower.base_cast_time == pytest.approx(0.6)
    assert empower.effective_cast_time == 0.0
