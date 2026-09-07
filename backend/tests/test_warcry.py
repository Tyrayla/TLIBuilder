import pytest

from engine.core_talent_resolver import _classify_effect
from engine.compute import compute
from engine.models import BuildSource
from engine.models import BuildInput
from engine.offense import calculate_offense
from engine.mod_parser import _parse_custom_mod_text
from engine.support_lines import SupportLine
from engine.support_mapper import map_via_parser
from engine.warcry import _CONTRIBUTIONS, apply_warcry_buffs, summarize_warcries
from engine.skill_resolver import resolve_skill
from server import _resolve_effect_modifiers, _resolve_gear_affix_clauses


def test_warcry_summary_uses_generic_and_warcry_timing_pools():
    source = BuildSource()
    source.add("warcry_effect_inc", 0.2)
    source.add("warcry_effect_additional", 0.2)
    source.add("cdr_speed_inc", 0.25)
    source.add("warcry_cdr_speed_inc", 0.25)
    source.add("cdr_speed_additional", 0.2)
    source.add("skill_effect_duration_inc", 0.1)
    source.add("duration_inc", 0.2)
    source.add("warcry_skill_effect_duration_inc", 0.2)
    source.add("skill_effect_duration_additional", 0.5)
    source.add("max_warcry_skill_charges_flat", 2)
    summaries = summarize_warcries(
        [{"skill_id": "raging_warcry", "slot": 2, "level": 20, "enabled": True}],
        {"raging_warcry": {"name": "Raging Warcry", "charges": 1, "skill_tags": ["Warcry"]}},
        source,
        {"warcry_power": 5, "formless_warcry_effects": True},
    )
    summary = summaries[0]
    assert summary["power"] == 5
    assert summary["power_base"] == 5
    assert summary["power_minimum"] == 0
    assert summary["power_cap"] == 16
    assert summary["warcry_effect"] == pytest.approx(0.44)
    assert summary["contributions"][0]["amount"] == pytest.approx(0.3564)
    assert summary["cooldown"] == pytest.approx(8 / 1.8)
    assert summary["duration"] == pytest.approx(3.5 * 1.5 * 1.5)
    assert summary["uptime"] == 1
    assert summary["max_charges"] == 3


def test_warcry_total_contribution_combines_base_power_and_effect():
    summary = summarize_warcries(
        [{"skill_id": "commanding_warcry", "slot": 1, "level": 20, "enabled": True}],
        {"commanding_warcry": {"name": "Commanding Warcry", "skill_tags": ["Warcry"]}},
        BuildSource(), {"warcry_power": 5},
    )[0]
    contribution = summary["contributions"][0]
    assert contribution["label"] == "Additional Minion Damage"
    assert contribution["base"] == pytest.approx(0.06)
    assert contribution["amount"] == pytest.approx(0.30)


def test_warcry_contributions_use_default_to_detailed_level_interpolation():
    source = BuildSource()
    skills = {"commanding_warcry": {"name": "Commanding Warcry", "skill_tags": ["Warcry"]}}
    level_one = summarize_warcries([{"skill_id": "commanding_warcry", "slot": 1, "level": 1}], skills, source, {"warcry_power": 1})[0]
    level_twenty = summarize_warcries([{"skill_id": "commanding_warcry", "slot": 1, "level": 20}], skills, source, {"warcry_power": 1})[0]
    assert level_one["contributions"][0]["amount"] == pytest.approx(0.041)
    assert level_twenty["contributions"][0]["amount"] == pytest.approx(0.06)


def test_charging_warcry_keeps_default_only_shadow_strike_effect():
    source = BuildSource()
    source.add("warcry_effect_inc", 0.50)
    summary = summarize_warcries(
        [{"skill_id": "charging_warcry", "slot": 1, "level": 20}],
        {"charging_warcry": {"name": "Charging Warcry", "skill_tags": ["Warcry"]}},
        source, {"warcry_power": 16},
    )[0]
    assert [c["label"] for c in summary["contributions"]] == [
        "Additional Shadow Strike Damage", "Additional Shadow Strike Ailment Damage", "Tracking Area",
    ]
    assert summary["contributions"][0]["amount"] == pytest.approx(0.96)
    # Tracking receives total Warcry Effect, but its tooltip has no per-enemy
    # term, so Warcry Power must not multiply it.
    assert summary["contributions"][2]["amount"] == pytest.approx(0.30)


