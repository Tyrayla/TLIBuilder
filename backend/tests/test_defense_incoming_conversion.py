"""
Tests for the incoming damage-taken-as conversion (`{src}_taken_as_{dst}_inc`, defense.py::_taken_as_fracs +
_incoming_taken_fraction_converted) — WS3 hardening. Conversion happens BEFORE type-specific armour/resistance/
damage-taken mitigation: an unconverted remainder keeps the source type's own mitigation, each converted slice
picks up its landing type's.

Source (needs-verification): TLI Help Database wording "Converts N% of <A> Damage taken to <B> Damage"; the cap/
redistribution rule when a single source's conversions exceed 100% is modeled after the outgoing-conversion cap
(offense.py::_conversion_fracs) — no in-game statement of the incoming-specific rule exists yet.
"""
from engine.models import BuildSource
from engine.defense import calculate_defense, calculate_incoming


def _incoming(cond=None, enemy=None, **stats) -> dict:
    s = BuildSource()
    for k, v in stats.items():
        s.add(k, v)
    if cond:
        s.condition_state = dict(cond)
    if enemy is not None:
        s.enemy_config = enemy
    return calculate_incoming(s, calculate_defense(s))


def test_full_physical_taken_as_fire():
    # 100% Physical Damage Taken as Fire: a physical hit is mitigated entirely as fire (fire resistance
    # applies, physical has none) — proves conversion precedes type-specific mitigation.
    inc = _incoming(physical_taken_as_fire_inc=1.0, fire_resistance=0.30,
                    enemy={"kind": "attack", "damage": {"phys_hit": 1000.0}})
    phys = inc["types"]["physical"]
    assert round(phys["mitigated_hit"], 2) == 700.0        # 1000 x (1 - 0.30 fire resist), no armour/phys-resist
    assert round(phys["hit_taken_fraction"], 4) == 0.70


def test_partial_physical_taken_as_fire_with_remainder():
    # 40% converted to fire (30% fire resist), 60% stays physical (no resist, no armour here) — weighted sum.
    inc = _incoming(physical_taken_as_fire_inc=0.40, fire_resistance=0.30,
                    enemy={"kind": "attack", "damage": {"phys_hit": 1000.0}})
    phys = inc["types"]["physical"]
    expected_frac = 0.60 * 1.0 + 0.40 * 0.70
    assert round(phys["hit_taken_fraction"], 4) == round(expected_frac, 4)
    assert round(phys["mitigated_hit"], 2) == round(1000.0 * expected_frac, 2)


def test_split_conversion_across_multiple_final_types():
    # 30% Physical Damage Taken as Fire + 20% Physical Damage Taken as Cold, 50% stays physical.
    inc = _incoming(physical_taken_as_fire_inc=0.30, physical_taken_as_cold_inc=0.20,
                    fire_resistance=0.30, cold_resistance=0.50,
                    enemy={"kind": "attack", "damage": {"phys_hit": 1000.0}})
    phys = inc["types"]["physical"]
    expected_frac = 0.50 * 1.0 + 0.30 * 0.70 + 0.20 * 0.50
    assert round(phys["hit_taken_fraction"], 4) == round(expected_frac, 4)


def test_conversion_changes_resistance_used():
    # Erosion has its own resistance; converting it to lightning switches which resistance pool applies.
    inc_no_conv = _incoming(erosion_resistance=0.10, lightning_resistance=0.50,
                            enemy={"kind": "attack", "damage": {"erosion_hit": 1000.0}})
    inc_conv = _incoming(erosion_taken_as_lightning_inc=1.0, erosion_resistance=0.10, lightning_resistance=0.50,
                         enemy={"kind": "attack", "damage": {"erosion_hit": 1000.0}})
    assert round(inc_no_conv["types"]["erosion"]["mitigated_hit"], 2) == 900.0    # 1000 x (1 - 0.10 erosion)
    assert round(inc_conv["types"]["erosion"]["mitigated_hit"], 2) == 500.0       # 1000 x (1 - 0.50 lightning)


