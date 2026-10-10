from types import SimpleNamespace

import pytest

from engine.hero_traits import has_module
from engine.hero_traits import vigilant_breeze as vb
from engine.models import BuildSource


def _amounts(result):
    return [(item["stat_key"], item["amount"]) for item in result["contributions"]]


def _amount_map(result):
    return dict(_amounts(result))


def test_vigilant_breeze_base_level_and_artificial_moon_contributions():
    from engine.minion_offense import apply_spirit_magi_growth

    result = vb.apply(
        build_input=SimpleNamespace(season="SS13"),
        condition_state={"vigilant_breeze_stacks": 0}, ls_state={}, uptime_mode="max",
        slot_levels=[5, 1, 1, 1], advanced_picks=[],
    )

    assert ("minion_dmg_additional", 0.20) in _amounts(result)
    assert result["set_conditions"]["vigilant_breeze_max_stacks"] == 10
    assert result["set_conditions"]["vigilant_breeze_artificial_moon_growth"] == 60
    magus_source = BuildSource()
    assert apply_spirit_magi_growth(magus_source, breeze_stacks=10) == 160
    assert magus_source.total("spirit_magi_initial_growth_flat") == 60


def test_breeze_stacks_are_shared_inputs_for_the_merged_magus_layer():
    common = {
        "build_input": SimpleNamespace(season="SS13"), "ls_state": {}, "uptime_mode": "max",
        "slot_levels": [1, 1, 1, 1], "advanced_picks": [],
    }
    unmerged = vb.apply(condition_state={"vigilant_breeze_active": False,
                                         "vigilant_breeze_stacks": 1}, **common)
    merged = vb.apply(condition_state={"vigilant_breeze_active": True,
                                       "vigilant_breeze_stacks": 1}, **common)

    assert unmerged["set_conditions"]["vigilant_breeze_current_stacks"] == 0
    assert merged["set_conditions"]["vigilant_breeze_current_stacks"] == 1


def test_happiest_reunion_uses_per_magus_product_and_adds_map_cap():
    result = vb.apply(
        build_input=SimpleNamespace(season="SS13"),
        condition_state={"vigilant_breeze_active": True, "vigilant_breeze_total_magi": 3,
                         "vigilant_breeze_stacks": 0},
        ls_state={}, uptime_mode="max", slot_levels=[5, 5, 5, 1],
        advanced_picks=["Happiest Reunion"],
    )

    # Owner-confirmed formula: 5% with three Magi gives 1.05**3 = 1.157625.
    assert ("spirit_magi_dmg_additional", pytest.approx(0.157625)) in _amounts(result)
    assert ("max_spirit_magi_flat", 1.0) in _amounts(result)
    # Tier 5 adds 6 percentage points to the 20%/s drain.
    assert result["set_conditions"]["vigilant_breeze_life_cost_pct_max_per_sec"] == pytest.approx(0.26)


def test_happiest_reunion_adds_eight_percentage_points_at_tier_one():
    result = vb.apply(
        build_input=SimpleNamespace(season="SS13"),
        condition_state={"vigilant_breeze_active": True}, ls_state={}, uptime_mode="max",
        slot_levels=[1, 1, 1, 1], advanced_picks=["Happiest Reunion"],
    )

    # Owner-confirmed percentage-point rule: 20%/s + 8 points = 28%/s.
    assert result["set_conditions"]["vigilant_breeze_life_cost_pct_max_per_sec"] == pytest.approx(0.28)


def test_happiest_reunion_uses_derived_active_magus_total_not_selector():
    result = vb.apply(
        build_input=SimpleNamespace(season="SS13"),
        condition_state={"vigilant_breeze_active": True, "vigilant_breeze_total_magi": 3,
                         "vigilant_breeze_stacks": 1},
        ls_state={}, uptime_mode="max", slot_levels=[1, 1, 5, 1],
        advanced_picks=["Happiest Reunion"],
    )

    assert result["set_conditions"]["vigilant_breeze_merged_magi_effective"] == 3
    reunion_damage = sum(amount for key, amount in _amounts(result) if key == "spirit_magi_dmg_additional")
    assert reunion_damage == pytest.approx(1.05**3 - 1)
    assert result["set_conditions"]["vigilant_breeze_current_stacks"] == 1


