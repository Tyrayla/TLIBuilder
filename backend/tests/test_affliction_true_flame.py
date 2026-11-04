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


def test_true_flame_scales_fire_hit_dps_exactly_once():
    # Regression guard for the double-count suspicion: 100 Affliction × 1% = 100% DoT bonus,
    # × 65% True Flame = a single x1.65 Fire-hit factor on total DPS (not 1.65^2, not 2.30).
    tf = ("65 % of the additional bonus to Damage Over Time taken from Affliction is also applied "
          "to your Fire Hit Damage")

    def dps(mods: list[str], ignited: bool = True) -> float:
        r = _response("flame_slash", custom_mods=mods,
                      extra_conditions={"affliction_stacks": 100, "enemy_ignited": ignited})
        return r["offense"]["total_dps"]

    base = dps([])
    assert dps([tf]) / base == pytest.approx(1.65, rel=1e-9)
    assert dps([tf], ignited=False) / base == pytest.approx(1.0, rel=1e-9)
    # +50% increased and 20% additional Effect: 100% × 1.5 × 1.2 = 180% bonus, × 65% = 117%.
    effect = ["+50 % Affliction Effect", "20 % additional Affliction Effect"]
    assert dps([tf, *effect]) / dps(effect) == pytest.approx(2.17, rel=1e-9)


_TF_RAW = ("[True Flame] When an enemy is Ignited , 65 % of the additional bonus to Damage Over Time "
           "taken from Affliction is also applied to your Fire Hit Damage")
_TF_PLAIN = _TF_RAW.split("] ", 1)[1]


def _tf_response(gear: list[dict], custom_mods: list[str] | None = None) -> dict:
    return _response("flame_slash", gear=gear, custom_mods=custom_mods or [],
                     extra_conditions={"affliction_stacks": 100, "enemy_ignited": True})


def _legendary(**extra) -> dict:
    # The payload shape the app's buildGearPayload emits for a legendary "[True Flame] ..." affix:
    # the bracket name rides in granted_talents AND the raw text lands in unresolved_texts.
    return {"contributions": [], "item_name": "Mindflame", "slot": "helmet",
            "unresolved_texts": [_TF_RAW], "granted_talents": ["True Flame"], **extra}


def test_single_legendary_true_flame_is_counted_once():
    # One item granting True Flame was ingested twice (core-talent grant AND plain gear affix text),
    # which is where the owner's x1.3 conversion came from.
    r = _tf_response([_legendary()])
    assert r["stats"]["affliction_dot_to_fire_hit"]["total"] == pytest.approx(0.65)
    assert r["stats"]["true_flame_fire_hit_taken"]["total"] == pytest.approx(0.65)


def test_magnus_mindflame_amulet_true_flame_is_not_doubled():
    # Pinned from the owner's reported build (single Magnus' Mindflame amulet; showed x1.3 / 328.9%
    # instead of x0.65 / 164.5%): the compound "True Flame ... +100 % Skill Area" affix.
    text = _TF_RAW + " +100 % Skill Area"
    amulet = {"contributions": [], "item_name": "Magnus' Mindflame", "slot": "amulet",
              "unresolved_texts": [text], "granted_talents": ["True Flame"]}
    r = _tf_response([amulet])
    assert r["stats"]["affliction_dot_to_fire_hit"]["total"] == pytest.approx(0.65)


def _mindflame_amulet(**extra) -> dict:
    return {"contributions": [], "item_name": "Magnus' Mindflame", "slot": "amulet",
            "unresolved_texts": [_TF_RAW + " +100 % Skill Area"], "granted_talents": ["True Flame"], **extra}


def test_mindflame_compound_affix_applies_true_flame_once_and_skill_area_once():
    # bug-408: the trailing "+100 % Skill Area" of the compound affix was dropped.
    r = _tf_response([_mindflame_amulet()])
    assert r["stats"]["affliction_dot_to_fire_hit"]["total"] == pytest.approx(0.65)
    assert r["stats"]["true_flame_fire_hit_taken"]["total"] == pytest.approx(0.65)
    assert r["stats"]["skill_area_inc"]["total"] == pytest.approx(1.0)


