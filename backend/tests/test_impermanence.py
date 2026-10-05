"""Endpoint behavior from SS13 Impermanence text and Help DB conversion rules."""
import pytest

from server import EngineStatsRequest, engine_stats
from tests.mock_build import make_request, weapon
from engine.models import BuildSource
from engine.offense import calculate_offense
from engine.skill_resolver import ResolvedSkill, SkillHitForm


def _result(enabled, *, lo=100, hi=200, mods=(), skill="thunder_spike", crit=0,
            supports=(), conditions=None):
    return engine_stats(EngineStatsRequest(**make_request(
        skill, 20, char_level=1, dual_wield=False,
        gear=[weapon("weapon1", "Endpoint sword", lo, hi, 1, crit)],
        custom_mods=list(mods),
        attached_supports=list(supports), extra_conditions=conditions,
        slots=[{"treeName": "Goddess of Hunting", "nodeStates": {},
                "coreTalentSelections": {"0": "goddess_of_hunting_impermanence"} if enabled else {}},
               None, None, None],
        target_config={"level": 1, "armor": 0, "fireRes": 0, "coldRes": 0,
                       "lightningRes": 0, "erosionRes": 0},
    )))


def test_thunder_spike_impermanence_reshapes_converted_endpoints():
    off = _result(False)["offense"]
    on = _result(True)["offense"]
    # Catalog Lv20 WAD 2.77, intrinsic Physical -> Lightning 100%,
    # existing two independently lasting Numbed stacks at 1 APS give x1.10.
    # OFF 100..200; ON 100*.10*.68 .. 200*1.80*1.32 = 6.8..475.2.
    assert off["hit_forms"][0]["hit_min_by_type"]["lightning"] == pytest.approx(304.7)
    assert off["hit_forms"][0]["hit_max_by_type"]["lightning"] == pytest.approx(609.4)
    assert off["total_dps"] == pytest.approx(457.05)
    assert on["hit_forms"][0]["hit_min_by_type"]["lightning"] == pytest.approx(20.7196)
    assert on["hit_forms"][0]["hit_max_by_type"]["lightning"] == pytest.approx(1447.9344)
    assert on["total_dps"] == pytest.approx(734.327)


@pytest.mark.parametrize("crit, expected", [(0, 734.327), (10000, 1101.4905)])
def test_crit_uses_the_reshaped_average(crit, expected):
    # 100% crit adds the base 50% crit damage to the corrected average, not to endpoints.
    offense = _result(True, crit=crit)["offense"]
    assert offense["crit_chance"] == pytest.approx(crit / 10000)
    assert offense["total_dps"] == pytest.approx(expected)
    assert offense["hit_forms"][0]["hit_max_by_type"]["lightning"] == pytest.approx(1447.9344)


def test_haunt_shadows_use_the_corrected_hit_average():
    # Canonical Haunt Lv1 gives +2 Shadows and -3% additional damage.
    # Help DB Shadow Strike: player + first shadow + .30 second shadow = x2.3.
    support = {"item_id": "haunt", "skill_type": "support_skill", "level": 1}
    off = _result(False, supports=[support])["offense"]
    on = _result(True, supports=[support])["offense"]
    assert on["shadow_count"] == 2
    assert off["total_dps"] == pytest.approx(1019.67855)
    assert on["total_dps"] == pytest.approx(1638.283537)


@pytest.mark.parametrize("active, expected", [(False, 881.1924), (True, 1290.947866)])
def test_rumbling_thunder_buff_keeps_its_gate_and_separate_multiplier(active, expected):
    # Rank5 universal x1.20; Tier1 canonical 45..48% midpoint gives x1.465 when active.
    support = {"item_id": "thunder_spike_rumbling_thunder_noble",
               "skill_type": "noble_support_skill", "rank": 5, "level": 1}
    on = _result(True, supports=[support],
                 conditions={"thunder_spike_true_body_buff": active})["offense"]
    assert on["total_dps"] == pytest.approx(expected)


def test_added_physical_and_native_lightning_are_reshaped_independently():
    # Weapon 100..200 plus added attack Physical 10..20 and Lightning 100..100.
    # Physical converts: min 110*.10*.68=7.48, max 220*1.80*1.32=522.72.
    # Native Lightning only takes generic endpoints 68..132. Final x2.77*x1.10.
    offense = _result(True, mods=("Adds 10-20 Physical Damage to Attacks",
                                 "Adds 100-100 Lightning Damage to Attacks"))["offense"]
    assert offense["hit_forms"][0]["hit_min_by_type"]["lightning"] == pytest.approx(229.98756)
    assert offense["hit_forms"][0]["hit_max_by_type"]["lightning"] == pytest.approx(1994.93184)
    assert offense["total_dps"] == pytest.approx(1112.4597)