def test_warmest_vigilance_uses_per_magus_life_counter_and_defeat_stacks():
    result = vb.apply(
        build_input=SimpleNamespace(season="SS13"),
        condition_state={"vigilant_breeze_life_consumed_pct": 10,
                         "vigilant_breeze_enemies_defeated": 2,
                         "vigilant_breeze_stacks": 3},
        ls_state={}, uptime_mode="max", slot_levels=[1, 1, 5, 1],
        advanced_picks=["Warmest Vigilance"],
    )

    assert result["set_conditions"]["vigilant_breeze_warmest_bonus_stacks"] == 2
    assert result["set_conditions"]["vigilant_breeze_max_stacks"] == 12
    assert result["set_conditions"]["vigilant_breeze_current_stacks"] == 5


def test_nurturing_breeze_copies_scaled_regen_and_regain_pools():
    result = vb.apply(
        build_input=SimpleNamespace(season="SS13"),
        condition_state={"vigilant_breeze_stacks": 10},
        ls_state={"iris_life_regen_inc": 0.04, "iris_life_regen_speed_inc": 0.50,
                  "iris_life_regain_inc": 0.20, "iris_energy_shield_regain_inc": 0.10},
        uptime_mode="max", slot_levels=[1, 1, 1, 3],
        advanced_picks=["Nurturing Breeze"],
    )

    amounts = _amount_map(result)
    assert amounts["minion_life_regen_inc"] == pytest.approx(0.028)
    assert amounts["minion_life_regen_speed_inc"] == pytest.approx(0.35)
    assert amounts["minion_life_regain_inc"] == pytest.approx(0.28)
    assert amounts["minion_es_regain_inc"] == pytest.approx(0.14)
    assert amounts["dmg_taken_additional"] == pytest.approx(-0.28)


def test_whisper_temporary_breeze_bonus_is_user_set_and_capped_not_automatic():
    common = {
        "build_input": SimpleNamespace(season="SS13"), "ls_state": {},
        "uptime_mode": "max", "slot_levels": [1, 5, 1, 1],
        "advanced_picks": ["Breeze's Whisper"],
    }

    no_bonus = vb.apply(condition_state={"vigilant_breeze_stacks": 0}, **common)
    with_bonus = vb.apply(condition_state={"vigilant_breeze_stacks": 0,
                                           "vigilant_breeze_whisper_bonus_stacks": 99}, **common)

    assert no_bonus["set_conditions"]["vigilant_breeze_max_stacks"] == 10
    assert with_bonus["set_conditions"]["vigilant_breeze_max_stacks"] == 18


def test_merging_stream_scales_origin_for_each_magus_growth():
    source = BuildSource()
    source.add("spirit_magi_origin_effect_inc", 0.20)
    condition_state = {
        "vigilant_breeze_merging_stream": True,
        "vigilant_breeze_origin_effect_per_2_growth": 0.001,
        "origin_of_fire": True,
        "origin_of_fire_value": 100.0,
    }

    vb.apply_merging_stream_origins(source=source, condition_state=condition_state, growth=200)

    # Fire Origin grants both Attack and Spell CSR. Both fold into the Magus's one CSR pool.
    # Each grant is 100 × (1 + 20% inc) × (1 + 10% Merging Stream additional) = 132.
    assert source.total("minion_crit_rating_flat") == pytest.approx(264.0)


def test_reconjuring_cycle_uses_heal_rate_and_reports_damage_uptime():
    from engine.minion_offense import spirit_magus_reconjuring_cycle
    cycle = spirit_magus_reconjuring_cycle(drain_pct_per_second=0.20)

    assert cycle["drain_seconds"] == 5.0
    assert cycle["reconjuring_seconds"] == 3.0
    assert cycle["damage_uptime"] == pytest.approx(0.625)

    with_regen = spirit_magus_reconjuring_cycle(
        drain_pct_per_second=0.20, regen_pct_per_second=0.10, regen_speed_inc=0.50,
    )
    assert with_regen["heal_pct_per_second"] == pytest.approx(0.48333333333333334)
    # 15%/s ordinary healing reduces the 20%/s drain to 5%/s, so drain lasts 20s.
    # Reconjuring lasts 1/(1/3 + 0.15)s. Uptime = 20 / (20 + 1/(1/3 + 0.15)).
    assert with_regen["damage_uptime"] == pytest.approx(0.90625)


