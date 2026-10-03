"""Focused Affliction / True Flame mechanics pinned to the owner-confirmed SS13 rules."""
from __future__ import annotations

import pytest

from engine.aggregator import aggregate
from engine.compute import compute
from engine.models import BuildInput, BuildSource, SourceEntry
from engine.offense import _enemy_vuln_mult, calculate_offense
from engine.mod_parser import _parse_custom_mod_text
from engine.skill_resolver import DotForm, ResolvedSkill, SkillHitForm
from engine.support_resolver import resolve_standard_supports, resolve_support_contributions
from server import EngineStatsRequest, engine_stats
from tests.mock_build import make_request


def _source(*entries: tuple[str, float, str]) -> BuildSource:
    source = BuildSource()
    for index, (stat, amount, text) in enumerate(entries):
        source.add_with_source(stat, amount, SourceEntry(
            stat=stat, amount=amount, source_type="test", label="test", text=text,
            # These are separate owner-confirmed additional sources.  The test must not accidentally
            # model them as two rolls of one affix merely because their value-less text identity matches.
            pooling_uuid=f"test-affliction-{index}",
        ))
    return source


def _response(skill_id: str = "icebound_beam", **kwargs) -> dict:
    request = make_request(skill_id, 16, **kwargs)
    response = engine_stats(EngineStatsRequest(**request))
    return response.model_dump() if hasattr(response, "model_dump") else response


def test_affliction_effect_formula_multiplies_additional_sources_independently():
    # 100 stacks × 1% × (1 + 50% increased) × (1 + 20%) × (1 + 30%) = 234% DoT taken.
    source = _source(
        ("affliction_dot_taken_base", 1.50, "100 Affliction, +50% Effect"),
        ("affliction_effect_additional", 0.20, "20% additional Affliction Effect"),
        ("affliction_effect_additional", 0.30, "30% additional Affliction Effect"),
    )
    assert _enemy_vuln_mult(source, "erosion", is_dot=True) == pytest.approx(3.34)


def test_affliction_is_dot_only_and_true_flame_is_fire_hit_only():
    source = _source(
        ("affliction_dot_taken_base", 1.50, "Affliction"),
        ("true_flame_fire_hit_taken", 0.975, "True Flame"),
    )
    # Affliction applies to all DoT types, but never to a hit.
    assert _enemy_vuln_mult(source, "erosion", is_dot=True) == pytest.approx(2.50)
    assert _enemy_vuln_mult(source, "fire", is_dot=False) == pytest.approx(1.975)
    assert _enemy_vuln_mult(source, "physical", is_dot=False) == pytest.approx(1.0)
    # True Flame cannot leak into Fire DoT; it is hit-only.
    assert _enemy_vuln_mult(source, "fire", is_dot=True) == pytest.approx(2.50)


def test_true_flame_requires_ignite_and_uses_final_affliction_bonus():
    common = dict(
        extra_conditions={"affliction_stacks": 100},
        custom_mods=[
            "+50 % Affliction Effect",
            "20 % additional Affliction Effect",
            "30 % additional Affliction Effect",
            "65 % of the additional bonus to Damage Over Time taken from Affliction is also applied to your Fire Hit Damage",
        ],
    )
    unignited = _response(**common)
    ignited = _response(extra_conditions={**common["extra_conditions"], "enemy_ignited": True},
                        custom_mods=common["custom_mods"])
    assert "true_flame_fire_hit_taken" not in unignited["stats"]
    # 234% final Affliction DoT bonus × 65% = 152.1% Fire Hit Damage taken.
    assert ignited["stats"]["true_flame_fire_hit_taken"]["total"] == pytest.approx(1.521)
    assert ignited["offense"]["affliction"]["true_flame_conversion"] == pytest.approx(0.65)
    assert ignited["offense"]["affliction"]["true_flame_fire_taken"] == pytest.approx(1.521)


