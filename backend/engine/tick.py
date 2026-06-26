"""Server tickrate model — TLI processes actions on a fixed 30 Hz clock.

Owner-confirmed: the server clock is **30 ticks/second** (the occasionally-cited 30.97/31
figure is a single flimsy datamined source and is dropped — see docs). Everything the server
schedules is bound by this one clock, including damage-over-time.

Two regimes share the clock:

1. **Smooth + hard cap** — the DEFAULT for player-controlled rates (cast/attack speed). A rate
   carries fractional progress between ticks, so it scales *smoothly*; it just can never exceed
   one action per tick → a hard ceiling of 30/s. Use ``cap_rate``. The cap is **per caster**:
   Tangle's N casters and Spell Burst's instant recasts multiply the capped single-caster rate,
   so the aggregate can exceed 30/s.

2. **Hard-rounded breakpoints** — an EXPLICIT, per-mechanism opt-in (NEVER automatic; the owner
   approves each one). Server-timed countdowns measured in *whole* ticks: the period rounds UP to
   an integer number of ticks, so the effective rate only changes when a speed increase crosses an
   integer-tick boundary (flat "dead zones" in between). Use ``period_ticks`` + ``rate_from_ticks``.
   Rule of thumb for what qualifies: server-calculated / not-directly-player-controlled timings
   (charge clocks, triggers, minions). Spell Burst charge is the first opted-in user (see offense).
   Other confirmed cases reuse these helpers later (minions, Reap, Wind Rhythm, Split Shot Rapid
   Advance) — filed in docs/BACKLOG.md, each manually opted-in.
"""

import math

TICK_RATE = 30  # Hz — server clock; owner-confirmed hard cap (not 31).


def cap_rate(raw: float, tickrate: int = TICK_RATE) -> float:
    """Smooth rate clamped to at most one action per tick (per caster)."""
    if raw <= 0.0:
        return 0.0
    return min(raw, float(tickrate))


def period_ticks(seconds: float, tickrate: int = TICK_RATE) -> int:
    """Whole-tick period of a server-timed countdown: ceil(seconds × tickrate), min 1 tick.

    Hard-rounded breakpoint regime ONLY (opt-in per mechanism). A countdown can't resolve mid-tick,
    so its period is the next whole tick — hence the breakpoint dead zones.
    """
    if seconds <= 0.0:
        return 1
    return max(1, math.ceil(seconds * tickrate))


def rate_from_ticks(ticks: int, tickrate: int = TICK_RATE) -> float:
    """Per-second rate of a mechanism whose period is ``ticks`` whole server ticks."""
    return tickrate / max(1, int(ticks))
