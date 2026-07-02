"""
Tests: shared uptime primitives (engine/uptime.py) — pure (rate, duration, cooldown, cap)→steady-state
math used by the real-uptime mechanics (Numbed via Feline Figure first).
"""
import pytest
from engine import uptime


def test_effective_stacks_basic():
    # 1 application/sec, each lasts 2s → 2 stacks at steady state.
    assert uptime.effective_stacks(1.0, 2.0, cap=10) == pytest.approx(2.0)


def test_effective_stacks_cap_clamps():
    # 5/sec × 4s = 20, clamped to cap 10.
    assert uptime.effective_stacks(5.0, 4.0, cap=10) == pytest.approx(10.0)


def test_effective_stacks_per_apply():
    # FF-style: 3 stacks per trigger, 1 trigger/sec, 2s duration → 6.
    assert uptime.effective_stacks(1.0, 2.0, cap=10, per_apply=3.0) == pytest.approx(6.0)


def test_effective_stacks_cooldown_caps_trigger_rate_not_total():
    # sps 5 but 1s cooldown → ≤1 trigger/sec; 3 per trigger × 2s = 6 (NOT min(15,1)=1).
    got = uptime.effective_stacks(5.0, 2.0, cap=10, per_apply=3.0, cooldown=1.0)
    assert got == pytest.approx(6.0)


def test_effective_stacks_cooldown_only_caps_when_faster():
    # sps 0.5 < 1/cooldown(1.0) → trigger rate stays 0.5; 0.5 × 1 × 2 = 1.0.
    assert uptime.effective_stacks(0.5, 2.0, cap=10, cooldown=1.0) == pytest.approx(1.0)


def test_effective_stacks_floors_at_zero():
    assert uptime.effective_stacks(-3.0, 2.0, cap=10) == 0.0
    assert uptime.effective_stacks(1.0, -2.0, cap=10) == 0.0


def test_uptime_fraction_clamped():
    assert uptime.uptime_fraction(1.0, 0.5) == pytest.approx(0.5)
    assert uptime.uptime_fraction(10.0, 5.0) == 1.0          # clamped to 1
    assert uptime.uptime_fraction(0.0, 5.0) == 0.0


def test_uptime_fraction_cooldown():
    # 10 procs/sec but 1s cooldown → 1/sec; ×0.3s = 0.3.
    assert uptime.uptime_fraction(10.0, 0.3, cooldown=1.0) == pytest.approx(0.3)


def test_mode_parsing():
    assert uptime.parse_mode("real") is uptime.UptimeMode.REAL
    assert uptime.parse_mode("REAL") is uptime.UptimeMode.REAL
    assert uptime.parse_mode("max") is uptime.UptimeMode.MAX
    assert uptime.parse_mode(None) is uptime.UptimeMode.MAX
    assert uptime.parse_mode("nonsense") is uptime.UptimeMode.MAX
    assert uptime.is_real("real") is True
    assert uptime.is_real("max") is False