def test_reconjuring_graft_regen_is_parsed_into_its_own_heal_window_pool():
    from engine.mod_parser import _parse_custom_mod_text
    from engine.minion_offense import spirit_magus_reconjuring_cycle

    parsed = _parse_custom_mod_text(
        "While Reconjuring , Spirit Magi regenerate (21–25) % Life per second")

    assert parsed == [{
        "stat_key": "minion_reconjuring_life_regen_inc",
        "amount": 0.23,
        "text": "While Reconjuring , Spirit Magi regenerate (21–25) % Life per second",
    }]
    cycle = spirit_magus_reconjuring_cycle(
        drain_pct_per_second=0.20, other_reconjuring_heal_pct_per_second=parsed[0]["amount"],
    )
    # 23% added to the 1/3 Max-Life/s base heal gives 300/169 s; uptime is 5/(5+300/169)=169/229.
    assert cycle["reconjuring_seconds"] == pytest.approx(300 / 169)
    assert cycle["damage_uptime"] == pytest.approx(169 / 229)


def test_selected_skill_contract_returns_per_cast_rate_and_keeps_ultimate_out_of_default_total():
    source = BuildSource()
    source.add("minion_attack_speed_inc", 1.0)
    source.add("minion_ultimate_attack_speed_additional", 0.5)
    source.add("minion_cdr_speed_inc", 1.0)
    source.add("spirit_magi_cdr_speed_inc", 1.0)
    source.add("spirit_magi_ultimate_dmg_inc", 0.25)
    source.add("spirit_magi_ultimate_dmg_additional", 0.40)
    ability = {
        "name": "Towering Mountains", "cast_speed": "1.5 s", "cooldown": "8 s",
        "skill_tags": ["Ultimate", "Attack", "Physical"],
    }

    regular = vb.selected_skill_contract(
        selected_skill="Lightning Surge (Ultimate)", minion_skills=[ability], source=source,
    )
    tango = vb.selected_skill_contract(
        selected_skill="Lightning Surge (Ultimate)", minion_skills=[ability], source=source,
        ultimate_cooldown_zero=True, life_cost_pct_max_per_cast=0.06, breeze_per_cast=4,
    )

    assert regular["casts_per_second"] == pytest.approx(0.375)
    assert regular["damage_in_default_total"] is False
    assert regular["ultimate_damage_pools"] == {"inc": 0.25, "additional": 0.40}
    assert tango["casts_per_second"] == pytest.approx(2.0)
    assert tango["life_cost_pct_max_per_cast"] == 0.06
    assert tango["breeze_per_cast"] == 4


@pytest.mark.parametrize(("enhanced_chance", "base_rate", "enhanced_rate"), [
    (0.0, 0.5, 0.0),
    (1.0, 0.0, 0.5),
])
def test_merged_base_selection_mixes_enhanced_as_a_replacement_per_cast(
        enhanced_chance, base_rate, enhanced_rate):
    source = BuildSource()
    source.add("spirit_magi_enhanced_skill_chance", enhanced_chance)
    abilities = [
        {"name": "Base Bolt", "cast_speed": "2 s", "cooldown": "1 s",
         "skill_tags": ["Base Skill", "Spell", "Lightning"]},
        {"name": "Enhanced Bolt", "cast_speed": "1 s", "cooldown": "4 s",
         "skill_tags": ["Enhanced Skill", "Spell", "Lightning"]},
    ]

    contract = vb.selected_skill_contract(
        selected_skill="Base Skill", minion_skills=abilities, source=source,
    )

    assert contract["role"] == "base skill"
    assert contract["casts_per_second"] == pytest.approx(0.5)
    assert contract["enhanced_chance"] == pytest.approx(enhanced_chance)
    assert contract["skill_forms"] == [
        {"role": "base skill", "skill_name": "Base Bolt", "casts_per_second": base_rate},
        {"role": "enhanced skill", "skill_name": "Enhanced Bolt", "casts_per_second": enhanced_rate},
    ]


def test_merged_base_selection_adds_growth_stage_two_enhanced_chance():
    source = BuildSource()
    abilities = [
        {"name": "Base Bolt", "cast_speed": "2 s", "cooldown": "1 s",
         "skill_tags": ["Base Skill", "Spell"]},
        {"name": "Enhanced Bolt", "cast_speed": "1 s", "cooldown": "4 s",
         "skill_tags": ["Enhanced Skill", "Spell"]},
    ]

    contract = vb.selected_skill_contract(
        selected_skill="Base Skill", minion_skills=abilities, source=source, growth=200,
    )

    assert contract["enhanced_chance"] == pytest.approx(0.30)
    assert contract["skill_forms"][0]["casts_per_second"] == pytest.approx(0.35)
    assert contract["skill_forms"][1]["casts_per_second"] == pytest.approx(0.15)


