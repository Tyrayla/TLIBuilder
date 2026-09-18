"""End-to-end proof of the custom-mod pooling fix (bug-281): drives the REAL request path
(server.engine_stats -> the enumerate(req.custom_mods) line_index tagging -> aggregator's
pooling_uuid stamp -> engine.modifier_lines.pool_identity's source_type == "custom" branch),
not just pool_identity given an already-stamped uuid (that unit-level proof lives in
tests/test_engine_offense.py::TestCustomModPoolingIndependence). Council follow-up from the
2026-09-17 review of bug-280/bug-281.
"""
import pytest

from server import engine_stats, EngineStatsRequest


def _sword(slot):
    def c(stat, val):
        return {"stat": stat, "display_value": val, "unit": "", "item_name": "BL", "text": "base",
                "slot": slot, "condition": None}
    cc = [c("physical_dmg_gear_flat_min", 100), c("physical_dmg_gear_flat_max", 150),
          c("weapon_attack_speed", 1.5)]
    return {"item_name": "BL", "base_type": "One-Handed Sword", "slot": slot, "contributions": cc}


def _dps(custom_mods):
    gear = [_sword("weapon1"), _sword("weapon2")]
    r = engine_stats(EngineStatsRequest(
        slots=[None, None, None, None], gear=gear, custom_mods=custom_mods,
        skills=[{"slot": 1, "skill_id": "focused_slash", "level": 14}],
        main_skill={"skill_id": "focused_slash", "level": 14}, characterLevel=100))
    return r["offense"]["total_dps"]


def test_two_separate_identical_lines_multiply_through_the_real_request_path():
    # Same fix as TestCustomModPoolingIndependence, but through engine_stats end-to-end, so the
    # server.py enumerate() -> line_index -> aggregator pooling_uuid plumbing is actually exercised
    # (not just pool_identity given a hand-stamped uuid).
    baseline = _dps([])
    two_separate_lines = _dps(["+50% additional attack damage", "+50% additional attack damage"])
    one_combined_line = _dps(["+100% additional attack damage"])

    # Two independent x1.5 factors (x2.25) must beat one combined x2.0 factor -- if the server/
    # aggregator plumbing regressed to summing by text again, these would be equal instead.
    assert two_separate_lines > one_combined_line > baseline
    ratio_two_lines = two_separate_lines / baseline
    ratio_one_line = one_combined_line / baseline
    assert ratio_two_lines == pytest.approx(2.25, rel=1e-6)
    assert ratio_one_line == pytest.approx(2.0, rel=1e-6)