def test_warcry_power_is_reserved_for_explicit_per_enemy_lines():
    power_scaled = {
        (skill_id, contribution["label"])
        for skill_id, contributions in _CONTRIBUTIONS.items()
        for contribution in contributions if contribution["per_power"]
    }
    assert power_scaled == {
        ("charging_warcry", "Additional Shadow Strike Damage"),
        ("charging_warcry", "Additional Shadow Strike Ailment Damage"),
        ("commanding_warcry", "Additional Minion Damage"),
        ("fearless_warcry", "Additional Slash-Strike Damage"),
        ("fearless_warcry", "Additional Slash-Strike Ailment Damage"),
        ("raging_warcry", "Additional Demolisher Damage"),
        ("raging_warcry", "Additional Demolisher Ailment Damage"),
        ("raging_warcry", "Demolisher Charge Recovery Speed"),
        ("resurrection_warcry", "Additional Damage Taken"),
        ("shockwave_warcry", "Additional Combo Finisher Damage"),
        ("shockwave_warcry", "Additional Combo Finisher Ailment Damage"),
    }


def test_warcry_power_defaults_and_manual_input_use_current_cap():
    skills = {"charging_warcry": {
        "item_id": "charging_warcry", "name": "Charging Warcry", "skill_tags": ["Warcry"],
    }}
    equipped = [{"skill_id": "charging_warcry", "slot": 1, "level": 20, "enabled": True}]

    def calculate(condition_state, *, formless=False):
        build = BuildInput(
            slots=[], slates=[], season="test", condition_state=condition_state,
            custom_contributions=[{"stat_key": "warcry_min_targets_flat", "amount": 20.0,
                                   "text": "Test minimum"}],
        )
        if formless:
            build.condition_state["formless_warcry_effects"] = True
        return compute(build, {}, {}, skills_input=equipped, skills_by_id=skills).warcry_summaries[0]

    # Automatic value: min(8, max(Boss 5, 20 minimum)) = 8.
    assert calculate({"enemy_count_weight": 5})["power"] == 8
    # Formless changes only the cap: min(16, max(5, 20)) = 16.
    assert calculate({"enemy_count_weight": 5}, formless=True)["power"] == 16
    # A manual value remains user-driven but is constrained to the same current cap.
    assert calculate({"enemy_count_weight": 5, "warcry_power": 99})["power"] == 8
    assert calculate({"enemy_count_weight": 5, "warcry_power": 99}, formless=True)["power"] == 16


def test_warcry_power_uses_the_actual_minimum_total_without_an_extra_base_point():
    skills = {"charging_warcry": {"name": "Charging Warcry", "skill_tags": ["Warcry"]}}
    result = compute(BuildInput(
        slots=[], slates=[], season="test", condition_state={"enemy_count_weight": 5},
        custom_contributions=[
            {"stat_key": "warcry_min_targets_flat", "amount": 4.0, "text": "First +4"},
            {"stat_key": "warcry_min_targets_flat", "amount": 4.0, "text": "Second +4"},
        ],
    ), {}, {}, skills_input=[{"skill_id": "charging_warcry", "slot": 1, "level": 20}], skills_by_id=skills)
    assert result.warcry_summaries[0]["power"] == 8


def test_resurrection_warcry_caps_the_final_total_contribution():
    source = BuildSource()
    source.add("warcry_effect_inc", 1.0)
    summary = summarize_warcries(
        [{"skill_id": "resurrection_warcry", "slot": 1, "level": 20}],
        {"resurrection_warcry": {"name": "Resurrection Warcry", "skill_tags": ["Warcry"]}},
        source, {"warcry_power": 16},
    )[0]
    contribution = summary["contributions"][0]
    assert contribution["minimum_amount"] == pytest.approx(-0.60)
    assert contribution["amount"] == pytest.approx(-0.60)


def test_warcry_duration_and_minimum_enemy_text_parse():
    parsed = _parse_custom_mod_text("+20% additional Warcry Skill Effect")
    assert parsed[0]["stat_key"] == "warcry_effect_additional"
    parsed = _parse_custom_mod_text("+13% Duration")
    assert parsed[0]["stat_key"] == "duration_inc"
    parsed = _parse_custom_mod_text("+15% Warcry Skill Effect Duration")
    assert parsed[0]["stat_key"] == "warcry_skill_effect_duration_inc"
    parsed = _parse_custom_mod_text("+4 to the minimum number of enemies affected by Warcry")
    assert parsed[0]["stat_key"] == "warcry_min_targets_flat"
    # Kragol's Roar is a timed, per-distinct-cast effect; it must not become a
    # permanent minimum until that independent state mechanic is modeled.
    assert _parse_custom_mod_text(
        "For each different Warcry cast, +4 to the minimum number of enemies affected by Warcry for 8 s") == []


def test_captain_kitty_additional_warcry_effect_resolves():
    contributions = _resolve_effect_modifiers(
        "Immediately casts Warcry. +20% additional Warcry Skill Effect", is_memory=False)
    assert [(c["stat_key"], c["amount"]) for c in contributions] == [
        ("warcry_effect_additional", 0.2),
    ]