def test_magnus_prefixed_true_flame_line_is_parsed():
    # Magnus' Mindflame prefixes the shared True Flame wording with its divinity tag.
    text = ("[True Flame] When an enemy is Ignited, 65 % of the additional bonus to Damage Over Time "
            "taken from Affliction is also applied to your Fire Hit Damage")
    assert _parse_custom_mod_text(text) == [{
        "stat_key": "affliction_dot_to_fire_hit", "amount": 0.65, "text": text,
    }]


def test_affliction_cap_is_dynamic_clamped_and_max_predicate_follows_it():
    # The configured snapshot may rise above the legacy base cap; the current cap is 100 + 20.
    at_max = _response(extra_conditions={"affliction_stacks": 120}, custom_mods=["+20 Max Affliction"])
    above_max = _response(extra_conditions={"affliction_stacks": 125}, custom_mods=["+20 Max Affliction"])
    assert at_max["condition_maximums"]["affliction_stacks"] == pytest.approx(120.0)
    assert above_max["clamp_report"]["affliction_stacks"] == {"requested": 125.0, "applied": 120.0}

    # A condition that refers to Max Affliction must use the derived 120 maximum, not a hard-coded 100.
    def gated_result(stacks: float):
        return compute(BuildInput(
            slots=[], slates=[], season="SS13", condition_state={"affliction_stacks": stacks},
            custom_contributions=[
                {"stat_key": "max_affliction_flat", "amount": 20.0, "text": "+20 Max Affliction"},
                {"stat_key": "dmg_inc", "amount": 0.5, "text": "at Max Affliction",
                 "condition": "enemy_has_max_affliction"},
            ],
        ), {}, {})

    assert "dmg_inc" not in gated_result(100.0).stat_map
    assert gated_result(120.0).stat_map["dmg_inc"]["total"] == pytest.approx(0.5)


def test_cataclysm_parser_and_support_contribution_are_slot_local():
    effect_line = "Affliction grants an additional 26.5% effect to the supported skill"
    rate_line = "When the supported skill deals Damage Over Time, it inflicts 8 Affliction on the enemy. Effect Cooldown: 1 s"
    assert _parse_custom_mod_text(effect_line)[0]["stat_key"] == "affliction_effect_additional"
    assert _parse_custom_mod_text(effect_line)[0]["amount"] == pytest.approx(0.265)
    assert _parse_custom_mod_text(rate_line)[0] == {
        "stat_key": "cataclysm_affliction_per_second_flat", "amount": 8.0, "text": rate_line,
    }

    support = {"item_id": "cataclysm", "name": "Cataclysm", "skill_type": "noble_support_skill",
               "description_lines": [effect_line, rate_line], "progression": []}
    contributions = resolve_support_contributions(
        [{"item_id": "cataclysm", "slot": 3, "rank": 1, "level": 1}], {"cataclysm": support},
    )
    by_stat = {entry["stat_key"]: entry for entry in contributions}
    assert by_stat["affliction_effect_additional"]["amount"] == pytest.approx(0.265)
    assert by_stat["cataclysm_affliction_per_second_flat"]["amount"] == pytest.approx(8.0)
    assert {entry["slot"] for entry in by_stat.values()} == {3}


