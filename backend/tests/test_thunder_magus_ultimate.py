"""Thunder Magus Ultimate per-cast data for Iris selection."""
import json

import pytest

from engine.models import BuildSource
from engine.minion_offense import MINION_MODULES
from persistence import season_manager


def _owner():
    skills = json.load(open(season_manager._season_dir("SS12") + "/_skills.json", encoding="utf-8"))["skills"]
    return next(skill for skill in skills if skill["item_id"] == "summon_thunder_magus")


def _base_stats():
    return {
        "constants": {"crit_rating_flat": 0, "crit_damage": 100},
        "base_damage_by_level": {"1": 1000, "20": 1000},
        "life_by_group": {"magus": {}, "synthetic_troop": {}},
    }


def test_lightning_surge_exposes_seven_full_hits_without_default_dps():
    import engine.minion_effects  # noqa: F401 -- populate MINION_MODULES

    owner = _owner()
    result = MINION_MODULES[owner["item_id"]](BuildSource(), owner, _base_stats(), 20, 1)
    form = result.minion_skill_casts["ultimate"]
    hit = form["hit_breakdown"]["hit_forms"][0]

    # SS12/SS13 level 20 coefficient is 301%. Owner-tested hit count is seven, all at full damage.
    # 1000 base damage * 301% * 7 hits = 21070 per cast, with zero crit chance and no modifiers.
    assert form["damage_per_cast"] == pytest.approx(21070)
    assert form["hits_per_cast"] == form["hits_per_target"] == form["chains_per_cast"] == 7
    assert hit["hit_min_by_type"]["lightning"] == pytest.approx(3010)
    assert hit["hit_max_by_type"]["lightning"] == pytest.approx(3010)
    assert hit["hits_per_fire"] == 7
    assert hit["shotgun_falloff"] == 0
    assert form["base_cast_time"] == form["cast_time"] == pytest.approx(1.5)
    assert form["base_cooldown"] == form["cooldown"] == pytest.approx(8)
    assert form["casts_per_second"] == pytest.approx(0.125)
    assert form["included_in_default_dps"] is False
    assert form["name"] == "Lightning Surge (Ultimate)"
    assert "Lightning Surge (Ultimate)" not in [f.name for f in result.hit_forms]
    assert result.minion_ultimate["max_targets"] == 8
    assert result.minion_ultimate["chain_interval_seconds"] == pytest.approx(0.25)
    assert result.minion_ultimate["bolt_travel_distance_m_estimate"] == 6
    assert result.minion_ultimate["bolt_travel_time_seconds_estimate"] == 1
    assert result.minion_ultimate["chain_targeting_radius_m_estimate"] == 12
    assert "not independently verified" in result.minion_ultimate["verification_note"]
    without_ultimate = dict(owner)
    without_ultimate["minion_skills"] = [
        skill for skill in owner["minion_skills"] if skill["item_id"] != "lightning_surge"
    ]
    baseline = MINION_MODULES[owner["item_id"]](BuildSource(), without_ultimate, _base_stats(), 20, 1)
    assert result.total_dps == pytest.approx(baseline.total_dps)


def test_lightning_surge_projectile_quantity_adds_targets_not_hits_or_bolts():
    import engine.minion_effects  # noqa: F401 -- populate MINION_MODULES

    owner = _owner()
    source = BuildSource()
    source.add("spirit_magi_initial_growth_flat", 200)  # Stage 3; no Ultimate projectile bonus.
    source.add("minion_projectile_quantity_flat", 2)
    result = MINION_MODULES[owner["item_id"]](source, owner, _base_stats(), 20, 1)
    ultimate = result.minion_skill_casts["ultimate"]

    assert ultimate["damage_per_cast"] == pytest.approx(21070)
    assert ultimate["hits_per_target"] == 7
    assert result.minion_ultimate["max_targets"] == 10


def test_lightning_surge_uses_spirit_magi_cooldown_recovery():
    import engine.minion_effects  # noqa: F401 -- populate MINION_MODULES

    owner = _owner()
    source = BuildSource()
    source.add("spirit_magi_cdr_speed_inc", 0.5)
    result = MINION_MODULES[owner["item_id"]](source, owner, _base_stats(), 20, 1)
    ultimate = result.minion_skill_casts["ultimate"]

    assert ultimate["cooldown"] == pytest.approx(8 / 1.5)
    assert ultimate["casts_per_second"] == pytest.approx(1.5 / 8)


def test_lightning_surge_separates_base_coefficient_from_added_damage_effectiveness():
    import engine.minion_effects  # noqa: F401 -- populate MINION_MODULES

    owner = _owner()
    ultimate_skill = next(skill for skill in owner["minion_skills"] if skill["item_id"] == "lightning_surge")
    # Isolate the two data fields: 250% base coefficient and 175% added-damage effectiveness.
    ultimate_skill["base_damage_coefficient"] = {"20": 250}
    ultimate_skill["effectiveness_of_added_damage"] = "175%"
    next(row for row in ultimate_skill["progression"] if row["level"] == 20)["values"][
        "Effectiveness of added damage"
    ] = "175%"
    source = BuildSource()
    source.add("minion_lightning_dmg_flat_min", 10)
    source.add("minion_lightning_dmg_flat_max", 10)

    result = MINION_MODULES[owner["item_id"]](source, owner, _base_stats(), 20, 1)
    form = result.minion_skill_casts["ultimate"]
    hit = form["hit_breakdown"]["hit_forms"][0]

    # (1000 base * 250%) + (10 flat * 175%) = 2517.5 per hit; seven full hits = 17622.5.
    assert hit["hit_min_by_type"]["lightning"] == pytest.approx(2517.5)
    assert hit["hit_max_by_type"]["lightning"] == pytest.approx(2517.5)
    assert form["damage_per_cast"] == pytest.approx(17622.5)
    assert any("always Penetrate" in note for note in form["hit_breakdown"]["nyi"])