def test_extended_duration_support_maps_to_generic_duration():
    line = SupportLine(
        text="+13% Duration for the supported skill",
        template="+# % duration for the supported skill",
        scaling=True,
        tier_values={1: "13", 20: "22.5"},
    )
    contribution = map_via_parser(line, 20)[0]
    assert contribution.stat_key == "duration_inc"
    assert contribution.amount == pytest.approx(0.225)


def test_formless_core_talent_is_a_flag():
    result = _classify_effect("Doubles Max Warcry Skill Effects", lambda _text: [], lambda _text: None)
    assert result == {"kind": "flag", "flag": "formless_warcry_effects"}
    area = _classify_effect("+66% Warcry Skill Area", _parse_custom_mod_text, lambda _text: None)
    assert area["contribs"][0]["stat_key"] == "warcry_skill_area_inc"


def test_warcry_uses_cast_rate_and_warcry_skill_area():
    source = BuildSource()
    source.add("warcry_skill_area_inc", 0.66)
    skill = resolve_skill({
        "item_id": "charging_warcry", "name": "Charging Warcry", "skill_tags": ["Warcry", "Area"],
        "cast_speed": "0.8 s", "max_level": 20,
    })
    offense = calculate_offense(source, skill, 20)
    assert offense.skills_per_second == pytest.approx(1.25)
    assert offense.skill_area_inc == pytest.approx(0.66)


def test_warcry_buffs_enter_their_existing_scoped_and_global_pools():
    source = BuildSource()
    skills = {"charging_warcry": {"name": "Charging Warcry", "skill_tags": ["Warcry"]}}
    equipped = [{"skill_id": "charging_warcry", "slot": 1, "level": 20}]
    _, restoration, conflict = apply_warcry_buffs(
        equipped, skills, source,
        {"warcry_power": 5, "shockwave_warcry_combo_finisher_stacks": 5}, "full")

    assert source.materialize_for_skill({"shadow strike"}).total("dmg_additional") == pytest.approx(0.20)
    assert source.materialize_for_skill({"shadow strike"}).total("ailment_dmg_additional") == pytest.approx(0.20)
    assert source.materialize_for_skill({"shadow strike"}).total("shadow_strike_tracking_area_inc") == pytest.approx(0.20)
    assert restoration == []
    assert conflict is None


def test_shadow_tracking_distance_is_separate_from_skill_area_and_uses_warcry_contribution():
    source = BuildSource()
    source.add("shadow_strike_tracking_area_inc", 0.60)
    skill = resolve_skill({
        "item_id": "shadow_test", "name": "Shadow Test", "skill_tags": ["Attack", "Shadow Strike", "Area"],
    })
    offense = calculate_offense(source, skill, 20)
    assert offense.shadow_tracking_area_inc == pytest.approx(0.60)
    assert offense.shadow_tracking_distance == pytest.approx(15.2)
    assert offense.skill_area_inc == pytest.approx(0.0)


def test_resurrection_restoration_uses_cooldown_and_generic_duration_only():
    source = BuildSource()
    source.add("duration_inc", 0.25)
    source.add("skill_effect_duration_inc", 0.50)
    source.add("warcry_skill_effect_duration_inc", 1.0)
    source.add("warcry_effect_inc", 1.0)
    _, restoration, conflict = apply_warcry_buffs(
        [{"skill_id": "resurrection_warcry", "slot": 1, "level": 20}],
        {"resurrection_warcry": {"name": "Resurrection Warcry", "skill_tags": ["Warcry"],
                                  "progression": [{"level": 20, "values": {"life_restore": 1160}}]}},
        source, {"warcry_power": 16}, "real")

    assert len(restoration) == 1
    assert conflict is None
    assert restoration[0]["base_amount"] == 1160
    assert restoration[0]["window"] == pytest.approx(7.0)
    assert restoration[0]["recast"] == pytest.approx(8.0)
    # Warcry-specific duration makes the persistent mitigation full uptime, but
    # intentionally does not extend the separate restoration window above.
    assert source.total("dmg_taken_additional") == pytest.approx(-0.60)


def test_distinct_warcries_apply_together_without_a_conflict():
    source = BuildSource()
    skills = {
        "charging_warcry": {"name": "Charging Warcry", "skill_tags": ["Warcry"]},
        "commanding_warcry": {"name": "Commanding Warcry", "skill_tags": ["Warcry"]},
    }
    equipped = [{"skill_id": "charging_warcry", "slot": 1, "level": 20},
                {"skill_id": "commanding_warcry", "slot": 2, "level": 20}]
    _, _, conflict = apply_warcry_buffs(equipped, skills, source, {"warcry_power": 5}, "full")
    assert conflict is None
    assert source.total("minion_dmg_additional") == pytest.approx(0.30)
    assert source.materialize_for_skill({"shadow strike"}).total("dmg_additional") == pytest.approx(0.20)