def test_conversion_changes_hit_armour_behavior():
    # Physical uses the full armour rate; fire uses the reduced non-physical rate (60% by default) — converting
    # 100% of a physical hit to fire should mitigate LESS from armour than staying physical, all else equal.
    inc_stay = _incoming(armor=50000.0,
                         enemy={"kind": "attack", "damage": {"phys_hit": 1000.0}})
    inc_conv = _incoming(physical_taken_as_fire_inc=1.0, armor=50000.0,
                         enemy={"kind": "attack", "damage": {"phys_hit": 1000.0}})
    assert inc_conv["types"]["physical"]["mitigated_hit"] > inc_stay["types"]["physical"]["mitigated_hit"]


def test_dot_conversion_uses_same_fracs_as_hit():
    # DoT rows: conversion applies, but the LANDING type's mitigation is resistance-only (DoT skips armour).
    inc = _incoming(physical_taken_as_fire_inc=1.0, fire_resistance=0.30, armor=50000.0,
                    enemy={"kind": "attack", "damage": {"phys_dot": 1000.0}})
    phys = inc["types"]["physical"]
    assert round(phys["mitigated_dot"], 2) == 700.0     # 1000 x (1 - 0.30 fire resist), no armour despite it being set
    assert round(phys["dot_taken_fraction"], 4) == 0.70


def test_conversion_over_100pct_is_capped_and_redistributed():
    # 70% + 50% = 120% from one source -> capped to 100%, redistributed by weight (7:5).
    inc = _incoming(physical_taken_as_fire_inc=0.70, physical_taken_as_cold_inc=0.50,
                    fire_resistance=0.0, cold_resistance=0.0,
                    enemy={"kind": "attack", "damage": {"phys_hit": 1000.0}})
    phys = inc["types"]["physical"]
    # No resistance on either landing type and no armour set -> mitigated == incoming regardless of the split,
    # but the taken fraction must still be 1.0 (fully converted, nothing left unconverted/uncapped-away).
    assert round(phys["hit_taken_fraction"], 4) == 1.0


# ── DoT effective pool / time-to-death (raw-DPS terms) ────────────────────────────

def test_dot_metrics_present_and_finite():
    inc = _incoming(max_life=1000.0, fire_resistance=0.30,
                    enemy={"kind": "attack", "damage": {"fire_dot": 100.0}})
    fire = inc["types"]["fire"]
    assert round(fire["mitigated_dot"], 2) == 70.0
    assert round(fire["dot_effective_pool"], 2) == round(1000.0 / 0.70, 2)
    assert round(fire["dot_time_to_death"], 2) == round(1000.0 / 70.0, 2)


def test_dot_time_to_death_none_when_no_incoming_dot():
    # dot_effective_pool is a pool-capacity figure (usable pool ÷ taken fraction) independent of the CURRENT
    # incoming value, so it stays finite at 0 incoming DoT; time-to-death (which divides BY the incoming-derived
    # mitigated DPS) is the one that must render N/A rather than a misleading infinity.
    inc = _incoming(max_life=1000.0, enemy={"kind": "attack", "damage": {"fire_dot": 0.0}})
    fire = inc["types"]["fire"]
    assert fire["dot_time_to_death"] is None


def test_dot_metrics_none_on_full_dot_immunity():
    inc = _incoming(max_life=1000.0, dmg_taken_additional=-1.0,
                    enemy={"kind": "attack", "damage": {"fire_dot": 500.0}})
    fire = inc["types"]["fire"]
    assert fire["dot_taken_fraction"] == 0.0
    assert fire["mitigated_dot"] == 0.0
    assert fire["dot_effective_pool"] is None
    assert fire["dot_time_to_death"] is None


def test_barrier_excluded_from_dot_pool():
    # Barrier active with a large shield must not change the DoT pool/effective-pool figures (Life+ES only).
    base = _incoming(max_life=1000.0, fire_resistance=0.0,
                     enemy={"kind": "attack", "damage": {"fire_dot": 100.0}})
    withb = _incoming(cond={"barrier_active": True}, max_life=1000.0, fire_resistance=0.0,
                      enemy={"kind": "attack", "damage": {"fire_dot": 100.0}})
    assert base["pool"] == withb["pool"] == 1000.0
    assert base["types"]["fire"]["dot_effective_pool"] == withb["types"]["fire"]["dot_effective_pool"]
