"""Demolisher Charge subsystem + Groundshaker tests.

Covers the restoration formula (increased-only), the charged-vs-uncharged split (mismatch), the bidirectional
restoration↔cadence breakpoint, ENUM fissure gating, the Cripple spread penalty, the Frequent Quake 5-hit
transform + relabel, the Collapse step function, and Wrathful Vault. Demolisher now CONSUMES the resolved cast
rate (from a trigger medium or manual APS) — the cadence comes from the equipped Rhythm medium's interval roll.
"""
from __future__ import annotations
import pytest

from tests.mock_build import make_request, DUAL_WEAPONS
from server import engine_stats, EngineStatsRequest
from engine.offense import compute_demolisher_rate

RHYTHM = "activation_medium_rhythm"
FQ = "groundshaker_frequent_quake_magnificent"
COLLAPSE = "groundshaker_collapse_noble"
CRIPPLE = "groundshaker_cripple_noble"
EPICENTER = "groundshaker_epicenter_magnificent"
WRATHFUL = "groundshaker_wrathful_vault_noble"


class _Src:
    """Minimal BuildSource stand-in — compute_demolisher_rate only reads demolisher_charge_speed_inc."""
    def __init__(self, inc: float = 0.0):
        self._inc = inc

    def total(self, key: str) -> float:
        return self._inc if key == "demolisher_charge_speed_inc" else 0.0


def _sup(item_id, level=1, slot=1, **kw):
    return {"slot": slot, "item_id": item_id, "level": level, "enabled": True, **kw}


def _rhythm(interval: float | None = None, tier: int = 1):
    """A Rhythm medium; when `interval` is given it pins the trigger-interval roll (→ cast rate = 1/interval)."""
    s = _sup(RHYTHM)
    if interval is not None:
        s["specific_rolls"] = {"trigger_interval": interval}
        s["specific_roll_tiers"] = {"trigger_interval": tier}
    return s


def _offense(supports, cond=None, level=20):
    req = make_request("groundshaker", level, attached_supports=supports, extra_conditions=cond)
    return engine_stats(EngineStatsRequest(**req)).get("offense") or {}


# ── Pure-math: compute_demolisher_rate (now consumes a resolved cast_rate) ──────
def test_restoration_increased_only():
    assert compute_demolisher_rate(_Src(0.0), 1.0, 3.0)["restoration_time"] == pytest.approx(3.0)
    assert compute_demolisher_rate(_Src(2.0), 1.0, 3.0)["restoration_time"] == pytest.approx(1.0)  # 3/(1+2)


def test_zero_base_restore_is_inert():
    r = compute_demolisher_rate(_Src(1.0), 2.0, 0.0)
    assert r["cast_rate"] == 0.0 and r["charged_rate"] == 0.0 and r["restoration_time"] == 0.0


def test_cast_rate_echoed():
    assert compute_demolisher_rate(_Src(0.0), 2.4, 3.0)["cast_rate"] == pytest.approx(2.4)


def test_charged_capped_by_restoration_when_slow():
    r = compute_demolisher_rate(_Src(0.0), 1.0, 3.0)   # cadence 1s, restoration 3s
    assert r["mismatch"] is True
    assert r["charged_rate"] == pytest.approx(1.0 / 3.0)


def test_every_cast_charged_when_restoration_fast():
    r = compute_demolisher_rate(_Src(2.0), 1.0, 3.0)   # restoration 1s == cadence 1s
    assert r["mismatch"] is False
    assert r["charged_rate"] == pytest.approx(r["cast_rate"])


def test_breakpoint_under_needs_more_charge_speed():
    r = compute_demolisher_rate(_Src(0.0), 1.0, 3.0)   # need (1+inc) ≥ 3/1 → inc ≥ 2.0
    assert r["under_breakpoint"] is True
    assert r["restore_to_sustain"] == pytest.approx(2.0)
    assert r["cdr_droppable"] == 0.0


def test_breakpoint_over_reports_droppable():
    r = compute_demolisher_rate(_Src(3.0), 1.0, 3.0)
    assert r["over_breakpoint"] is True
    assert r["cdr_droppable"] == pytest.approx(1.0)


def test_breakpoint_exact():
    r = compute_demolisher_rate(_Src(2.0), 1.0, 3.0)
    assert r["under_breakpoint"] is False and r["over_breakpoint"] is False


# ── Engine integration ─────────────────────────────────────────────────────────
def test_engine_detects_demolisher_mode():
    o = _offense([_rhythm(1.0)])
    assert o["demolisher_mode"] == "rhythm"
    assert o["demolisher_base_restore"] == pytest.approx(3.0)
    assert o["demolisher_cast_rate"] == pytest.approx(1.0)
    assert [f["name"] for f in o["hit_forms"]] == ["Primary Fissure", "Secondary Explosion"]


def test_manual_mode_without_medium():
    o = _offense([])
    assert o["demolisher_mode"] == "manual" and o["demolisher_cast_rate"] > 0


