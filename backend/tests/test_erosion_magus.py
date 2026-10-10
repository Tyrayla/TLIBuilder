"""Erosion Magus forms and source-backed damage delivery."""
import json

import pytest

from engine.models import BuildInput, BuildSource
from engine.minion_offense import MINION_MODULES
from engine.compute import compute
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
    assert forms["Scattered Mud"].avg_hit_pre_crit == pytest.approx(336.0)  # +20% Empower buff × 60% uptime.
    # World of Thorns is 2298% = 300 * 22.98 = 6894 per cast, one hit per enemy.
    assert forms["World of Thorns"].avg_hit_pre_crit == pytest.approx(6894.0 * 1.12)
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
    source.add("minion_dmg_inc", 0.10)
    source.add("minion_physical_dmg_inc", 0.20)
    source.add("minion_erosion_dmg_inc", 0.50)
    source.add("minion_dmg_additional", 0.10)
    source.add("minion_physical_dmg_additional", 0.20)
    source.add("minion_at_center_dmg_additional", 0.25)
    result = MINION_MODULES[owner["item_id"]](
        source, owner, season_manager.load_minion_base_stats("SS14"), 1, 1,
        condition_state={"enemy_count_weight": 1.0})
    forms = {form.name.split(" (")[0]: form for form in result.hit_forms}

    # Native Erosion and converted Physical packets retain their own conversion-path modifiers.
    # Physical has both Physical and Erosion bonuses after the owner conversion; shared bonuses apply once.
    withering_additional = 1.0 + (0.20 * 0.60)
    native_erosion = 10.0 * 1.08 * 1.6 * 1.1 * withering_additional * 1.25
    converted_physical = 100.0 * 1.08 * 1.8 * 1.1 * 1.2 * withering_additional * 1.25
    assert forms["Bleak Grass"].avg_hit_pre_crit == pytest.approx(native_erosion + converted_physical)
    assert forms["Bleak Grass"].hits_per_fire == 2  # spike + explosion; full damage, zero falloff.
    assert forms["Bleak Grass"].shotgun_mult == pytest.approx(2.0)
    assert forms["Bleak Grass"].shotgun_falloff == 0.0
    # No cast-slot penalty is applied without a sourced Erosion-specific rotation rule.
    assert forms["Bleak Grass"].fires_per_sec == pytest.approx(0.30 / 0.8)


def test_gold_rush_empower_effect_uses_enemy_type_weight_and_uptime():
    import engine.minion_effects  # noqa: F401 -- populate MINION_MODULES

    owner = _owner()
    base_stats = season_manager.load_minion_base_stats("SS14")
    module = MINION_MODULES[owner["item_id"]]
    missing_condition = module(BuildSource(), owner, base_stats, 20, 1)
    normal = module(BuildSource(), owner, base_stats, 20, 1, condition_state={"enemy_count_weight": 1.0})
    boss = module(BuildSource(), owner, base_stats, 20, 1, condition_state={"enemy_count_weight": 5.0})

    assert normal.minion_empower["uptime"] == pytest.approx(0.6)  # six seconds / ten seconds
    assert normal.minion_empower["empower_effect"] == pytest.approx(1.0)
    assert missing_condition.minion_empower["empower_effect"] == pytest.approx(1.0)
    # Stage 1 does not unlock Gold Rush; confirm the boss branch remains inactive below Stage 4.
    assert boss.minion_empower["empower_effect"] == pytest.approx(1.0)
    stage4_source = BuildSource()
    stage4_source.add("spirit_magi_initial_growth_flat", 300.0)
    stage4 = module(stage4_source, owner, base_stats, 20, 1, condition_state={"enemy_count_weight": 5.0})
    stage4_default_enemy = module(stage4_source, owner, base_stats, 20, 1)
    assert stage4.minion_empower["empower_effect"] == pytest.approx(2.2)
    # This module defaults an unspecified enemy to Normal; Gold Rush is boss-only.
    assert stage4_default_enemy.minion_empower["empower_effect"] == pytest.approx(1.0)
    assert stage4.minion_empower["buffs"][0]["value"] == pytest.approx(0.20 * 2.2 * 0.6)
    assert stage4.minion_empower["buffs"][1]["value"] == pytest.approx(0.50 * 2.2 * 0.6)
    assert stage4.minion_empower["buffs"][1]["active"] is True
    assert stage4_default_enemy.minion_empower["buffs"][1]["value"] == pytest.approx(0.50 * 0.6)
    assert _forms(stage4)["Bleak Grass"].hits_per_fire == 2  # Extra spike input defaults off.
    selected_spike = module(stage4_source, owner, base_stats, 20, 1, condition_state={
        "enemy_count_weight": 5.0, "erosion_stage4_extra_spike": True,
    })
    assert _forms(selected_spike)["Bleak Grass"].hits_per_fire == pytest.approx(2.6)