def test_cataclysm_scales_true_flame_only_for_its_supported_slot():
    # Cataclysm's +26.5% additional Effect is slot-local: it amplifies the supported skill's
    # True Flame Fire-hit vulnerability, but must not spill into another skill slot.
    source = aggregate(BuildInput(
        slots=[], slates=[], season="SS13",
        custom_contributions=[
            {"stat_key": "affliction_dot_to_fire_hit", "amount": 0.65, "text": "True Flame"},
        ],
        attached_support_contributions=[
            {"stat_key": "affliction_effect_additional", "amount": 0.265,
             "text": "Cataclysm Effect", "label": "Cataclysm", "slot": 3},
            {"stat_key": "cataclysm_affliction_per_second_flat", "amount": 8.0,
             "text": "Cataclysm Affliction", "label": "Cataclysm", "slot": 3},
        ],
    ), {}, {}, active_booleans=frozenset({"enemy_ignited"}), numeric_vals={"affliction_stacks": 100.0})

    other_slot = source.materialize_for_skill(set(), slot=1)
    supported_slot = source.materialize_for_skill(set(), slot=3)
    assert _enemy_vuln_mult(other_slot, "fire") == pytest.approx(1.65)
    # (1 + 100% Affliction × 65% True Flame × 1.265 Cataclysm Effect).
    assert _enemy_vuln_mult(supported_slot, "fire") == pytest.approx(1.82225)
    assert supported_slot.total("cataclysm_affliction_per_second_flat") == pytest.approx(8.0)
    assert other_slot.total("cataclysm_affliction_per_second_flat") == 0.0


def test_cataclysm_does_not_report_aps_when_supported_skill_has_no_dot():
    rate_line = "When the supported skill deals Damage Over Time, it inflicts 8 Affliction on the enemy. Effect Cooldown: 1 s"
    effect_line = "Affliction grants an additional 26.5 % effect to the supported skill"
    cataclysm = {"item_id": "cataclysm", "name": "Cataclysm", "skill_type": "support_skill",
                 "description_lines": [rate_line, effect_line], "progression": []}
    # A minimal hit-only host resolves with no dot forms. Cataclysm still grants its supported-skill
    # Effect, but its 8/sec rate must not be reported without an active DoT host.
    hit_only_host = {"item_id": "hit_only", "name": "Hit only", "skill_tags": ["Spell"],
                     "description_lines": []}
    contributions, _ = resolve_standard_supports(
        [{"item_id": "cataclysm", "slot": 1, "level": 1}],
        {"cataclysm": cataclysm, "hit_only": hit_only_host}, "spell", [], {},
        slot_cats={1: "spell"}, source=BuildSource(), slot_skill={1: "hit_only"},
    )
    assert {entry["stat_key"] for entry in contributions} == {"affliction_effect_additional"}


def test_magmaskull_cataclysm_fire_bonus_is_max_gated_and_hit_slot_scoped():
    bundled_bonus = {
        "stat_key": "magmaskull_cataclysm_fire_hit_taken", "amount": 0.12,
        "text": "Magmaskull Cataclysm: additional Hit Fire Damage at Max Affliction",
        "label": "Magmaskull", "source_name": "Magmaskull", "slot": 3,
        "condition": "enemy_has_max_affliction",
    }
    def materialized(active: frozenset[str], slot: int) -> BuildSource:
        source = aggregate(BuildInput(slots=[], slates=[], season="SS13",
                                      attached_support_contributions=[bundled_bonus]),
                           {}, {}, active_booleans=active, numeric_vals={})
        return source.materialize_for_skill(set(), slot)

    assert _enemy_vuln_mult(materialized(frozenset(), 3), "fire") == pytest.approx(1.0)
    at_max = materialized(frozenset({"enemy_has_max_affliction"}), 3)
    assert _enemy_vuln_mult(at_max, "fire") == pytest.approx(1.12)
    assert _enemy_vuln_mult(at_max, "fire", is_dot=True) == pytest.approx(1.0)
    assert _enemy_vuln_mult(materialized(frozenset({"enemy_has_max_affliction"}), 1), "fire") == pytest.approx(1.0)


