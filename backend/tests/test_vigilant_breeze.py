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
    assert result["set_conditions"]["vigilant_breeze_current_stacks"] == 10
    magus_source = BuildSource()
    assert apply_spirit_magi_growth(magus_source, breeze_stacks=10) == 160
    assert magus_source.total("spirit_magi_initial_growth_flat") == 60


def test_breeze_stacks_are_shared_inputs_for_the_merged_magus_layer():
    common = {
        "build_input": SimpleNamespace(season="SS13"), "ls_state": {}, "uptime_mode": "max",
        "slot_levels": [1, 1, 1, 1], "advanced_picks": [],
    }
    unmerged = vb.apply(condition_state={"vigilant_breeze_active": False, "vigilant_breeze_use_max_stacks": False,
                                         "vigilant_breeze_stacks": 1}, **common)
    merged = vb.apply(condition_state={"vigilant_breeze_active": True, "vigilant_breeze_use_max_stacks": False,
                                       "vigilant_breeze_stacks": 1}, **common)

    assert unmerged["set_conditions"]["vigilant_breeze_current_stacks"] == 0
    assert merged["set_conditions"]["vigilant_breeze_current_stacks"] == 1


def test_zero_breeze_stacks_can_be_selected_explicitly():
    result = vb.apply(
        build_input=SimpleNamespace(season="SS13"),
        condition_state={"vigilant_breeze_active": True, "vigilant_breeze_use_max_stacks": False,
                         "vigilant_breeze_stacks": 0},
        ls_state={}, uptime_mode="max", slot_levels=[5, 1, 1, 1], advanced_picks=[],
    )

    assert result["set_conditions"]["vigilant_breeze_current_stacks"] == 0


def test_breeze_damage_is_exposed_as_owner_confirmed_linear_scaling():
    rows = vb.status_lines(slot_levels=[1, 1, 1, 1], advanced_picks=[])
    breeze = next(row for row in rows if "Breeze adds +" in row["text"])

    assert breeze["status"] == "working"
    assert "owner-confirmed" in breeze["text"]
    assert "10 stacks = +160%" in breeze["text"]


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
                         "vigilant_breeze_use_max_stacks": False,
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
                         "vigilant_breeze_use_max_stacks": False,
                         "vigilant_breeze_stacks": 3},
        ls_state={}, uptime_mode="max", slot_levels=[1, 1, 5, 1],
        advanced_picks=["Warmest Vigilance"],
    )

    assert result["set_conditions"]["vigilant_breeze_warmest_bonus_stacks"] == 2
    assert result["set_conditions"]["vigilant_breeze_max_stacks"] == 12
    assert result["set_conditions"]["vigilant_breeze_current_stacks"] == 5


@pytest.mark.parametrize(("tier_level", "consumed_pct"), [(3, 8.2), (4, 7.6)])
def test_warmest_vigilance_uses_integer_basis_points_at_exact_thresholds(tier_level, consumed_pct):
    result = vb.apply(
        build_input=SimpleNamespace(season="SS13"),
        condition_state={"vigilant_breeze_life_consumed_pct": consumed_pct,
                         "vigilant_breeze_use_max_stacks": False, "vigilant_breeze_stacks": 1},
        ls_state={}, uptime_mode="max", slot_levels=[1, 1, tier_level, 1],
        advanced_picks=["Warmest Vigilance"],
    )

    assert result["set_conditions"]["vigilant_breeze_warmest_bonus_stacks"] == 2


def test_happiest_reunion_and_tango_keep_separate_additional_damage_factors():
    from engine.minion_offense import fold_spirit_magi_pools
    from engine.offense import _additional_product, _build_additional_factors
    from engine.models import SourceEntry

    result = vb.apply(
        build_input=SimpleNamespace(season="SS13"),
        condition_state={"vigilant_breeze_active": True, "vigilant_breeze_total_magi": 2,
                         "vigilant_breeze_use_max_stacks": False, "vigilant_breeze_stacks": 0},
        ls_state={}, uptime_mode="max", slot_levels=[1, 5, 5, 1],
        advanced_picks=["Whirlwind Tango", "Happiest Reunion"],
    )
    source = BuildSource()
    for item in result["contributions"]:
        source.add_with_source(item["stat_key"], item["amount"], SourceEntry(
            stat=item["stat_key"], amount=item["amount"], source_type="condition",
            label=item["source"], text=item["text"]))
    fold_spirit_magi_pools(source)
    factors = _build_additional_factors(source)
    actual = _additional_product(source, factors, lambda tags: "minion" in tags)

    # SS13 Tango is -60%; tier-5 Reunion is +5% per Magus, compounded across two Magi.
    assert actual == pytest.approx(0.4 * 1.05**2)