def _simple_hit(stats, *, spell=False, conversion=None, compulsory=()):
    source = BuildSource()
    if spell:
        # Cancel the engine's base 500 spell crit rating to isolate roll expectation.
        source.add("spell_crit_rating_flat", -500)
    for key, value in stats.items():
        source.add(key, value)
    skill = ResolvedSkill(
        skill_id="endpoint_control", name="Endpoint control", tags=["Spell" if spell else "Attack"],
        max_level=1, supported=True, main_stat=[], is_spell=spell,
        base_dmg_by_level={1: {"lightning": (100, 100)}} if spell else {},
        base_flat_by_level={1: (100, 100)} if compulsory else {},
        base_cast_time=1, added_dmg_effectiveness=2,
        hit_forms_by_level={1: [SkillHitForm("Hit", 100, "additive")]},
        intrinsic_convert=conversion or {}, compulsory_elements=list(compulsory),
    )
    return calculate_offense(source, skill, 1)


def _endpoints():
    # Exact four factors from canonical Impermanence wording, no parser stubs.
    return {"physical_dmg_min_additional": -.90, "physical_dmg_max_additional": .80,
            "dmg_min_additional": -.32, "dmg_max_additional": .32}


def test_partial_conversion_and_added_as_inherit_physical_endpoints_once():
    offense = _simple_hit({**_endpoints(), "physical_dmg_gear_flat_min": 100,
                          "physical_dmg_gear_flat_max": 200, "weapon_attack_speed": 1,
                          "physical_convert_to_lightning": .5, "physical_as_fire": .25})
    # Staying Physical and converted Lightning each retain half of 6.8..475.2.
    # Added-as Fire retains one quarter, without removing damage from Physical.
    form = offense.hit_forms[0]
    assert form.hit_min_by_type == pytest.approx({"physical": 3.4, "lightning": 3.4, "fire": 1.7})
    assert form.hit_max_by_type == pytest.approx({"physical": 237.6, "lightning": 237.6, "fire": 118.8})
    assert offense.total_dps == pytest.approx(301.25)


def test_multi_hop_conversion_does_not_repeat_endpoint_factors():
    offense = _simple_hit({**_endpoints(), "physical_dmg_gear_flat_min": 100,
                          "physical_dmg_gear_flat_max": 200, "weapon_attack_speed": 1,
                          "physical_convert_to_lightning": 1, "lightning_convert_to_fire": 1})
    assert offense.hit_forms[0].hit_min_by_type == pytest.approx({"fire": 6.8})
    assert offense.hit_forms[0].hit_max_by_type == pytest.approx({"fire": 475.2})
    assert offense.total_dps == pytest.approx(241)


def test_spell_base_and_effective_added_flat_receive_only_generic_endpoints():
    # Spell base 100 plus added 10 at 200% effectiveness = 120, then 81.6..158.4.
    offense = _simple_hit({**_endpoints(), "lightning_spell_dmg_flat_min": 10,
                          "lightning_spell_dmg_flat_max": 10}, spell=True)
    assert offense.hit_forms[0].hit_min_by_type["lightning"] == pytest.approx(81.6)
    assert offense.hit_forms[0].hit_max_by_type["lightning"] == pytest.approx(158.4)
    assert offense.total_dps == pytest.approx(120)


def test_compulsory_element_spell_uses_reshaped_endpoints():
    # Compulsory spell chooses an element for its same 100 base + 20 effective added.
    # Physical endpoint stats must not leak into its Fire or Lightning packets.
    offense = _simple_hit({**_endpoints(), "lightning_spell_dmg_flat_min": 10,
                          "lightning_spell_dmg_flat_max": 10}, spell=True,
                         compulsory=("fire", "lightning"))
    assert offense.hit_forms[0].hit_min_by_type == pytest.approx({"fire": 81.6, "lightning": 81.6})
    assert offense.hit_forms[0].hit_max_by_type == pytest.approx({"fire": 158.4, "lightning": 158.4})
    assert offense.total_dps == pytest.approx(120)


@pytest.mark.parametrize("luck, expected", [("lucky_lightning", 110.6666666667),
                                          ("unlucky_lightning", 89.3333333333)])
def test_roll_expectation_can_legitimately_lower_dps(luck, expected):
    off = _simple_hit({luck: 1}, spell=True)
    on = _simple_hit({**_endpoints(), luck: 1}, spell=True)
    # Flat 100 OFF. ON 68..132. Lucky takes min+2/3 spread, Unlucky min+1/3.
    assert off.total_dps == pytest.approx(100)
    assert on.total_dps == pytest.approx(expected)


def test_zero_damage_and_zero_minimum_boundary():
    zero = _simple_hit(_endpoints())
    boundary = _simple_hit({"physical_dmg_gear_flat_min": 100,
                           "physical_dmg_gear_flat_max": 200, "weapon_attack_speed": 1,
                           "dmg_min_additional": -1})
    assert zero.total_dps == 0
    assert boundary.hit_forms[0].hit_min_by_type["physical"] == 0
    assert boundary.hit_forms[0].hit_max_by_type["physical"] == 200
    assert boundary.total_dps == 100