def test_magmaskull_scales_fire_continuously_but_aps_in_effect_steps():
    # 31% Fire-hit-taken per 100% base Effect, capped at 160%; -6 APS per whole +10% Effect.
    gear = [{"name": "Magmaskull", "slot": "helmet", "contributions": [
        {"stat": "magmaskull_initial_affliction_flat", "display_value": 100, "unit": "", "text": "Magmaskull"},
        {"stat": "magmaskull_fire_hit_taken_per_effect", "display_value": 0.31, "unit": "", "text": "Magmaskull"},
        {"stat": "magmaskull_fire_hit_taken_cap", "display_value": 1.60, "unit": "", "text": "Magmaskull"},
        {"stat": "magmaskull_affliction_per_second_per_effect", "display_value": -6, "unit": "", "text": "Magmaskull"},
        {"stat": "magmaskull_affliction_effect_step", "display_value": 0.10, "unit": "", "text": "Magmaskull"},
        {"stat": "affliction_effect_inc", "display_value": 0.55, "unit": "", "text": "+55% Affliction Effect"},
    ]}]
    source = aggregate(BuildInput(slots=[], slates=[], season="SS13", gear=gear), {}, {}, numeric_vals={})
    assert source.total("affliction_initial_flat") == pytest.approx(100.0)
    assert source.total("affliction_per_second_flat") == pytest.approx(-30.0)  # floor(55 / 10) steps
    assert source.total("magmaskull_fire_hit_taken") == pytest.approx(0.31 * 1.55)

    gear[0]["contributions"][-1]["display_value"] = 10.0
    capped = aggregate(BuildInput(slots=[], slates=[], season="SS13", gear=gear), {}, {}, numeric_vals={})
    assert capped.total("magmaskull_fire_hit_taken") == pytest.approx(1.60)


def test_magmaskull_real_implicit_uses_full_effect_product_and_stepped_aps():
    # This is the corroded Magmaskull implicit with an actual 31% roll.  It arrives as raw
    # equipped-line text, so this exercises its real parser -> aggregator recovery path end to end.
    implicit = (
        "Changes the initially inflicted Affliction to 100 Affliction gains an additional effect: "
        "+31 % additional Hit Fire Damage taken, up to +160 % -6 Affliction Per Second "
        "for every +10 % Affliction Effect"
    )
    source = aggregate(BuildInput(
        slots=[], slates=[], season="SS13",
        gear=[{"name": "Magmaskull", "slot": "helmet", "contributions": [{"text": implicit}]}],
        custom_contributions=[
            {"stat_key": "affliction_effect_inc", "amount": 0.50, "text": "+50% Affliction Effect"},
            {"stat_key": "affliction_effect_additional", "amount": 0.20,
             "text": "20% additional Affliction Effect"},
            {"stat_key": "affliction_effect_additional", "amount": 0.30,
             "text": "30% additional Affliction Effect"},
        ],
    ), {}, {}, numeric_vals={})

    # Total Effect is 1.5 × 1.2 × 1.3 = 2.34: Fire scaling is continuous, while APS uses
    # floor((2.34 - 1) / 0.10) = 13 negative-APS steps.
    assert source.total("affliction_initial_flat") == pytest.approx(100.0)
    assert source.total("magmaskull_fire_hit_taken") == pytest.approx(0.31 * 2.34)
    assert source.total("affliction_per_second_flat") == pytest.approx(-78.0)


def test_torturers_touch_uses_full_effect_product_in_whole_steps():
    source = aggregate(BuildInput(
        slots=[], slates=[], season="SS13",
        gear=[{"name": "Torturer's Touch", "slot": "gloves", "contributions": [{
            "text": "+1 Affliction Per Second for every +4% Affliction Effect",
        }]}],
        custom_contributions=[
            {"stat_key": "affliction_effect_inc", "amount": 0.50, "text": "+50% Affliction Effect"},
            {"stat_key": "affliction_effect_additional", "amount": 0.20, "text": "+20% additional Affliction Effect"},
            {"stat_key": "affliction_effect_additional", "amount": 0.30, "text": "+30% additional Affliction Effect"},
        ],
    ), {}, {}, numeric_vals={})
    # (1.5 * 1.2 * 1.3 - 1) = 134% Effect; 33 completed four-percent steps.
    assert source.total("affliction_per_second_flat") == pytest.approx(33.0)


