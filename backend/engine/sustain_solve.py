"""Steady-state pool % solver (Stage C): the life % where recovery == consumption.

A consume build never sits at full Life — it settles where net (recovery − consumption) = 0. Total recovery is
monotone-DECREASING in Life % (regain is missing-based; restoration's effective share shrinks as you fill), and
%-current consumption is monotone-INCREASING in Life %, so net_life is strictly decreasing in Life % → a UNIQUE root,
found by bisection (cannot oscillate or diverge). No timeline needed — this is the analytic equilibrium.

Edge cases:
- recovery beats consumption even at full Life  → stays at 100 % (no deficit).
- consumption beats recovery even near-empty    → death spiral → clamp to 0 % (unsustainable; recovery's verdict
  surfaces time-to-empty).
"""
from __future__ import annotations

from engine.recovery import calculate_recovery
from engine.consumption import calculate_consumption

LIFE_PCT_QUANTUM = 0.5   # resolution + the snapshot-quantization granularity (keeps the fixed-point loop terminating)


# pool → (the condition_state % key it solves, the RecoveryResult net field to drive to zero).
_POOL_SPEC = {
    "life":          ("current_life_pct", "net_life_per_sec"),
    "mana":          ("current_mana_pct", "net_mana_per_sec"),
    "energy_shield": ("current_es_pct",   "net_es_per_sec"),
}


def _net_at(source, condition_state, pool, pct, restoration_inputs, rates, reservation, uptime_mode,
            skill_cost_mana_per_sec=0.0, skill_cost_life_per_sec=0.0) -> float:
    pct_key, net_field = _POOL_SPEC[pool]
    cs = dict(condition_state)
    cs[pct_key] = pct
    cons = calculate_consumption(source, condition_state=cs, rates=rates, reservation=reservation,
                                 skill_cost_mana_per_sec=skill_cost_mana_per_sec,
                                 skill_cost_life_per_sec=skill_cost_life_per_sec)
    rec = calculate_recovery(
        source, condition_state=cs, restoration_inputs=restoration_inputs, reservation=reservation,
        consumption={"life_per_sec": cons.life_per_sec, "mana_per_sec": cons.mana_per_sec,
                     "energy_shield_per_sec": cons.energy_shield_per_sec,
                     "skill_cost_mana_per_sec": cons.skill_cost_mana_per_sec,
                     "skill_cost_life_per_sec": cons.skill_cost_life_per_sec},
        uptime_mode=uptime_mode)
    return getattr(rec, net_field)


def solve_steady_pool_pct(source, condition_state, pool, restoration_inputs, rates, reservation=None,
                          uptime_mode=None, skill_cost_mana_per_sec=0.0, skill_cost_life_per_sec=0.0) -> float:
    """Bisect the `pool` % where its net = 0; quantized to LIFE_PCT_QUANTUM in [0, 100]. `pool` ∈
    {'life','mana','energy_shield'}. Net is monotone-decreasing in the pool % (recovery falls — missing-based
    regain/restoration share shrink as the pool fills; %-current consumption rises), so there is a unique root,
    found by bisection (cannot oscillate). uptime_mode is threaded so the equilibrium uses the SAME restoration
    cadence the display reads (else the solved % and the displayed net disagree in Effective mode)."""
    f = lambda pct: _net_at(source, condition_state, pool, pct, restoration_inputs, rates, reservation, uptime_mode,
                            skill_cost_mana_per_sec=skill_cost_mana_per_sec,
                            skill_cost_life_per_sec=skill_cost_life_per_sec)
    if f(100.0) >= 0.0:
        return 100.0   # recovery beats consumption even at full → stays full
    if f(0.0) <= 0.0:
        return 0.0     # consumption beats recovery even near-empty → death spiral
    lo, hi = 0.0, 100.0   # f(lo) > 0 (recovering), f(hi) < 0 (draining)
    for _ in range(9):    # 100 / 2^9 ≈ 0.2 % precision
        mid = 0.5 * (lo + hi)
        if f(mid) >= 0.0:
            lo = mid
        else:
            hi = mid
    return round((0.5 * (lo + hi)) / LIFE_PCT_QUANTUM) * LIFE_PCT_QUANTUM