def test_spirit_magi_pool_fold_preserves_distinct_additional_sources_without_iris():
    from engine.minion_offense import fold_spirit_magi_pools
    from engine.offense import _additional_product, _build_additional_factors
    from engine.models import SourceEntry

    source = BuildSource()
    source.add_with_source("spirit_magi_dmg_additional", 0.10, SourceEntry(
        stat="spirit_magi_dmg_additional", amount=0.10, source_type="gear",
        label="Gear", text="First Magus damage source"))
    source.add_with_source("spirit_magi_dmg_additional", 0.20, SourceEntry(
        stat="spirit_magi_dmg_additional", amount=0.20, source_type="talent",
        label="Talent", text="Second Magus damage source"))

    fold_spirit_magi_pools(source)
    factors = _build_additional_factors(source)
    actual = _additional_product(source, factors, lambda tags: "minion" in tags)

    assert actual == pytest.approx(1.10 * 1.20)
    assert [entry.text for entry in source.source_log if entry.stat == "minion_dmg_additional"] == [
        "First Magus damage source", "Second Magus damage source",
    ]


def test_spirit_magi_pool_fold_clamps_mismatched_log_and_reports_nyi():
    from engine.minion_offense import fold_spirit_magi_pools
    from engine.models import SourceEntry

    source = BuildSource()
    source.add_with_source("spirit_magi_dmg_additional", 0.25, SourceEntry(
        stat="spirit_magi_dmg_additional", amount=0.25, source_type="gear",
        label="Gear", text="Magus damage source"))
    source._entries[0] = ("spirit_magi_dmg_additional", -0.10)

    nyi = fold_spirit_magi_pools(source)

    assert nyi == ["Spirit Magi additional damage source log did not balance; used a non-negative summed "
                   "fallback (distinct-source multiplication NYI for this Magus)."]
    assert source.total("minion_dmg_additional") == 0.0


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
        "origin_of_ice": True,
        "origin_of_ice_value": 2.4,
        "origin_of_rock": True,
        "origin_of_rock_value": -10.0,
        "origin_of_erosion": True,
        "origin_of_erosion_value": -10.0,
    }

    unsupported = vb.apply_merging_stream_origins(
        source=source, condition_state=condition_state, growth=200, magus_skill_tags={"spell"})

    # Fire Origin's Attack and Spell CSR stay scoped; a spell Magus receives only the spell grant.
    # The grant is 100 × (1 + 20% inc) × (1 + 10% Merging Stream additional) = 132.
    assert source.total("minion_crit_rating_flat") == pytest.approx(132.0)
    assert source.total("minion_life_regen_inc") > 0
    assert unsupported == ["dot_dmg_taken_additional", "energy_shield_regen_pct",
                           "hit_dmg_taken_additional"]

    attack_source = BuildSource()
    attack_source.add("spirit_magi_origin_effect_inc", 0.20)
    vb.apply_merging_stream_origins(source=attack_source, condition_state=condition_state, growth=200,
                                    magus_skill_tags={"attack"})
    assert attack_source.total("minion_crit_rating_flat") == pytest.approx(132.0)

    base_growth_source = BuildSource()
    vb.apply_merging_stream_origins(source=base_growth_source, condition_state={
        "vigilant_breeze_merging_stream": True,
        "vigilant_breeze_origin_effect_per_2_growth": 0.001,
        "origin_of_fire": True, "origin_of_fire_value": 100.0,
    }, growth=100, magus_skill_tags={"spell"})
    assert base_growth_source.total("minion_crit_rating_flat") == pytest.approx(105.0)

    frost_status = vb.status_lines(slot_levels=[1, 1, 1, 5], advanced_picks=["Merging Stream"],
                                   skills_input=[{"skill_id": "summon_frost_magus"}])
    assert any(row["status"] == "NYI" and "Energy Shield regeneration" in row["text"]
               for row in frost_status)


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

    no_drain = spirit_magus_reconjuring_cycle(
        drain_pct_per_second=0.20, regen_pct_per_second=0.30,
        other_reconjuring_heal_pct_per_second=0.10,
    )
    assert no_drain["damage_uptime"] == 1
    assert no_drain["heal_pct_per_second"] == pytest.approx(1 / 3 + 0.30 + 0.10)


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


