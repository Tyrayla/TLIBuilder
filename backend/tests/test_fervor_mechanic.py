"""
Tests: the Fervor Rating mechanic — Fervor's base effects (today +2% generic Critical Strike Rating
per point) scale per point of Fervor Rating AND are multiplied by Fervor Effect. Driven off the
user-set fervor_rating condition for now.
"""
import pytest
from engine.aggregator import aggregate
from engine.models import BuildInput


def _build(custom=None):
    return BuildInput(slots=[], slates=[], season="t", custom_contributions=custom or [])


def _fervor_effect(frac):
    # Feed fervor_effect_inc into the aggregated source via a custom contribution.
    return [{"stat_key": "fervor_effect_inc", "amount": frac, "text": "Fervor Effect"}]


class TestFervorCrit:
    def test_fervor_rating_grants_generic_crit(self):
        src = aggregate(_build(), {}, {}, numeric_vals={"fervor_rating": 100.0})
        assert src.total("crit_rating_inc") == pytest.approx(2.0)  # 0.02 * 100 = +200%, no Fervor Effect

    def test_fervor_130(self):
        src = aggregate(_build(), {}, {}, numeric_vals={"fervor_rating": 130.0})
        assert src.total("crit_rating_inc") == pytest.approx(2.6)  # +260%

    def test_scales_with_fervor_effect(self):
        # +50% Fervor Effect multiplies the whole base bonus: 0.02 * 100 * (1 + 0.5) = 3.0.
        src = aggregate(_build(_fervor_effect(0.5)), {}, {}, numeric_vals={"fervor_rating": 100.0})
        assert src.total("crit_rating_inc") == pytest.approx(3.0)

    def test_fervor_effect_noop_without_rating(self):
        # Fervor Effect alone (no rating) grants no crit.
        src = aggregate(_build(_fervor_effect(0.5)), {}, {}, numeric_vals={"fervor_rating": 0.0})
        assert src.total("crit_rating_inc") == 0.0

    def test_no_fervor_no_crit(self):
        assert aggregate(_build(), {}, {}, numeric_vals={}).total("crit_rating_inc") == 0.0

    def test_logged_as_source(self):
        src = aggregate(_build(), {}, {}, numeric_vals={"fervor_rating": 50.0})
        entry = next(e for e in src.source_log if e.stat == "crit_rating_inc")
        assert entry.label == "Fervor Rating" and entry.source_type == "condition"


def _run_public(item_name=None, lines=(), rating=100.0, custom_mods=()):
    from server import EngineStatsRequest, engine_stats
    from tests.mock_build import DUAL_WEAPONS, make_request

    gear = list(DUAL_WEAPONS)
    if item_name:
        slot = "gloves" if item_name == "Ghost Slaughter" else "boots"
        gear.append({"item_name": item_name, "slot": slot,
                     "unresolved_texts": list(lines), "contributions": []})
    request = make_request("berserking_blade", 20, gear=gear,
                           extra_conditions={"fervor_rating": rating})
    request["custom_mods"] = list(custom_mods)
    result = engine_stats(EngineStatsRequest(**request))
    return result if isinstance(result, dict) else result.model_dump()


def _total(result, stat):
    return result["stats"].get(stat, {}).get("total", 0.0)


def test_ghost_slaughter_base_effects_are_item_gated_and_scale_with_rating():
    area = "Fervor gains an additional base effect: +1% Skill Area for every 3 Fervor Rating"
    damage = "Fervor gains an additional base effect: +3% additional Attack and Ailment Damage for every 4 Fervor Rating"
    without = _run_public(rating=100)
    with_item = _run_public("Ghost Slaughter", [area, damage], rating=100)
    half_rating = _run_public("Ghost Slaughter", [area, damage], rating=50)

    assert _total(without, "skill_area_inc") == 0.0
    assert _total(without, "attack_dmg_additional") == 0.0
    assert _total(without, "ailment_dmg_additional") == 0.0
    assert _total(with_item, "skill_area_inc") == pytest.approx(0.01 / 3 * 100, abs=1e-6)
    assert _total(with_item, "attack_dmg_additional") == pytest.approx(0.03 / 4 * 100)
    assert _total(with_item, "ailment_dmg_additional") == pytest.approx(0.03 / 4 * 100)
    assert _total(half_rating, "skill_area_inc") == pytest.approx(0.01 / 3 * 50, abs=1e-6)


def test_ghost_slaughter_stronger_damage_variant_and_fervor_effect():
    area = "Fervor gains an additional base effect: +1% Skill Area for every 3 Fervor Rating +(30–50) % Skill Area"
    damage = "Fervor gains an additional base effect: +1% additional Attack and Ailment Damage for every 1 Fervor Rating"
    result = _run_public("Ghost Slaughter", [area, damage], rating=100,
                         custom_mods=["+50% Fervor Effect"])

    assert _total(result, "skill_area_inc") == pytest.approx(0.01 / 3 * 100 * 1.5 + 0.40, abs=1e-6)
    assert _total(result, "attack_dmg_additional") == pytest.approx(0.01 * 100 * 1.5)
    assert _total(result, "ailment_dmg_additional") == pytest.approx(0.01 * 100 * 1.5)


def test_ralphs_footsteps_movement_speed_and_corrupted_fervor_effect():
    movement = "Fervor gains an additional base effect: +1% Movement Speed for every 5 Fervor Rating"
    regular = _run_public("Ralph's Footsteps", [movement], rating=100)
    corrupted = _run_public("Ralph's Footsteps",
                            [movement + " +20 % Fervor effect"], rating=100)
    without = _run_public(rating=100)

    assert _total(without, "movement_speed") == 0.0
    assert _total(regular, "movement_speed") == pytest.approx(0.01 / 5 * 100)
    assert _total(corrupted, "movement_speed") == pytest.approx(0.01 / 5 * 100 * 1.2)