def test_enum_primary_only_zeroes_secondary():
    o = _offense([_rhythm(1.0)], {"groundshaker_area_selector": "Primary Fissure only"})
    forms = {f["name"]: f["dps_vs_target"] for f in o["hit_forms"]}
    assert forms["Primary Fissure"] > 0 and forms["Secondary Explosion"] == 0.0
    assert o["demolisher_area_mode"] == "primary"


def test_enum_secondary_only_zeroes_primary():
    o = _offense([_rhythm(1.0)], {"groundshaker_area_selector": "Secondary Explosion only"})
    forms = {f["name"]: f["dps_vs_target"] for f in o["hit_forms"]}
    assert forms["Primary Fissure"] == 0.0 and forms["Secondary Explosion"] > 0


def test_enum_both_is_sum():
    both = _offense([_rhythm(1.0)], {"groundshaker_area_selector": "Both"})
    prim = _offense([_rhythm(1.0)], {"groundshaker_area_selector": "Primary Fissure only"})
    sec = _offense([_rhythm(1.0)], {"groundshaker_area_selector": "Secondary Explosion only"})
    assert both["total_dps_vs_target"] == pytest.approx(
        prim["total_dps_vs_target"] + sec["total_dps_vs_target"], rel=1e-6)


def test_frequent_quake_relabels_secondary_form():
    o = _offense([_rhythm(1.0), _sup(FQ)])
    assert [f["name"] for f in o["hit_forms"]] == ["Primary Fissure", "Fissure Ticks (Frequent Quake)"]
    prim = next(f for f in o["hit_forms"] if f["name"] == "Primary Fissure")
    ticks = next(f for f in o["hit_forms"] if f["name"].startswith("Fissure Ticks"))
    assert ticks["avg_hit_with_crit"] == pytest.approx(prim["avg_hit_with_crit"], rel=1e-6)
    assert o["demolisher_frequent_quake"] is True


def test_collapse_step_function():
    # roll ~0.65 (mid of 60–70). floor(1.6/R): R=1.0 → 1 → +32.5%; R=0.6 → 2 → +65%.
    sups = [_sup(FQ), _sup(COLLAPSE)]
    o10 = _offense([_rhythm(1.0)] + sups)
    o06 = _offense([_rhythm(0.6)] + sups)
    assert o10["demolisher_collapse_pct"] == pytest.approx(1 * 0.5 * 0.65, abs=1e-6)
    assert o06["demolisher_collapse_pct"] == pytest.approx(2 * 0.5 * 0.65, abs=1e-6)


def test_collapse_boundary_averaged_at_0p8():
    o = _offense([_rhythm(0.8), _sup(FQ), _sup(COLLAPSE)])
    assert o["demolisher_collapse_pct"] == pytest.approx(1.5 * 0.5 * 0.65, abs=1e-6)


def test_collapse_requires_frequent_quake():
    o = _offense([_rhythm(1.0), _sup(COLLAPSE)])
    assert o["demolisher_collapse_pct"] == 0.0


def test_cripple_penalises_primary_not_explosion():
    plain = _offense([_rhythm(1.0)])
    crip = _offense([_rhythm(1.0), _sup(CRIPPLE)])
    assert crip["demolisher_primary_dps"] < plain["demolisher_primary_dps"]
    assert crip["demolisher_secondary_dps"] >= plain["demolisher_secondary_dps"]


def test_rhythm_interval_default_from_support():
    # No pinned roll → the Rhythm interval defaults to its tier-1 band midpoint 0.4 → cast rate 2.5.
    o = _offense([_sup(RHYTHM)])
    assert o["demolisher_mode"] == "rhythm"
    assert o["demolisher_cast_rate"] == pytest.approx(2.5, abs=1e-6)


def test_wrathful_vault_mobility_tag_and_manual():
    o = _offense([_sup(WRATHFUL)])
    assert o["demolisher_mode"] == "manual"
    assert "mobility" in [t.lower() for t in o["skill_tags"]]


def test_wrathful_vault_movement_to_attack_speed_capped():
    ms = [{"item_name": "MS Boots", "contributions": [
        {"stat": "movement_speed_inc", "display_value": 1.0, "unit": "", "slot": "boots",
         "item_name": "MS Boots", "text": "MS:movement_speed_inc"}]}]

    def run(sups, gear):
        return engine_stats(EngineStatsRequest(**make_request(
            "groundshaker", 20, attached_supports=sups, gear=gear))).get("offense") or {}
    base = run([_sup(WRATHFUL)], DUAL_WEAPONS)
    boosted = run([_sup(WRATHFUL)], DUAL_WEAPONS + ms)
    assert boosted["skills_per_second"] == pytest.approx(base["skills_per_second"] * 1.60, rel=1e-6)
    assert run([], DUAL_WEAPONS + ms)["skills_per_second"] == pytest.approx(base["skills_per_second"], rel=1e-6)
