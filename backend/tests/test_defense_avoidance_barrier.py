"""
Tests for the WS1 defensive additions: Blur -> Chance to Avoid Damage (with the 60% cap) and the Barrier
absorb pool (shield formula + absorption-rate clamp), plus the consumed-stat contract for the stats that are
read unconditionally so they register even when the mechanic is inactive.

Sources (needs-verification): TLI Help Database — Blur.md, Chance to Avoid Damage.md, Barrier.md.
"""
from engine.models import BuildSource
from engine.defense import (
    calculate_defense, calculate_incoming, _MAX_DMG_AVOID_CHANCE, _BASE_BARRIER_ABSORPTION_RATE,
)
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


# ── Incoming damage → Max Hit / EHP (WS3) ────────────────────────────────────────

def _incoming(cond=None, enemy=None, **stats):
    s = _source(cond=cond, **stats)
    if enemy is not None:
        s.enemy_config = enemy
    return calculate_incoming(s, calculate_defense(s))


def test_resistance_mitigates_hit_and_dot():
    inc = _incoming(fire_resistance=0.30,
                    enemy={"kind": "attack", "damage": {"fire_hit": 1000.0, "fire_dot": 500.0}})
    fire = inc["types"]["fire"]
    assert fire["mitigated_hit"] == 700.0          # 1000 × (1 − 0.30)
    assert fire["mitigated_dot"] == 350.0          # DoT also takes resistance


def test_physical_hit_has_no_resistance():
    inc = _incoming(enemy={"kind": "attack", "damage": {"phys_hit": 1000.0}})
    assert inc["types"]["physical"]["mitigated_hit"] == 1000.0   # no armour, no resistance


def test_dot_skips_armour_but_hit_does_not():
    # Big armour so physical hit is mitigated; the DoT ignores armour (mitigated == incoming).
    inc = _incoming(armor=50000.0, enemy={"kind": "attack", "damage": {"phys_hit": 1000.0, "phys_dot": 1000.0}})
    phys = inc["types"]["physical"]
    assert phys["mitigated_hit"] < 1000.0
    assert phys["mitigated_dot"] == 1000.0


def test_max_hit_is_pool_over_taken_fraction():
    inc = _incoming(max_life=5000.0, max_energy_shield=1000.0, fire_resistance=0.30,
                    enemy={"kind": "attack", "damage": {"fire_hit": 1000.0}})
    fire = inc["types"]["fire"]
    assert inc["pool"] == 6000.0
    assert round(fire["max_hit"], 2) == round(6000.0 / 0.70, 2)   # pool ÷ 0.70


def test_ehp_folds_avoidance_and_block_for_hits():
    # Blur active → 25% avoid; Max Hit ignores it, EHP divides by (1 − 0.25).
    inc = _incoming(cond={"blur_active": True}, max_life=6000.0,
                    enemy={"kind": "attack", "damage": {"fire_hit": 1000.0}})
    fire = inc["types"]["fire"]
    assert round(fire["ehp"], 2) == round(fire["max_hit"] / (1.0 - 0.25), 2)


def test_full_immunity_yields_none_max_hit():
    # 100% damage-taken reduction → taken fraction 0 → Max Hit / EHP are None (the UI renders '∞').
    inc = _incoming(dmg_taken_additional=-1.0, max_life=5000.0,
                    enemy={"kind": "attack", "damage": {"fire_hit": 1000.0}})
    fire = inc["types"]["fire"]
    assert fire["hit_taken_fraction"] == 0.0
    assert fire["mitigated_hit"] == 0.0
    assert fire["max_hit"] is None
    assert fire["ehp"] is None


def test_barrier_inactive_hit_capacity_equals_pool():
    inc = _incoming(max_life=1000.0, max_energy_shield=1000.0,
                    enemy={"kind": "attack", "damage": {"phys_hit": 100.0}})
    assert inc["pool"] == 2000.0
    assert inc["hit_capacity"] == 2000.0


def test_barrier_active_exhausted_hit_capacity():
    # P=2000, Barrier=20%*(1000+1000)=400, rate=50%. Non-exhausted: x = P/(1-r) = 4000; check r*x=2000 <= B=400?
    # No -> non-exhausted case invalid here, exhausted case applies: x = P + B = 2400.
    inc = _incoming(cond={"barrier_active": True}, max_life=1000.0, max_energy_shield=1000.0,
                    enemy={"kind": "attack", "damage": {"phys_hit": 100.0}})
    assert inc["pool"] == 2000.0
    assert inc["hit_capacity"] == 2400.0


def test_barrier_non_exhausted_case_when_barrier_is_large():
    # P=100 (small pool), Barrier=1000 (huge, from a big life/ES base with barrier_shield_inc), rate=50%.
    # Non-exhausted: x = P/(1-r) = 200; check r*x = 100 <= B=1000 -> valid, use x=200 (barrier never exhausts).
    inc = _incoming(cond={"barrier_active": True}, max_life=100.0, max_energy_shield=0.0,
                    barrier_shield_inc=39.0,  # 20%*100 * (1+39) = 800; want a bigger Barrier than the exhausted case
                    enemy={"kind": "attack", "damage": {"phys_hit": 100.0}})
    assert inc["pool"] == 100.0
    assert round(inc["hit_capacity"], 4) == 200.0


def test_barrier_max_hit_uses_barrier_aware_capacity():
    inc = _incoming(cond={"barrier_active": True}, max_life=1000.0, max_energy_shield=1000.0, fire_resistance=0.30,
                    enemy={"kind": "attack", "damage": {"fire_hit": 1000.0}})
    fire = inc["types"]["fire"]
    assert round(fire["max_hit"], 2) == round(2400.0 / 0.70, 2)
