"""Self-consume drains (Mana Boil, life-consume affixes) → life/mana/ES consumed per second + the rolling
"consumed recently" totals that drive per-N-consumed affixes and threshold gates.

Stage B of the consumption subsystem (see docs/we-re-going-to-work-quiet-glade.md). A POST-LOOP reader, like
engine.recovery: it converts the typed consume-rate stats into a drain rate per pool, using the assumed/solved
current pool % for %-current bases and the main skill's casts/sec for per-cast bases. NOT the skill's intrinsic
mana cost (Arcane / Frozen Lotus) — these are self-consume affixes only.

Model:
- per second = pct_current × current_pool + pct_max × max_pool + flat
- per cast   = (pct_current × current_pool + pct_max × max_pool + flat) × casts_per_sec
- consumed_recently = consumed_per_sec × RECENTLY_WINDOW (rolling sum; the mean rate × window is accurate even
  when the pool sawtooths, because "recently" integrates over many cycles).
Gated affixes (while Fervor / at Full Life) are handled upstream by the normal condition-gating of their
contribution, so a disabled gate simply means the stat total is 0 here.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from engine.models import BuildSource

_USE_VS_CAST_FLAG = ("Per-use consume is approximated by the cast rate (aps); triggered/repeated casts "
                     "(Tangle, Spell Burst) over-count it — use-vs-cast modeling is a follow-up.")

# "Recently" window = 4 s (owner-confirmed). Single source of truth.
RECENTLY_WINDOW_S = 4.0

# USE vs CAST (owner-flagged, FOLLOW-UP): most LIFE-consume mods say "on skill USE" while most MANA-consume mods say
# "on cast". They differ because spells are typically not "used" — they're cast/triggered by Tangle, Spell Burst, etc.
# A triggered/repeated cast counts as a CAST but not a USE. We don't yet model a separate USE rate, so the per-cast
# consume here is multiplied by the cast rate (aps) for BOTH — which OVER-counts "per use" life consume on
# triggered/repeating builds. Surfaced via ConsumptionResult.flags. Real use-vs-cast modeling is a deferred follow-up.


@dataclass
class ConsumptionResult:
    life_per_sec: float = 0.0
    mana_per_sec: float = 0.0
    energy_shield_per_sec: float = 0.0
    consumed_recently_life: float = 0.0
    consumed_recently_mana: float = 0.0
    consumed_recently_energy_shield: float = 0.0
    window: float = RECENTLY_WINDOW_S
    flags: list = field(default_factory=list)    # surfaced approximations (e.g. the use-vs-cast follow-up)

    @property
    def any_consumption(self) -> bool:
        return (self.life_per_sec > 1e-9 or self.mana_per_sec > 1e-9 or self.energy_shield_per_sec > 1e-9)


def _pool_per_sec(source: BuildSource, pool: str, current: float, pool_max: float, casts_per_sec: float) -> float:
    """consumed/sec for one pool from its typed consume-rate stats."""
    per_sec = (source.total(f"{pool}_consumed_pct_current_per_sec") * current
               + source.total(f"{pool}_consumed_pct_max_per_sec") * pool_max
               + source.total(f"{pool}_consumed_flat_per_sec"))
    per_cast = (source.total(f"{pool}_consumed_pct_current_per_cast") * current
                + source.total(f"{pool}_consumed_pct_max_per_cast") * pool_max
                + source.total(f"{pool}_consumed_flat_per_cast"))
    return per_sec + per_cast * max(0.0, casts_per_sec)


def calculate_consumption(source: BuildSource, *, condition_state: dict | None = None,
                          defense: dict | None = None, casts_per_sec: float = 0.0) -> ConsumptionResult:
    cs = condition_state or {}
    d = defense or {}
    max_life = float(d.get("max_life", source.total("max_life")) or 0.0)
    max_mana = float(d.get("max_mana", source.total("max_mana")) or 0.0)
    max_es = float(d.get("max_energy_shield", source.total("max_energy_shield")) or 0.0)
    life_pct = float(cs.get("current_life_pct", 100.0) or 0.0)
    mana_pct = float(cs.get("current_mana_pct", 100.0) or 0.0)
    es_pct = float(cs.get("current_es_pct", 100.0) or 0.0)

    life_ps = _pool_per_sec(source, "life", life_pct / 100.0 * max_life, max_life, casts_per_sec)
    mana_ps = _pool_per_sec(source, "mana", mana_pct / 100.0 * max_mana, max_mana, casts_per_sec)
    # Energy Shield: per-sec bases only (no per-cast ES consume seen). Reuse the per-cast=0 path.
    es_ps = (source.total("energy_shield_consumed_pct_current_per_sec") * (es_pct / 100.0 * max_es)
             + source.total("energy_shield_consumed_pct_max_per_sec") * max_es
             + source.total("energy_shield_consumed_flat_per_sec"))

    # Flag the use-vs-cast approximation whenever any per-cast/use consume contributes (so triggered builds know the
    # per-use life consume may be over-counted).
    flags = []
    if casts_per_sec > 0 and any(source.total(f"{p}_consumed_{b}_per_cast")
                                 for p in ("life", "mana") for b in ("pct_current", "pct_max", "flat")):
        flags.append(_USE_VS_CAST_FLAG)

    w = RECENTLY_WINDOW_S
    return ConsumptionResult(
        life_per_sec=life_ps, mana_per_sec=mana_ps, energy_shield_per_sec=es_ps,
        consumed_recently_life=life_ps * w, consumed_recently_mana=mana_ps * w,
        consumed_recently_energy_shield=es_ps * w, window=w, flags=flags,
    )
