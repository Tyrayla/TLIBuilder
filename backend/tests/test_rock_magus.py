"""Rock Magus ability forms use the sourced SS13 coefficients and timings."""
from engine.models import BuildSource
import pytest


def _owner():
    return {
        "name": "Summon Rock Magus",
        "minion_skills": [
            {"name": "Shattered Stone", "skill_tags": ["Base Skill", "Attack", "Physical"],
             "cast_speed": "0.8 s", "effectiveness_of_added_damage": "107%",
             "base_damage_coefficient": {"1": 1.07}},
            {"name": "Rock Blast", "skill_tags": ["Enhanced Skill", "Attack", "Physical"],
             "cast_speed": "0.4 s", "effectiveness_of_added_damage": "31%",
             "base_damage_coefficient": {"1": 0.31}},
            {"name": "Gold Rush", "skill_tags": ["Empower", "Attack", "Physical"],
             "cast_speed": "0.6 s", "cooldown": "10 s", "duration": 6.0},
            {"name": "Towering Mountains", "skill_tags": ["Ultimate", "Attack", "Physical"],
             "cast_speed": "1.5 s", "cooldown": "8 s",
             "base_damage_coefficient": {"1": 1.52}},
        ],
    }


def test_rock_magus_shares_base_and_enhanced_cadence_and_reports_hits():
    import engine.minion_effects  # noqa: F401
    from engine.minion_offense import MINION_MODULES

    # SS13 data: Shattered Stone 0.8 s; Rock Blast 0.4 s and three strikes per use.
    result = MINION_MODULES["summon_rock_magus"](
        BuildSource(), _owner(), {"base_damage_by_level": {"1": 10}}, 1, 1,
    )
    forms = {form.name: form for form in result.hit_forms}
    # Gold Rush takes 0.6 s from each 10 s cooldown; Thunder Magus's calibrated 50% cast-slot overlap
    # gives 1 - 0.5 × (0.6 / 10) = 0.97 of the attack time.
    assert forms["Shattered Stone (Base)"].fires_per_sec == pytest.approx(1.25 * 0.97)
    assert forms["Shattered Stone (Base)"].hits_per_fire == 1
    assert forms["Rock Blast (Enhanced)"].fires_per_sec == 0.0
    assert forms["Rock Blast (Enhanced)"].hits_per_fire == 3
    assert forms["Gold Rush (Empower)"].nyi
    assert result.minion_ultimate["hits_per_cast"] == 2
    assert result.minion_ultimate["base_cast_time"] == 1.5
    assert result.minion_ultimate["base_cooldown"] == 8.0
    assert result.minion_ultimate["included_in_default_dps"] is False
    assert set(result.minion_skill_casts) == {"base", "enhanced", "empower", "ultimate"}
    assert result.minion_skill_casts["base"]["included_in_default_dps"] is False
    assert result.minion_skill_casts["enhanced"]["hits_per_cast"] == 3
    assert result.minion_skill_casts["ultimate"]["hits_per_cast"] == 2
    assert result.minion_skill_casts["empower"]["damage_per_cast"] == 0
    assert result.minion_skill_casts["base"]["casts_per_second"] == pytest.approx(1.25)
    assert result.minion_skill_casts["enhanced"]["casts_per_second"] == pytest.approx(2.5)
    assert result.minion_skill_casts["ultimate"]["casts_per_second"] == pytest.approx(0.125)
    assert result.minion_skill_casts["ultimate"]["name"] == "Towering Mountains (Ultimate)"
    assert "Towering Mountains (Ultimate)" not in [form.name for form in result.hit_forms]
    from dataclasses import asdict
    ultimate = asdict(result)["minion_skill_casts"]["ultimate"]["hit_breakdown"]
    assert ultimate["hit_forms"][0]["name"] == "Towering Mountains (Ultimate)"
    assert ultimate["hit_forms"][0]["hits_per_fire"] == 2
    assert ultimate["total_dps"] == pytest.approx(ultimate["hit_forms"][0]["dps_contribution"])
    assert ultimate["damage_rows"][0]["dps_vs_target_final"] == pytest.approx(ultimate["total_dps_vs_target"])
    assert any(
        source["label"] == "Towering Mountains"
        for source in ultimate["stat_map"]["minion_dmg_additional"]["sources"]
    )


