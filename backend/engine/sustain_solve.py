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


def _net_life_at(source, condition_state, life_pct, restoration_inputs, casts_per_sec) -> float:
    cs = dict(condition_state)
    cs["current_life_pct"] = life_pct
    cons = calculate_consumption(source, condition_state=cs, casts_per_sec=casts_per_sec)
    rec = calculate_recovery(source, condition_state=cs, restoration_inputs=restoration_inputs,
                             consumption={"life_per_sec": cons.life_per_sec})
    return rec.net_life_per_sec


def solve_steady_life_pct(source, condition_state, restoration_inputs, casts_per_sec) -> float:
    """Bisect the Life % where net_life = 0; quantized to LIFE_PCT_QUANTUM in [0, 100]."""
    if _net_life_at(source, condition_state, 100.0, restoration_inputs, casts_per_sec) >= 0.0:
        return 100.0
    if _net_life_at(source, condition_state, 0.0, restoration_inputs, casts_per_sec) <= 0.0:
        return 0.0
    lo, hi = 0.0, 100.0   # f(lo) > 0 (recovering), f(hi) < 0 (draining)
    for _ in range(9):    # 100 / 2^9 ≈ 0.2 % precision
        mid = 0.5 * (lo + hi)
        if _net_life_at(source, condition_state, mid, restoration_inputs, casts_per_sec) >= 0.0:
            lo = mid
        else:
            hi = mid
    mid = 0.5 * (lo + hi)
    return round(mid / LIFE_PCT_QUANTUM) * LIFE_PCT_QUANTUM