def test_merged_selected_skill_keeps_empower_buff_and_pays_empower_cast_slot():
    source = BuildSource()
    base = {"name": "Base Strike", "cast_speed": "2 s", "cooldown": "1 s",
            "skill_tags": ["Base Skill", "Attack", "Physical"]}
    dispatch = vb.selected_skill_contract(
        selected_skill="Base Skill", minion_skills=[base], source=source,
    )
    empower_output = SimpleNamespace(
        minion_empower={
            "uptime": 0.60,
            "empower_effect": 1.20,
            "cooldown": 5.0,
            "buffs": [
                {"stat": "attack_speed", "value": 0.35 * 1.20 * 0.60},
                {"stat": "damage", "value": 0.20},
            ],
        },
        minion_skill_casts={"empower": {"base_cast_time": 1.0, "cast_time": 0.8, "cooldown": 5.0}},
        hit_forms=[],
    )

    adjusted = vb.apply_merged_empower_to_contract(dispatch, empower_output)

    # Base rate 0.5/s; Empower's +25.2% Attack Speed and half-cast slot loss (1s/5s) both apply.
    assert adjusted["base_casts_per_second"] == pytest.approx(0.5)
    assert adjusted["empower_uptime"] == pytest.approx(0.60)
    assert adjusted["empower_effect"] == pytest.approx(1.20)
    assert adjusted["empower_casts_per_second"] == pytest.approx(0.20)
    assert adjusted["empower_cast_slot_factor"] == pytest.approx(0.90)
    assert adjusted["empower_rate_multiplier"] == pytest.approx(1.252 * 0.90)
    assert adjusted["casts_per_second"] == pytest.approx(0.5 * 1.252 * 0.90)
    assert adjusted["skill_forms"][0]["casts_per_second"] == pytest.approx(0.5 * 1.252 * 0.90)
    assert adjusted["empower_buffs"] == empower_output.minion_empower["buffs"]


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