def test_rock_magus_per_cast_template_does_not_change_unmerged_output_for_count_two():
    import engine.minion_effects  # noqa: F401
    from engine.minion_offense import MINION_MODULES

    handler = MINION_MODULES["summon_rock_magus"]
    base_stats = {"base_damage_by_level": {"1": 10}}
    one = handler(BuildSource(), _owner(), base_stats, 1, 1)
    two = handler(BuildSource(), _owner(), base_stats, 1, 2)

    # The task only needs a unit-count reusable template; ordinary Rock rotation DPS remains unchanged here.
    assert one.total_dps == pytest.approx(0.13776825125)
    assert two.total_dps == pytest.approx(0.13776825125)
    assert two.total_dps_vs_target == pytest.approx(one.total_dps_vs_target)
    assert two.minion_skill_casts["base"]["damage_per_cast"] == pytest.approx(
        one.minion_skill_casts["base"]["damage_per_cast"],
    )
    assert two.minion_skill_forms["base skill"].total_dps == pytest.approx(
        one.minion_skill_forms["base skill"].total_dps,
    )


def test_rock_magus_ultimate_reads_spirit_magus_cdr_and_tango_zeroes_merged_cooldown():
    import engine.minion_effects  # noqa: F401
    from engine.minion_offense import MINION_MODULES

    handler = MINION_MODULES["summon_rock_magus"]
    base_stats = {"base_damage_by_level": {"1": 10}}
    source = BuildSource()
    source.add("spirit_magi_cdr_speed_inc", 0.5)
    result = handler(source, _owner(), base_stats, 1, 1)
    assert result.minion_skill_casts["ultimate"]["cooldown"] == pytest.approx(8 / 1.5)

    source.condition_state = {"whirlwind_tango_merged": True}
    tango = handler(source, _owner(), base_stats, 1, 1)
    assert tango.minion_skill_casts["ultimate"]["cooldown"] == 0
    assert tango.minion_skill_casts["ultimate"]["casts_per_second"] == pytest.approx(
        1 / tango.minion_skill_casts["ultimate"]["cast_time"],
    )


def test_rock_magus_enhanced_per_cast_target_damage_counts_its_three_hits_once():
    import engine.minion_effects  # noqa: F401
    from engine.minion_offense import MINION_MODULES

    source = BuildSource()
    source.add("spirit_magi_initial_growth_flat", 100)
    owner = _owner()
    owner["minion_skills"] = [skill for skill in owner["minion_skills"] if skill["name"] != "Gold Rush"]
    result = MINION_MODULES["summon_rock_magus"](
        source, owner, {"base_damage_by_level": {"1": 10}}, 1, 1,
    )
    enhanced = next(form for form in result.hit_forms if form.name == "Rock Blast (Enhanced)")
    assert enhanced.fires_per_sec > 0
    assert enhanced.hits_per_fire == 3
    assert result.minion_skill_casts["enhanced"]["damage_per_cast_vs_target"] == pytest.approx(
        enhanced.dps_vs_target / enhanced.fires_per_sec,
    )


def test_rock_magus_growth_stage_two_splits_replacement_casts():
    import engine.minion_effects  # noqa: F401
    from engine.minion_offense import MINION_MODULES

    # Help DB: Stage 2 adds 30 percentage points Enhanced chance. Enhanced replaces Base.
    source = BuildSource()
    source.add("spirit_magi_initial_growth_flat", 100)
    result = MINION_MODULES["summon_rock_magus"](
        source, _owner(), {"base_damage_by_level": {"1": 10}}, 1, 1,
    )
    forms = {form.name: form for form in result.hit_forms}
    assert result.spirit_magi_growth == 200
    assert result.spirit_magi_enhanced_chance == 0.30
    assert forms["Shattered Stone (Base)"].fires_per_sec == pytest.approx(1.25 * 0.70 * 0.97)
    assert forms["Rock Blast (Enhanced)"].fires_per_sec == pytest.approx(2.5 * 0.30 * 0.97)
    assert forms["Rock Blast (Enhanced)"].hits_per_fire == 3


def test_rock_blast_uses_existing_enemy_count_weight_for_stage_three_bonus():
    import engine.minion_effects  # noqa: F401
    from engine.minion_offense import MINION_MODULES

    # The existing Enemy condition maps Normal=1 and Rare=2. Rock Blast adds 3.5% per enemy at Stage 3.
    normal = BuildSource()
    rare = BuildSource()
    for source in (normal, rare):
        source.add("spirit_magi_initial_growth_flat", 200)
    normal.condition_state = {"enemy_count_weight": 1}
    rare.condition_state = {"enemy_count_weight": 2}
    handler = MINION_MODULES["summon_rock_magus"]
    base_stats = {"base_damage_by_level": {"1": 10}}
    owner = _owner()
    owner["minion_skills"] = [skill for skill in owner["minion_skills"] if skill["name"] != "Gold Rush"]
    n = {f.name: f for f in handler(normal, owner, base_stats, 1, 1).hit_forms}
    r = {f.name: f for f in handler(rare, owner, base_stats, 1, 1).hit_forms}
    # Without Empower, only Rock Blast changes: +7% vs +3.5% additional damage.
    assert (r["Rock Blast (Enhanced)"].avg_hit_with_crit
            / n["Rock Blast (Enhanced)"].avg_hit_with_crit) == pytest.approx(1.07 / 1.035)