def test_harvest_time_makes_empower_cast_instant():
    import engine.minion_effects  # noqa: F401 -- populate MINION_MODULES

    owner = _owner()
    source = BuildSource()
    result = MINION_MODULES[owner["item_id"]](
        source, owner, season_manager.load_minion_base_stats("SS14"), 20, 1,
        condition_state={"_engine_harvest_time_linked": True})
    empower = _forms(result)["Withering Payback"]
    assert empower.base_cast_time == pytest.approx(0.6)
    assert empower.effective_cast_time == 0.0


def test_ultimate_per_cast_cooldown_uses_minion_and_spirit_magus_recovery():
    import engine.minion_effects  # noqa: F401 -- populate MINION_MODULES

    owner = _owner()
    source = BuildSource()
    source.add("minion_cdr_speed_inc", 0.25)
    source.add("spirit_magi_cdr_speed_inc", 0.25)
    result = MINION_MODULES[owner["item_id"]](
        source, owner, season_manager.load_minion_base_stats("SS14"), 20, 1)
    ultimate = _forms(result)["World of Thorns"]
    assert ultimate.effective_cooldown == pytest.approx(8.0 / 1.5)
    assert ultimate.fires_per_sec == 0.0
    assert any("assumes casts sample the Empower window" in note for note in ultimate.nyi)
    empower = _forms(result)["Withering Payback"]
    assert empower.effective_cooldown == pytest.approx(10.0 / 1.5)
    assert result.minion_empower["uptime"] == pytest.approx(0.9)
    assert result.minion_empower["cdr_inc"] == pytest.approx(0.5)
    assert result.minion_empower["duration_inc"] == 0.0


def test_negative_one_hundred_percent_spirit_magus_cdr_reports_zero_cooldown_with_note():
    import engine.minion_effects  # noqa: F401 -- populate MINION_MODULES

    owner = _owner()
    source = BuildSource()
    source.add("minion_cdr_speed_inc", -0.5)
    source.add("spirit_magi_cdr_speed_inc", -0.5)
    result = MINION_MODULES[owner["item_id"]](
        source, owner, season_manager.load_minion_base_stats("SS14"), 20, 1)
    empower = _forms(result)["Withering Payback"]
    ultimate = _forms(result)["World of Thorns"]
    assert result.minion_empower["cooldown"] == 0.0
    assert empower.effective_cooldown == 0.0
    assert ultimate.effective_cooldown == 0.0
    assert any("Empower cooldown recovery is at or below -100%" in note for note in empower.nyi)
    assert any("Ultimate cooldown recovery is at or below -100%" in note for note in ultimate.nyi)


def test_compute_passes_enemy_type_condition_to_registered_minion_handler():
    owner = _owner()
    # compute() expects normalized detail strings while the raw catalog uses structured records.
    owner["detailed_description"] = []
    owner["description_lines"] = []
    build = BuildInput(
        slots=[], slates=[], season="SS14", attached_supports=[{"item_id": "harvest_time", "slot": 2}],
        condition_state={"enemy_count_weight": 1.0, "erosion_stage4_extra_spike": True},
        custom_contributions=[{"stat_key": "spirit_magi_initial_growth_flat", "amount": 300.0,
                               "text": "Integration test Growth"}],
    )
    result = compute(
        build, {}, {}, skills_input=[{"skill_id": owner["item_id"], "slot": 2, "level": 20}],
        skills_by_id={owner["item_id"]: owner})
    erosion = result.minion_offense[owner["item_id"]]
    assert erosion["minion_empower"]["empower_effect"] == pytest.approx(1.0)
    bleak_grass = next(form for form in erosion["hit_forms"] if form["name"].startswith("Bleak Grass"))
    assert bleak_grass["hits_per_fire"] == pytest.approx(2.6)
    assert next(form for form in erosion["hit_forms"] if form["name"].startswith("World of Thorns"))["fires_per_sec"] == 0.0
    assert next(form for form in erosion["hit_forms"] if form["name"].startswith("Withering Payback"))["effective_cast_time"] == 0.0


def test_growth_stage_four_ultimate_bonus_and_stage_five_damage_pool():
    import engine.minion_effects  # noqa: F401 -- populate MINION_MODULES

    owner = _owner()
    base_stats = season_manager.load_minion_base_stats("SS14")
    module = MINION_MODULES[owner["item_id"]]
    stage4 = BuildSource()
    stage4.add("spirit_magi_initial_growth_flat", 300.0)
    stage4_boss = module(stage4, owner, base_stats, 20, 1, condition_state={"enemy_count_weight": 5.0})
    assert _forms(stage4_boss)["World of Thorns"].avg_hit_pre_crit == pytest.approx(6894.0 * 1.264 * 1.66)

    stage5 = BuildSource()
    stage5.add("spirit_magi_initial_growth_flat", 400.0)
    result = module(stage5, owner, base_stats, 20, 1, condition_state={"enemy_count_weight": 1.0})
    assert _forms(result)["Scattered Mud"].avg_hit_pre_crit == pytest.approx(300.0 * 1.50 * 1.12)