def test_terra_support_reports_its_attack_speed_scaled_affliction_rate():
    terra = {
        "item_id": "corrosive_shot_burst_of_agony_noble", "name": "Burst of Agony",
        "description_lines": [
            "When supported skill's Terra inflicts damage, it inflicts 2 Affliction to enemies.",
            "Interval for each enemy: 0.03 s.",
        ], "progression": [],
    }
    entries = resolve_support_contributions(
        [{"item_id": "corrosive_shot_burst_of_agony_noble", "slot": 2}],
        {"corrosive_shot_burst_of_agony_noble": terra},
    )
    assert entries == [{"stat_key": "terra_affliction_per_second_base", "amount": pytest.approx(2 / .03),
                        "text": "Terra Affliction: 2 every 0.03s", "label": "Burst of Agony",
                        "source_name": "Burst of Agony", "slot": 2}]


def test_black_hole_uses_its_levelled_affliction_dot_bonus_and_reports_rate():
    result = _response(skill_id="black_hole", extra_conditions={"affliction_stacks": 100})
    slots = result["stats"]["affliction_per_second_flat"]["slot_sources"]
    assert any(row["source_name"] == "Black Hole" and row["amount"] == pytest.approx(100.0) for row in slots)
    # Default test skill level is 16; SS13's progression supplies 3.1% per 10 at that level.
    dot_sources = result["stats"]["dot_dmg_additional"]["sources"]
    assert any(row["source_name"] == "Black Hole" and row["amount"] == pytest.approx(0.31) for row in dot_sources)
    assert result["stats"]["affliction_initial_flat"]["total"] == pytest.approx(100.0)


def test_dot_vulnerability_breakdown_names_affliction_source():
    result = _response(
        skill_id="path_of_flames",
        extra_conditions={"affliction_stacks": 100},
        custom_mods=["+50 % Affliction Effect", "20 % additional Affliction Effect"],
    )
    offense = result["offense"]
    # 100% × 1.5 × 1.2 = 180% additional DoT taken, exposed in the shared vulnerability breakdown.
    assert offense["enemy_vuln_by_type"]["fire"] == pytest.approx(2.8)
    assert "affliction_dot_taken" in offense["enemy_vuln_sources_by_type"]["fire"]
    # The selected-skill mechanic panel reads this same materialized payload and the normal source map.
    assert offense["affliction"]["dot_taken"] == pytest.approx(1.8)
    assert offense["affliction"]["effect_additional"] == pytest.approx(0.2)
    assert result["stats"]["affliction_dot_taken"]["slot_sources"][0]["amount"] == pytest.approx(1.8)


def test_fire_hit_and_dot_have_separate_vulnerability_breakdowns():
    source = BuildSource()
    source.add("weapon_attack_speed", 1.0)
    source.add("affliction_dot_taken_base", 1.0)
    source.add("true_flame_fire_hit_taken", 0.65)
    skill = ResolvedSkill(
        skill_id="mixed_fire", name="Mixed Fire", tags=["spell", "fire"], max_level=1,
        hit_forms_by_level={1: [SkillHitForm(name="Fire Hit", effectiveness_pct=1.0,
                                              form_type="additive", base_dmg={"fire": (100.0, 100.0)})]},
        dot_forms_by_level={1: [DotForm(base_per_second=100.0, dtype="fire")]},
        is_spell=True, damage_types=["fire"],
    )
    offense = calculate_offense(source, skill, 1)
    assert offense.enemy_vuln_by_form == {"hit:fire": pytest.approx(1.65), "dot:fire": pytest.approx(2.0)}
    assert "true_flame_fire_hit_taken" in offense.enemy_vuln_sources_by_form["hit:fire"]
    assert "affliction_dot_taken" in offense.enemy_vuln_sources_by_form["dot:fire"]