def test_gold_rush_stage_four_boss_uses_existing_enemy_selector_for_empower_effect():
    import engine.minion_effects  # noqa: F401
    from engine.minion_offense import MINION_MODULES

    source = BuildSource()
    source.add("spirit_magi_initial_growth_flat", 300)
    source.condition_state = {"enemy_count_weight": 5}
    result = MINION_MODULES["summon_rock_magus"](
        source, _owner(), {"base_damage_by_level": {"1": 10}}, 1, 1,
    )
    assert result.minion_empower["empower_effect"] == pytest.approx(2.2)
    assert result.minion_empower["uptime"] == pytest.approx(0.6)
    # Gold Rush: 6% × 5 enemies × 2.2 Empower Effect × 60% uptime = a 1.396 damage multiplier.
    # It multiplies Rock Blast's independently applied Stage 3+ per-enemy bonus.
    enhanced = next(form for form in result.hit_forms if form.name == "Rock Blast (Enhanced)")
    no_empower_owner = _owner()
    no_empower_owner["minion_skills"] = [s for s in no_empower_owner["minion_skills"] if s["name"] != "Gold Rush"]
    no_empower = MINION_MODULES["summon_rock_magus"](
        source, no_empower_owner, {"base_damage_by_level": {"1": 10}}, 1, 1,
    )
    enhanced_without_gold_rush = next(f for f in no_empower.hit_forms if f.name == "Rock Blast (Enhanced)")
    assert enhanced.avg_hit_with_crit / enhanced_without_gold_rush.avg_hit_with_crit == pytest.approx(
        1.396,
    )
    assert (result.minion_skill_casts["enhanced"]["damage_per_cast"]
            == no_empower.minion_skill_casts["enhanced"]["damage_per_cast"])


def test_rock_magus_harvest_time_makes_empower_instant_and_restores_attack_slot():
    import engine.minion_effects  # noqa: F401
    from engine.minion_offense import MINION_MODULES

    handler = MINION_MODULES["summon_rock_magus"]
    base_stats = {"base_damage_by_level": {"1": 10}}
    normal = handler(BuildSource(), _owner(), base_stats, 1, 1)

    linked_source = BuildSource()
    linked_source.condition_state = {"_engine_harvest_time_linked": True}
    linked = handler(linked_source, _owner(), base_stats, 1, 1)

    # Gold Rush normally pays 0.6 s of the 10 s cycle: 1 - 0.5 * 0.6 / 10 = 0.97.
    assert normal.minion_empower["cast_slot_factor"] == 0.97
    assert normal.minion_skill_casts["empower"]["cast_time"] == 0.6
    assert linked.minion_empower["cast_slot_factor"] == 1.0
    assert linked.minion_skill_casts["empower"]["cast_time"] == 0.0


def test_rock_magus_handler_accepts_shared_condition_state_and_legacy_calls():
    import engine.minion_effects  # noqa: F401
    from engine.minion_offense import MINION_MODULES

    handler = MINION_MODULES["summon_rock_magus"]
    base_stats = {"base_damage_by_level": {"1": 10}}
    owner = _owner()
    source = BuildSource()
    source.add("spirit_magi_initial_growth_flat", 300)
    source.condition_state = {"enemy_count_weight": 1}

    # Existing direct callers omit the keyword and retain the source's Normal enemy state.
    legacy = handler(source, owner, base_stats, 1, 1)
    assert legacy.minion_empower["empower_effect"] == pytest.approx(1.0)
    assert legacy.minion_empower["cast_slot_factor"] == pytest.approx(0.97)

    # The shared compute caller passes its current Boss and Harvest Time state explicitly.
    shared = handler(
        source, owner, base_stats, 1, 1,
        condition_state={"enemy_count_weight": 5, "_engine_harvest_time_linked": True},
    )
    assert shared.minion_empower["empower_effect"] == pytest.approx(2.2)
    assert shared.minion_empower["cast_slot_factor"] == pytest.approx(1.0)
    assert shared.minion_skill_casts["empower"]["cast_time"] == 0.0


def test_rock_magus_towering_mount_whole_attack_speed_step_avoids_float_truncation():
    from engine.minion_effects.rock_magus import _whole_attack_speed_percent_steps

    # Towering Mountains counts whole increased Attack Speed points; 0.29 is 29 steps
    # despite its binary float product being represented just below 29 on some platforms.
    assert _whole_attack_speed_percent_steps(0.29) == 29
    assert _whole_attack_speed_percent_steps(0.299) == 29
    assert _whole_attack_speed_percent_steps(0.30) == 30