def test_enhanced_is_not_a_selectable_iris_skill():
    contract = vb.selected_skill_contract(
        selected_skill="Enhanced Skill", minion_skills=[], source=BuildSource(),
    )

    assert contract["available"] is False


@pytest.mark.parametrize(("selected", "role"), [
    ("Base", "base skill"), ("Base Skill", "base skill"),
    ("Blazing Dance (Base)", "base skill"),
    ("Ultimate", "ultimate"), ("Ultimate Skill", "ultimate"),
    ("Lightning Surge (Ultimate)", "ultimate"),
])
def test_selected_skill_role_normalization_accepts_condition_and_dropdown_labels(selected, role):
    assert vb.normalize_selected_skill_role(selected) == role


def test_compute_replaces_rotation_only_while_merged_and_suppresses_player_origins_for_stream():
    from server import EngineStatsRequest, engine_stats
    from tests.mock_build import make_request

    def calculate(vigilant=True, picks=()):
        request = make_request(
            "summon_thunder_magus", 20, trait_id="vigilant_breeze", trait_slot_levels=[1, 1, 1, 1],
            advanced_trait_selections=list(picks),
            extra_conditions={"vigilant_breeze_active": vigilant,
                              "vigilant_breeze_stacks": 1},
        )
        return engine_stats(EngineStatsRequest(**request))

    merged = calculate()
    merged_magus = merged["minion_offense"]["summon_thunder_magus"]
    assert merged_magus["vigilant_merged"] is True
    assert merged_magus["total_dps"] == 0.0
    assert "normal rotation is replaced" in " ".join(merged_magus["nyi"]).lower()
    assert merged_magus["iris_skill_dispatch"]["role"] == "ultimate"
    assert merged_magus["selected_skill_damage_status"] == "NYI"
    assert merged_magus["selected_skill_damage_pending"] is True
    assert merged_magus["reconjuring_cycle"]["damage_uptime"] == pytest.approx(0.625)

    unmerged = calculate(False)
    unmerged_magus = unmerged["minion_offense"]["summon_thunder_magus"]
    assert unmerged_magus["vigilant_merged"] is False
    assert unmerged_magus["total_dps"] > 0
    assert "iris_skill_dispatch" not in unmerged_magus

    stream = calculate(True, ["Merging Stream"])
    assert stream.get("origin_summary") is None
    assert stream["stats"].get("cast_speed_additional", {}).get("total", 0) == 0

    reunion = calculate(True, ["Happiest Reunion"])
    reunion_magus = reunion["minion_offense"]["summon_thunder_magus"]
    # Thunder has one base summon at this level; Happiest Reunion adds one map-cap Magus.
    assert reunion_magus["iris_merged_magi_count"] == 2
    assert reunion_magus["iris_skill_dispatch"]["role"] == "ultimate"
    assert reunion_magus["selected_skill_damage_status"] == "NYI"


def test_compute_whisper_heals_enhanced_base_casts_but_not_selected_ultimate():
    from server import EngineStatsRequest, engine_stats
    from tests.mock_build import make_request

    def calculate(selected):
        request = make_request(
            "summon_thunder_magus", 20, trait_id="vigilant_breeze", trait_slot_levels=[1, 5, 1, 1],
            advanced_trait_selections=["Breeze's Whisper"],
            extra_conditions={"vigilant_breeze_active": True, "vigilant_breeze_skill": selected},
        )
        return engine_stats(EngineStatsRequest(**request))["minion_offense"]["summon_thunder_magus"]

    base = calculate("Base Skill")
    ultimate = calculate("Ultimate")
    assert base["iris_skill_dispatch"]["enhanced_casts_per_second"] > 0
    assert base["reconjuring_cycle"]["drain_heal_pct_per_second"] > 0
    assert ultimate["iris_skill_dispatch"]["enhanced_casts_per_second"] == 0
    assert ultimate["reconjuring_cycle"]["drain_heal_pct_per_second"] == 0