def test_mindflame_skill_area_not_repeated_on_dual_wield_second_slot():
    second_slot_copy = {"contributions": [], "item_name": "Magnus' Mindflame",
                        "unresolved_texts": [_TF_RAW + " +100 % Skill Area"]}
    r = _tf_response([_mindflame_amulet(slot="weapon1"), second_slot_copy])
    assert r["stats"]["affliction_dot_to_fire_hit"]["total"] == pytest.approx(0.65)
    assert r["stats"]["skill_area_inc"]["total"] == pytest.approx(1.0)


def test_other_compound_legendary_affixes_keep_their_trailing_clause_once():
    # Same mechanism for Gale (a talent the resolver fully resolves): its trailing Projectile Speed roll
    # applies while the talent's own 60% conversion stays a single copy.
    gale = ("[Gale] 60 % of the Projectile Speed bonus is also applied to the additional bonus for "
            "Projectile Damage")
    item = {"contributions": [], "item_name": "Gale Item", "slot": "helmet", "granted_talents": ["Gale"]}
    r = _tf_response([{**item, "unresolved_texts": [gale + " +35 % Projectile Speed"]}])
    assert r["core_talent_statuses"][0]["resolved"] is True
    assert r["stats"]["proj_speed_to_proj_dmg"]["total"] == pytest.approx(0.6)
    assert r["stats"]["projectile_speed_inc"]["total"] == pytest.approx(0.35)
    bare = _tf_response([{**item, "unresolved_texts": [gale]}])
    assert "projectile_speed_inc" not in bare["stats"]


def test_unnamed_items_with_identical_companion_are_not_deduped():
    # Dedup is only for the re-emitted same-item copy; unnamed distinct items each keep their companion.
    a = {"contributions": [], "slot": "ring1", "granted_talents": ["True Flame"],
         "unresolved_texts": [_TF_RAW + " +100 % Skill Area"]}
    b = {"contributions": [], "slot": "ring2", "unresolved_texts": [_TF_RAW + " +100 % Skill Area"]}
    r = _tf_response([a, b])
    assert r["stats"]["skill_area_inc"]["total"] == pytest.approx(2.0)
    assert r["stats"]["affliction_dot_to_fire_hit"]["total"] == pytest.approx(0.65)


def test_companion_text_unit():
    from engine.core_talent_resolver import companion_text
    eff = ["A foo , 5 % bar (Max Active Divinity: 1)", "Baz qux."]
    assert companion_text("[T] A foo, 5% bar Baz qux. +10 % Skill Area", eff) == "+10 % Skill Area"
    assert companion_text("[T] A foo, 5% bar Baz qux.", eff) == ""
    assert companion_text("[T] A foo, 5% bar +10 % Skill Area", eff) is None   # second effect absent
    assert companion_text("[T] anything", []) is None


def test_bracket_text_with_unknown_talent_name_is_still_parsed():
    # A granted name the core-talent catalog cannot resolve must not erase the affix: the gear-text
    # parse stays the fallback (never silently drop).
    item = _legendary(granted_talents=["Not A Real Talent"])
    r = _tf_response([item])
    assert r["stats"]["affliction_dot_to_fire_hit"]["total"] == pytest.approx(0.65)


def test_same_item_dual_wield_does_not_repeat_true_flame():
    # buildGearPayload re-emits the unresolved texts (without granted_talents) for the 2nd weapon slot.
    second_slot_copy = {"contributions": [], "item_name": "Mindflame", "unresolved_texts": [_TF_RAW]}
    r = _tf_response([_legendary(slot="weapon1"), second_slot_copy])
    assert r["stats"]["affliction_dot_to_fire_hit"]["total"] == pytest.approx(0.65)


def test_true_flame_is_a_core_talent_and_never_stacks_across_sources():
    # Core talents cannot stack (owner-confirmed): a granted talent plus an independent second source
    # still applies a single 0.65, and DPS gets one x1.65 factor.
    from tests.mock_build import DUAL_WEAPONS
    r = _tf_response([*DUAL_WEAPONS, _legendary()], custom_mods=[_TF_PLAIN])
    assert r["offense"]["affliction"]["true_flame_conversion"] == pytest.approx(0.65)
    assert r["stats"]["true_flame_fire_hit_taken"]["total"] == pytest.approx(0.65)
    base = _response("flame_slash", extra_conditions={"affliction_stacks": 100, "enemy_ignited": True})
    assert r["offense"]["total_dps"] / base["offense"]["total_dps"] == pytest.approx(1.65, rel=1e-9)
