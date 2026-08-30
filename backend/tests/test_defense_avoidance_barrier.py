"""
Tests for the WS1 defensive additions: Blur -> Chance to Avoid Damage (with the 60% cap) and the Barrier
absorb pool (shield formula + absorption-rate clamp), plus the consumed-stat contract for the stats that are
read unconditionally so they register even when the mechanic is inactive.

Sources (needs-verification): TLI Help Database — Blur.md, Chance to Avoid Damage.md, Barrier.md.
"""
from engine.models import BuildSource
from engine.defense import calculate_defense, _MAX_DMG_AVOID_CHANCE, _BASE_BARRIER_ABSORPTION_RATE
from engine.consumable_universe import consumable_universe


def _source(cond=None, **stats) -> BuildSource:
    s = BuildSource()
    for k, v in stats.items():
        s.add(k, v)
    if cond:
        s.condition_state = dict(cond)   # BuildSource() has no condition_state attr until set (custom init)
    return s


# ── Blur -> Chance to Avoid Damage ──────────────────────────────────────────────

def test_blur_inactive_no_avoidance():
    d = calculate_defense(_source(blur_effect_inc=1.0))  # effect present but Blur off
    assert d.dmg_avoid_blur == 0.0
    assert d.dmg_avoid_chance == 0.0


def test_blur_active_base_is_25pct():
    d = calculate_defense(_source(cond={"blur_active": True}))
    assert d.dmg_avoid_blur == 0.25          # 100 rating x 0.25%
    assert d.dmg_avoid_chance == 0.25


def test_blur_effect_scales_avoidance():
    # 100 rating x 0.25% x (1 + 100% Blur Effect) = 50%
    d = calculate_defense(_source(cond={"blur_active": True}, blur_effect_inc=1.0))
    assert d.dmg_avoid_blur == 0.50
    assert d.dmg_avoid_chance == 0.50


def test_avoidance_capped_at_60pct():
    # gear 50% + Blur 50% = 100% raw, clamped to the 60% ceiling; the Blur attribution stays pre-cap.
    d = calculate_defense(_source(cond={"blur_active": True}, dmg_avoid_chance=0.50, blur_effect_inc=1.0))
    assert d.dmg_avoid_chance == _MAX_DMG_AVOID_CHANCE == 0.60
    assert d.dmg_avoid_blur == 0.50


# ── Barrier ─────────────────────────────────────────────────────────────────────

def test_barrier_pool_is_20pct_of_life_plus_es():
    d = calculate_defense(_source(max_life=1000.0, max_energy_shield=500.0))
    assert d.barrier_shield == 0.20 * 1500.0          # 300
    assert d.barrier_absorption_rate == _BASE_BARRIER_ABSORPTION_RATE == 0.50
    assert d.barrier_active is False


def test_barrier_shield_scales_by_increased_and_additional():
    d = calculate_defense(_source(
        max_life=1000.0, max_energy_shield=0.0,
        barrier_shield_inc=0.5, barrier_shield_additional=0.2,
    ))
    # 20% of 1000 = 200; x (1 + 0.5) = 300; x (1 + 0.2) = 360
    assert d.barrier_shield == 200.0 * 1.5 * 1.2


def test_barrier_absorption_rate_clamped_to_100pct():
    d = calculate_defense(_source(barrier_absorption_rate_inc=2.0))  # 50% x 3 = 150% -> clamp
    assert d.barrier_absorption_rate == 1.0


def test_barrier_active_gate():
    d = calculate_defense(_source(cond={"barrier_active": True}, max_life=1000.0))
    assert d.barrier_active is True


# ── Consumed-stat contract (unconditional reads register even when inactive) ─────

def test_new_defensive_stats_are_consumed():
    universe = consumable_universe()
    for key in ("blur_effect_inc", "dmg_avoid_chance",
                "barrier_shield_inc", "barrier_shield_additional", "barrier_absorption_rate_inc"):
        assert key in universe, f"{key} must be in the consumable universe"