def test_vigilant_merge_is_derived_for_each_magus_with_reunion_and_toggle(monkeypatch):
    from server import EngineStatsRequest, engine_stats
    from tests.mock_build import make_request
    from engine import minion_offense

    # Let the Rock owner borrow an implemented owner formula so this integration case can distinguish
    # its ordinary rotation DPS from merged selected-skill replacement.
    monkeypatch.setitem(minion_offense.MINION_MODULES, "summon_rock_magus",
                        minion_offense.MINION_MODULES["summon_thunder_magus"])

    def calculate(vigilant=True, reunion=False):
        req = make_request(
            "summon_thunder_magus", 20, trait_id="vigilant_breeze", trait_slot_levels=[1, 1, 5, 1],
            advanced_trait_selections=["Happiest Reunion"] if reunion else [],
            extra_conditions={"vigilant_breeze_active": vigilant},
            skills=[{"slot": 1, "skill_id": "summon_thunder_magus", "level": 20},
                    {"slot": 2, "skill_id": "summon_rock_magus", "level": 20}],
        )
        return engine_stats(EngineStatsRequest(**req))["minion_offense"]

    without_reunion = calculate()
    assert without_reunion["summon_thunder_magus"]["vigilant_merged"] is True
    assert without_reunion["summon_rock_magus"]["vigilant_merged"] is False
    assert "selected_skill_damage_status" not in without_reunion["summon_rock_magus"]
    assert without_reunion["summon_rock_magus"]["total_dps"] > 0

    with_reunion = calculate(reunion=True)
    assert with_reunion["summon_thunder_magus"]["vigilant_merged"] is True
    assert with_reunion["summon_rock_magus"]["vigilant_merged"] is True
    assert with_reunion["summon_rock_magus"]["total_dps"] == 0

    disabled = calculate(vigilant=False, reunion=True)
    assert disabled["summon_thunder_magus"]["vigilant_merged"] is False
    assert disabled["summon_rock_magus"]["vigilant_merged"] is False
    assert disabled["summon_rock_magus"]["total_dps"] > 0


def test_missing_magus_life_data_skips_flat_regen_and_flags_nyi(monkeypatch):
    from persistence import season_manager
    from server import EngineStatsRequest, engine_stats
    from tests.mock_build import make_request

    monkeypatch.setattr(season_manager, "load_minion_base_stats", lambda _season: {"life_by_group": {}})
    req = make_request(
        "summon_thunder_magus", 20, trait_id="vigilant_breeze", trait_slot_levels=[1, 1, 1, 5],
        advanced_trait_selections=["Nurturing Breeze"],
        extra_conditions={"vigilant_breeze_active": True},
    )
    magus = engine_stats(EngineStatsRequest(**req))["minion_offense"]["summon_thunder_magus"]
    assert any("base Life is unavailable" in item for item in magus["nyi"])


def test_non_iris_spirit_magus_exposes_shared_growth_and_reconjuring_formula_without_dps_penalty():
    from server import EngineStatsRequest, engine_stats
    from tests.mock_build import make_request

    request = make_request("summon_thunder_magus", 20)
    magus = engine_stats(EngineStatsRequest(**request))["minion_offense"]["summon_thunder_magus"]

    assert magus["total_dps"] > 0
    assert magus["spirit_magi_growth"] == 100
    assert magus["reconjuring_cycle"]["heal_pct_per_second"] == pytest.approx(1 / 3)
    assert magus["reconjuring_cycle"]["damage_uptime"] == 1


def test_inactive_vigilant_merging_stream_condition_does_not_suppress_player_origin():
    from server import EngineStatsRequest, engine_stats
    from tests.mock_build import make_request

    request = make_request(
        "summon_thunder_magus", 20, trait_id="vigilant_breeze", trait_slot_levels=[0, 0, 0, 0],
        extra_conditions={"vigilant_breeze_merging_stream": True, "origin_of_thunder": True},
    )
    result = engine_stats(EngineStatsRequest(**request))
    stats = result["stats"]

    assert stats["cast_speed_additional"]["total"] == pytest.approx(0.06)
    assert stats["dmg_additional"]["total"] == pytest.approx(0.0725)
    assert result.get("origin_summary") is not None


def test_vigilant_breeze_is_registered_in_trait_dispatch():
    assert has_module("vigilant_breeze") is True
