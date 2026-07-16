"""Unit coverage for engine.sustain_solve.solve_steady_pool_pct — the bisection solver itself (Stage C: the
Life/Mana/ES % where recovery == consumption).

This is a pure numerical unit: rather than assembling a full BuildSource/gear/skill payload to coax specific
recovery/consumption curves out of the real engine (which would make the branch being tested — the bisection
logic — incidental to a much bigger setup), we monkeypatch the two functions solve_steady_pool_pct calls
(engine.recovery.calculate_recovery, engine.consumption.calculate_consumption, both imported at module scope
into engine.sustain_solve) with tiny stand-ins that report a fully controlled net = f(pct) curve. This lets
each branch (the two short-circuits, the bisection search, and the quantization) be hit directly and exactly,
per the assignment's own instruction to "stub/choose inputs to hit each branch."
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import engine.sustain_solve as sustain_solve
from engine.sustain_solve import LIFE_PCT_QUANTUM, solve_steady_pool_pct


def _install_fake_net(monkeypatch, net_fn):
    """Wire solve_steady_pool_pct's two collaborators so `net_life_per_sec` at any pool % is `net_fn(pct)`.
    Signatures mirror the exact keyword shapes _net_at calls them with."""

    def fake_consumption(source, *, condition_state, rates, reservation,
                          skill_cost_mana_per_sec=0.0, skill_cost_life_per_sec=0.0):
        return SimpleNamespace(
            life_per_sec=0.0, mana_per_sec=0.0, energy_shield_per_sec=0.0,
            skill_cost_mana_per_sec=skill_cost_mana_per_sec, skill_cost_life_per_sec=skill_cost_life_per_sec,
        )

    def fake_recovery(source, *, condition_state, restoration_inputs, reservation, consumption, uptime_mode):
        pct = condition_state["current_life_pct"]
        return SimpleNamespace(net_life_per_sec=net_fn(pct), net_mana_per_sec=0.0, net_es_per_sec=0.0)

    monkeypatch.setattr(sustain_solve, "calculate_consumption", fake_consumption)
    monkeypatch.setattr(sustain_solve, "calculate_recovery", fake_recovery)


def _solve(net_fn, monkeypatch) -> float:
    _install_fake_net(monkeypatch, net_fn)
    return solve_steady_pool_pct(source=None, condition_state={}, pool="life",
                                 restoration_inputs=None, rates=None)


class TestSolveSteadyPoolPct:
    def test_recovery_beats_consumption_even_at_full_short_circuits_100(self, monkeypatch):
        # f(100) >= 0 for a constant-positive net curve -> short-circuits without ever bisecting.
        result = _solve(lambda pct: 5.0, monkeypatch)
        assert result == 100.0

    def test_consumption_beats_recovery_even_near_empty_short_circuits_0(self, monkeypatch):
        # f(0) <= 0 for a constant-negative net curve -> death spiral, clamps to 0.
        result = _solve(lambda pct: -5.0, monkeypatch)
        assert result == 0.0

    def test_mid_range_bisection_finds_the_root(self, monkeypatch):
        # net crosses zero at pct=60 (f(100) < 0, f(0) > 0) -> unique root found by bisection.
        result = _solve(lambda pct: 60.0 - pct, monkeypatch)
        assert result == pytest.approx(60.0, abs=LIFE_PCT_QUANTUM)

    def test_life_pct_quantum_rounds_the_bisected_result(self, monkeypatch):
        # True root (41.2) is NOT a quantum multiple -> the returned value must be snapped to the nearest
        # LIFE_PCT_QUANTUM (0.5) grid point, i.e. round(41.2 / 0.5) * 0.5 == 41.0.
        result = _solve(lambda pct: 41.2 - pct, monkeypatch)
        expected = round(41.2 / LIFE_PCT_QUANTUM) * LIFE_PCT_QUANTUM
        assert result == pytest.approx(expected, abs=1e-9)
        # and it really is an exact multiple of the quantum (not just numerically close)
        assert (result / LIFE_PCT_QUANTUM) == pytest.approx(round(result / LIFE_PCT_QUANTUM), abs=1e-9)

    def test_boundary_is_exclusive_short_circuit_not_bisection(self, monkeypatch):
        # f(100) == 0 exactly still takes the >= 0 short-circuit (not the bisection path).
        result = _solve(lambda pct: 100.0 - pct if pct >= 100 else 1.0, monkeypatch)
        assert result == 100.0