def test_duplicate_warcries_have_independent_most_recent_selectors():
    skills = {"charging_warcry": {"name": "Charging Warcry", "skill_tags": ["Warcry"]}}
    equipped = [{"skill_id": "charging_warcry", "slot": 1, "level": 20},
                {"skill_id": "charging_warcry", "slot": 2, "level": 20}]
    unselected = BuildSource()
    _, _, conflict = apply_warcry_buffs(equipped, skills, unselected, {"warcry_power": 5}, "full")
    assert conflict is not None and conflict["resolved"] is False
    assert unselected.materialize_for_skill({"shadow strike"}).total("dmg_additional") == 0

    source = BuildSource()
    _, _, conflict = apply_warcry_buffs(equipped, skills, source,
                                        {"warcry_power": 5, "warcry_sel_charging_warcry_2": True}, "full")
    assert conflict is not None and conflict["resolved"] is True
    assert {item["sel_key"] for item in conflict["groups"][0]["active"]} == {
        "warcry_sel_charging_warcry_1", "warcry_sel_charging_warcry_2"}
    assert source.materialize_for_skill({"shadow strike"}).total("dmg_additional") == pytest.approx(0.20)


def _kragol_gear(*clauses):
    """Build the exact GearEngineItem contribution shape from raw Kragol text."""
    contributions = []
    for text in clauses:
        for resolved in _resolve_gear_affix_clauses(text):
            for entry in resolved["parsed"]:
                contributions.append({
                    "stat": entry["stat_key"], "display_value": entry["amount"], "unit": "",
                    "condition": resolved["cond_expr"], "text": resolved["clause"],
                    "item_name": "Kragol's Roar", "slot": "amulet",
                })
    return [{"contributions": contributions}]


def test_kragols_roar_defaults_to_unique_warcry_count_and_clamps_manual_override():
    skills = {
        "charging_warcry": {"name": "Charging Warcry", "skill_tags": ["Warcry"]},
        "raging_warcry": {"name": "Raging Warcry", "skill_tags": ["Warcry"]},
    }
    equipped = [
        {"skill_id": "charging_warcry", "slot": 1, "level": 20},
        {"skill_id": "raging_warcry", "slot": 2, "level": 20},
        {"skill_id": "charging_warcry", "slot": 3, "level": 20},
    ]
    gear = _kragol_gear(
        "For each different Warcry cast, +4 to the minimum number of enemies affected by Warcry for 8 s",
        "+6 % additional Warcry Effect and +14 % additional Warcry Cooldown Recovery Speed for each different Warcry cast for 8 s (multiplies)",
    )

    def calculate(condition_state):
        return compute(BuildInput(slots=[], slates=[], season="test", gear=gear,
                                  condition_state=condition_state), {}, {},
                       skills_input=equipped, skills_by_id=skills)

    automatic = calculate({"enemy_count_weight": 5})
    summary = next(s for s in automatic.warcry_summaries if s["skill_id"] == "raging_warcry")
    # Two DISTINCT types, not three slots: +4 × 2 sets the Power minimum to 8.
    assert summary["power"] == 8
    assert summary["warcry_effect"] == pytest.approx(0.12)
    assert summary["cooldown"] == pytest.approx(8 / 1.28)
    assert automatic.condition_maximums["kragols_roar_distinct_warcries"] == 2
    assert automatic.auto_conditions["kragols_roar_distinct_warcries"]["value"] == 2

    manual = calculate({"enemy_count_weight": 5, "kragols_roar_distinct_warcries": 99})
    summary = next(s for s in manual.warcry_summaries if s["skill_id"] == "raging_warcry")
    assert summary["power"] == 8
    assert summary["warcry_effect"] == pytest.approx(0.12)
    assert manual.clamp_report["kragols_roar_distinct_warcries"] == {"requested": 99.0, "applied": 2.0}


def test_kragols_corroded_duration_is_warcry_only_and_scales_with_power():
    gear = _kragol_gear(
        "+1 % additional duration for the current Warcry for each enemy affected by Warcry +25 % Warcry Effect",
    )
    skills = {"raging_warcry": {"name": "Raging Warcry", "skill_tags": ["Warcry"]}}
    result = compute(BuildInput(slots=[], slates=[], season="test", gear=gear,
                                condition_state={"enemy_count_weight": 5, "warcry_power": 8}), {}, {},
                     skills_input=[{"skill_id": "raging_warcry", "slot": 1, "level": 20}],
                     skills_by_id=skills)
    summary = result.warcry_summaries[0]
    assert summary["duration"] == pytest.approx(3.5 * 1.08)
    assert summary["warcry_effect"] == pytest.approx(0.25)
    assert result.stat_map["warcry_skill_effect_duration_additional"]["total"] == pytest.approx(0.08)
