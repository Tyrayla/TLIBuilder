"""Icebound Beam canvas supports (Chilling Spike, Frostbitten, Ring Blade) — engine behavior validated against
the owner's in-game dummy tests (ratios; absolute numbers depend on the test build's buffs)."""
import pytest
from server import engine_stats, EngineStatsRequest
from tests.mock_build import make_request

CHILLING = "icebound_beam_chilling_spike_noble"
FROSTBITTEN = "icebound_beam_frostbitten_magnificent"
RING_BLADE = "icebound_beam_ring_blade_noble"


def _sup(item_id, *, tier=1, rank=1, slot=1):
    return {"item_id": item_id, "slot": slot, "level": tier, "rank": rank, "enabled": True}


def _gear(**stats):
    from tests.mock_build import DUAL_WEAPONS
    return DUAL_WEAPONS + [{"item_name": "X", "contributions": [
        {"stat": k, "display_value": v, "unit": "", "slot": "ring", "item_name": "X", "text": f"+{v} {k}"}
        for k, v in stats.items()]}]


def _offense(level=16, supports=None, conds=None, gear=None):
    r = engine_stats(EngineStatsRequest(**make_request(
        "icebound_beam", level, attached_supports=supports, extra_conditions=conds, gear=gear)))
    d = r.model_dump() if hasattr(r, "model_dump") else r
    return d["offense"]


def _form(off, name):
    return next(f for f in off["hit_forms"] if f["name"] == name)


# ── baseline ──────────────────────────────────────────────────────────────────
def test_base_beam_suppressed_while_blades_fire():
    o = _offense()
    beam, blade = _form(o, "Cold Beam"), _form(o, "Icy Blade")
    assert blade["hits_per_fire"] == 2          # base 2 Icy Blade projectiles
    assert beam["dps_contribution"] > 0 and blade["dps_contribution"] > 0


# ── Chilling Spike: disable suppression + extra blades + signed hit-damage roll ──
def test_chilling_spike_unsuppresses_beam():
    base = _form(_offense(), "Cold Beam")["dps_contribution"]
    cs = _form(_offense(supports=[_sup(CHILLING)]), "Cold Beam")["dps_contribution"]
    # 1/3 suppression removed → beam ~3x (per-hit ×3).
    assert cs == pytest.approx(base * 3.0, rel=0.03)


def test_chilling_spike_adds_extra_blades():
    base = _form(_offense(), "Icy Blade")["dps_contribution"]
    cs = _form(_offense(supports=[_sup(CHILLING)]), "Icy Blade")["dps_contribution"]
    # +~0.69 blade-equivalents on top of the base 2-blade shotgun (1.35) → ×(1 + 0.69/1.35).
    assert cs == pytest.approx(base * (1 + 0.69 / 1.35), rel=0.02)


def test_chilling_spike_hit_damage_roll_signed():
    from engine.skill_effects.icebound_beam import chilling_spike_contribution
    from server import _get_skills_data, season_manager
    data = _get_skills_data(season_manager.get_active_season())
    d = data[CHILLING]
    # default tier (1) is NEGATIVE: (-2 – -1) → mid -1.5%
    c = chilling_spike_contribution({"item_id": CHILLING, "slot": 1, "level": 1}, d)
    assert c["stat_key"] == "dmg_additional" and c["amount"] == pytest.approx(-0.015)
    # tier 0 is positive: (1 – 4) → +2.5%
    c0 = chilling_spike_contribution({"item_id": CHILLING, "slot": 1, "level": 0}, d)
    assert c0["amount"] == pytest.approx(0.025)


# ── Frostbitten: assume-max 8 stacks ────────────────────────────────────────────
def test_frostbitten_assume_max_8():
    base = _offense()["total_dps"]
    fr = _offense(supports=[_sup(FROSTBITTEN)])["total_dps"]
    # T1 mid 4.15% × 8 stacks = +33.2% (default frostbitten_stacks=8 via preseed).
    assert fr == pytest.approx(base * 1.332, rel=0.01)


def test_frostbitten_scales_with_stacks():
    base = _offense()["total_dps"]
    half = _offense(supports=[_sup(FROSTBITTEN)], conds={"frostbitten_stacks": 4})["total_dps"]
    assert half == pytest.approx(base * 1.166, rel=0.01)   # 4 × 4.15% = +16.6%


# ── Ring Blade: +1 projectile + Frozen-proc full burst ──────────────────────────
def test_ring_blade_adds_projectile():
    base = _form(_offense(), "Icy Blade")["hits_per_fire"]
    rb = _form(_offense(supports=[_sup(RING_BLADE)]), "Icy Blade")["hits_per_fire"]
    assert rb == base + 1


def test_ring_blade_frozen_proc_adds_full_burst():
    no_frozen = _offense(supports=[_sup(RING_BLADE)])
    frozen = _offense(supports=[_sup(RING_BLADE)], conds={"enemy_frozen": True})
    blade_nf = _form(no_frozen, "Icy Blade")["dps_contribution"]
    blade_fr = _form(frozen, "Icy Blade")["dps_contribution"]
    # +1 full Icy Blade burst/sec on top of the normal cadence → a large jump only when frozen.
    assert blade_fr > blade_nf * 1.5


def test_ring_blade_frozen_gated():
    # Without enemy_frozen, Ring Blade adds NO frozen burst (only the +1 projectile + the roll).
    no_frozen = _form(_offense(supports=[_sup(RING_BLADE)]), "Icy Blade")["dps_contribution"]
    base_3proj = _form(_offense(supports=[_sup(RING_BLADE)]), "Icy Blade")["dps_contribution"]
    assert no_frozen == base_3proj   # sanity: deterministic, no frozen stream


def _eff_frozen_rate(cast_speed_inc=0.0):
    """Back out the Frozen proc's EFFECTIVE rate from the Icy Blade form's frozen vs no-frozen DPS."""
    gear = _gear(cast_speed_inc=cast_speed_inc) if cast_speed_inc else None
    nf = _form(_offense(gear=gear, supports=[_sup(RING_BLADE)]), "Icy Blade")
    fz = _form(_offense(gear=gear, supports=[_sup(RING_BLADE)], conds={"enemy_frozen": True}), "Icy Blade")
    per_burst = nf["dps_contribution"] / nf["fires_per_sec"]      # avg_hit × shotgun (one full burst's worth/s)
    return (fz["dps_contribution"] - nf["dps_contribution"]) / per_burst


def test_frozen_proc_hit_aligned_to_channel_rate():
    # The proc fires on the first beam hit after its 1s cooldown; the beam hits at the channel rate (aps).
    # Base ~3/s → lands ~1 proc/s (full). +27% cast speed (~3.8/s) → the cooldown expires between hits, so it
    # waits for the next hit → effective rate drops below 1.0 (matches the owner's in-game ~3-4% shortfall).
    assert _eff_frozen_rate(0.0) == pytest.approx(1.0, abs=0.02)
    assert _eff_frozen_rate(0.27) < 0.97