def test_selected_skill_with_unparsed_cast_time_is_unavailable():
    contract = vb.selected_skill_contract(
        selected_skill="Ultimate",
        minion_skills=[{"name": "Unknown Ultimate", "cooldown": "8 s",
                        "skill_tags": ["Ultimate", "Spell"]}],
        source=BuildSource(),
    )

    assert contract["available"] is False
    assert contract["reason"] == "selected skill cast time is unavailable"


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
    empower = merged_magus["minion_empower"]
    dispatch = merged_magus["iris_skill_dispatch"]
    attack_speed_buff = next(buff["value"] for buff in empower["buffs"]
                             if buff["stat"] == "attack_speed")
    assert dispatch["empower_uptime"] == pytest.approx(empower["uptime"])
    assert dispatch["empower_cast_slot_factor"] == pytest.approx(empower["cast_slot_factor"])
    assert dispatch["empower_rate_multiplier"] == pytest.approx(
        (1.0 + attack_speed_buff) * empower["cast_slot_factor"])
    assert dispatch["casts_per_second"] == pytest.approx(
        dispatch["base_casts_per_second"] * dispatch["empower_rate_multiplier"])

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
    whisper_tier = vb._tier([1, 5, 1, 1], vb._SLOT_45)
    assert base["reconjuring_cycle"]["drain_heal_pct_per_second"] == pytest.approx(
        min(base["iris_skill_dispatch"]["enhanced_casts_per_second"],
            1.0 / vb._WHISPER_INTERVAL[whisper_tier]) * vb._WHISPER_HEAL[whisper_tier])
    assert base["iris_skill_dispatch"]["empower_rate_multiplier"] != 1.0
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

    def calculate(vigilant=True, reunion=False, picks=()):
        selected_picks = list(picks) + (["Happiest Reunion"] if reunion else [])
        req = make_request(
            "summon_thunder_magus", 20, trait_id="vigilant_breeze", trait_slot_levels=[1, 1, 5, 1],
            advanced_trait_selections=selected_picks,
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

    with_stream = calculate(picks=["Merging Stream"])
    assert with_stream["summon_rock_magus"]["vigilant_merged"] is False
    assert with_stream["summon_rock_magus"]["total_dps"] > without_reunion["summon_rock_magus"]["total_dps"]

    with_reunion = calculate(reunion=True)
    assert with_reunion["summon_thunder_magus"]["vigilant_merged"] is True
    assert with_reunion["summon_rock_magus"]["vigilant_merged"] is True
    assert with_reunion["summon_thunder_magus"]["iris_merged_magi_count"] == 3
    assert with_reunion["summon_rock_magus"]["total_dps"] == 0

    disabled = calculate(vigilant=False, reunion=True)
    assert disabled["summon_thunder_magus"]["vigilant_merged"] is False
    assert disabled["summon_rock_magus"]["vigilant_merged"] is False
    assert disabled["summon_rock_magus"]["total_dps"] > 0


def test_reunion_count_uses_per_owner_active_minion_cap():
    from engine.compute import _spirit_magi_base_active_count

    skills_by_id = {
        "summon_thunder_magus": {"item_id": "summon_thunder_magus", "minion_skills": [{}],
                                 "detailed_description": ["Summons up to 3 Spirit Magi"]},
        "summon_rock_magus": {"item_id": "summon_rock_magus", "minion_skills": [{}],
                              "detailed_description": ["Summons up to 2 Spirit Magi"]},
    }
    skills_input = [{"slot": 2, "skill_id": "summon_rock_magus", "level": 20, "enabled": True}]
    main_skill = type("MainSkill", (), {"skill_id": "summon_thunder_magus", "level": 20})()

    assert _spirit_magi_base_active_count(
        skills_by_id, skills_input, main_skill, True, 1, 1) == 2
    assert _spirit_magi_base_active_count(
        skills_by_id, skills_input, main_skill, True, 1, 0) == 5
    assert _spirit_magi_base_active_count(
        skills_by_id, skills_input, main_skill, True, 1, 1, shared_bonus=1) == 2
    assert _spirit_magi_base_active_count(
        skills_by_id, skills_input, main_skill, True, 1, 2, shared_bonus=1) == 4
    assert _spirit_magi_base_active_count(
        skills_by_id, skills_input, main_skill, True, 1, 0, shared_bonus=1) == 6
    one_each = {key: {**owner, "detailed_description": []}
                for key, owner in skills_by_id.items()}
    assert _spirit_magi_base_active_count(
        one_each, skills_input, main_skill, True, 1, 1, shared_bonus=2) == 2
    assert _spirit_magi_base_active_count(
        one_each, skills_input, main_skill, True, 1, 2, shared_bonus=2) == 4
    assert _spirit_magi_base_active_count(None, skills_input, main_skill, True, 1, 0) == 0


def test_happiest_reunion_count_includes_gear_max_magi():
    from server import EngineStatsRequest, engine_stats
    from tests.mock_build import make_request

    gear = [{"item_name": "Max Magi Ring", "contributions": [{
        "stat": "max_spirit_magi_flat", "display_value": 1, "unit": "", "slot": "ring1",
        "item_name": "Max Magi Ring", "text": "+1 Max Spirit Magi",
    }]}]
    request = make_request(
        "summon_thunder_magus", 20, trait_id="vigilant_breeze", trait_slot_levels=[1, 1, 5, 1],
        advanced_trait_selections=["Happiest Reunion"], gear=gear,
        extra_conditions={"vigilant_breeze_active": True},
    )
    magus = engine_stats(EngineStatsRequest(**request))["minion_offense"]["summon_thunder_magus"]

    # Base cap 1 + gear +1 + Happiest Reunion +1.
    assert magus["iris_merged_magi_count"] == 3

    two_magi_limited = make_request(
        "summon_thunder_magus", 20, trait_id="vigilant_breeze", trait_slot_levels=[1, 1, 5, 1],
        advanced_trait_selections=["Happiest Reunion"], gear=gear,
        skills=[{"slot": 1, "skill_id": "summon_thunder_magus", "level": 20},
                {"slot": 2, "skill_id": "summon_rock_magus", "level": 20}],
        extra_conditions={"vigilant_breeze_active": True, "active_minions": 1},
    )
    limited = engine_stats(EngineStatsRequest(**two_magi_limited))["minion_offense"]
    # Each owner is at its configured active cap, so shared gear/Reunion capacity adds no active Magi.
    assert limited["summon_thunder_magus"]["iris_merged_magi_count"] == 2


def test_compute_forwards_breeze_and_reunion_damage_into_magus_pools(monkeypatch):
    from engine import minion_offense
    from server import EngineStatsRequest, engine_stats
    from tests.mock_build import make_request

    real_calculate = minion_offense.calculate_minion_offense
    observed = []

    def capture_magus_source(source, *args, **kwargs):
        observed.extend(entry for entry in source.source_log
                        if entry.stat == "minion_dmg_additional"
                        and (entry.amount == pytest.approx(0.32)
                             or entry.amount == pytest.approx(1.05**2 - 1)))
        return real_calculate(source, *args, **kwargs)

    monkeypatch.setattr(minion_offense, "calculate_minion_offense", capture_magus_source)
    request = make_request(
        "summon_thunder_magus", 20, trait_id="vigilant_breeze", trait_slot_levels=[5, 1, 5, 1],
        advanced_trait_selections=["Happiest Reunion"],
        extra_conditions={"vigilant_breeze_active": True, "vigilant_breeze_use_max_stacks": False,
                          "vigilant_breeze_stacks": 2, "vigilant_breeze_skill": "Ultimate"},
    )
    magus = engine_stats(EngineStatsRequest(**request))["minion_offense"]["summon_thunder_magus"]

    assert magus["selected_skill_damage_status"] == "NYI"
    assert any(entry.amount == pytest.approx(0.32) for entry in observed)
    assert any(entry.amount == pytest.approx(1.05**2 - 1) for entry in observed)


def test_missing_magus_life_data_skips_flat_regen_and_flags_nyi(monkeypatch):
    from persistence import season_manager
    from server import EngineStatsRequest, engine_stats
    from tests.mock_build import make_request

    monkeypatch.setattr(season_manager, "load_minion_base_stats", lambda _season: {"life_by_group": {}})
    no_flat_regen = make_request(
        "summon_thunder_magus", 20, trait_id="vigilant_breeze", trait_slot_levels=[1, 1, 1, 5],
        advanced_trait_selections=["Nurturing Breeze"],
        extra_conditions={"vigilant_breeze_active": True},
    )
    no_regen_magus = engine_stats(EngineStatsRequest(**no_flat_regen))["minion_offense"]["summon_thunder_magus"]
    assert not any("base Life is unavailable" in item for item in no_regen_magus["nyi"])

    gear = [{"item_name": "Life Regeneration Ring", "contributions": [{
        "stat": "life_regen_flat", "display_value": 100, "unit": "", "slot": "ring1",
        "item_name": "Life Regeneration Ring", "text": "+100 Life Regeneration per Second",
    }]}]
    with_flat_regen = make_request(
        "summon_thunder_magus", 20, trait_id="vigilant_breeze", trait_slot_levels=[1, 1, 1, 5],
        advanced_trait_selections=["Nurturing Breeze"], gear=gear,
        extra_conditions={"vigilant_breeze_active": True},
    )
    magus = engine_stats(EngineStatsRequest(**with_flat_regen))["minion_offense"]["summon_thunder_magus"]
    assert any("base Life is unavailable" in item for item in magus["nyi"])


def test_unavailable_selected_skill_reason_is_reported_in_compute(monkeypatch):
    import copy
    import server
    from server import EngineStatsRequest, engine_stats
    from tests.mock_build import make_request

    real_get_skills_data = server._get_skills_data

    def get_skills_without_ultimate_cast_time(season):
        skills = copy.deepcopy(real_get_skills_data(season))
        ultimate = next(ability for ability in skills["summon_thunder_magus"]["minion_skills"]
                        if "ultimate" in {str(tag).lower() for tag in ability.get("skill_tags", [])})
        ultimate["cast_speed"] = None
        return skills

    monkeypatch.setattr(server, "_get_skills_data", get_skills_without_ultimate_cast_time)
    request = make_request(
        "summon_thunder_magus", 20, trait_id="vigilant_breeze", trait_slot_levels=[1, 1, 1, 1],
        extra_conditions={"vigilant_breeze_active": True, "vigilant_breeze_skill": "Ultimate"},
    )
    magus = engine_stats(EngineStatsRequest(**request))["minion_offense"]["summon_thunder_magus"]

    assert any("selected skill cast time is unavailable" in item for item in magus["nyi"])
    assert not any("0.000 casts/s" in item for item in magus["nyi"])


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
