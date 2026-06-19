"""
Shared uptime / ramp primitives.

Pure math — no engine coupling, fully unit-testable. These convert a (rate, duration, cooldown, cap)
description of a refreshing buff/debuff into its steady-state stack count or uptime fraction. They are the
single home for rate→uptime math so the many consumers (Numbed via Feline Figure, blessings-on-hit,
Squidnova, Berserking Blade ramp, Nourishment, …) reuse one implementation instead of re-deriving it.

Mode model: every mechanic chooses MAX or REAL. MAX = the legacy assume-max behaviour (full stacks /
100% uptime). REAL = compute the steady state from the build's actual rates. A mechanic that has no REAL
implementation must keep returning its MAX value regardless of the selected mode (the caller's contract),
so flipping the global mode to REAL can never break an unmigrated mechanic.
"""
from __future__ import annotations

from enum import Enum


class UptimeMode(str, Enum):
    MAX = "max"
    REAL = "real"


def parse_mode(value) -> UptimeMode:
    """Coerce an arbitrary stored value (str / enum / None) to a UptimeMode, defaulting to MAX."""
    if isinstance(value, UptimeMode):
        return value
    if isinstance(value, str) and value.lower() == UptimeMode.REAL.value:
        return UptimeMode.REAL
    return UptimeMode.MAX


def is_real(value) -> bool:
    return parse_mode(value) is UptimeMode.REAL


def _capped_rate(apply_rate: float, cooldown: float | None) -> float:
    """The effective application/trigger rate per second, floored at 0 and capped at 1/cooldown."""
    rate = max(0.0, float(apply_rate))
    if cooldown and cooldown > 0:
        rate = min(rate, 1.0 / cooldown)
    return rate


def effective_stacks(
    apply_rate: float,
    duration: float,
    cap: float,
    *,
    per_apply: float = 1.0,
    cooldown: float | None = None,
) -> float:
    """Steady-state stack count for a stacking buff/debuff.

    Each application adds ``per_apply`` stacks that each last ``duration`` seconds; applications occur at
    ``apply_rate`` per second (a trigger rate). At steady state ``rate × per_apply × duration`` stacks are
    simultaneously active, clamped to ``[0, cap]``.

    ``cooldown`` (seconds) caps the *trigger* rate at ``1/cooldown`` — e.g. Feline Figure's ≤1/s/enemy
    re-trigger. It gates the trigger rate, NOT the total gain, so a trigger that applies many stacks
    (``per_apply > 1``) still delivers them all per (cooldown-limited) trigger.
    """
    rate = _capped_rate(apply_rate, cooldown)
    stacks = rate * max(0.0, float(per_apply)) * max(0.0, float(duration))
    return max(0.0, min(stacks, float(cap)))


def uptime_fraction(
    proc_per_sec: float,
    duration: float,
    *,
    cooldown: float | None = None,
) -> float:
    """Fraction of time a binary (on/off) buff is active, clamped to ``[0, 1]``.

    Modelled as ``min(1, rate × duration)`` (a refreshing buff at ``rate`` procs/sec each lasting
    ``duration``). ``cooldown`` caps the proc rate at ``1/cooldown``.
    """
    rate = _capped_rate(proc_per_sec, cooldown)
    return max(0.0, min(1.0, rate * max(0.0, float(duration))))
