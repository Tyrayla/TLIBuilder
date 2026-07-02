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

# Per the Help DB: Cast = Use (player button press) + Trigger (automatic). Only USE counts for "when you use a skill"
# mods; triggered/repeated casts (Tangle, Spell Burst, Activation Mediums) do NOT. The engine's per-event consume
# already multiplies by the active skill's BASE use rate (compute_skill_rates sps) — the Tangle/Spell-Burst inflation
# happens later in offense, so it is NOT counted here. So per-USE consume is correct (one skill at a time). Remaining
# gaps, surfaced via ConsumptionResult.flags only when relevant: PROXY use events (Seething Spirit USES skills →
# extra use events, currently uncounted) and "on cast" mana consume that should scale with the full CAST rate
# (tied to the skill-cost model).
_PROXY_USE_FLAG = ("Proxy skill uses (e.g. Seething Spirit) add use events that aren't counted yet — "
                   "per-use consume may be under-counted for proxy builds.")

# "Recently" window = 4 s (Tyra-confirmed). Single source of truth.
RECENTLY_WINDOW_S = 4.0


def floored_consumed(consumed: float, unit: float) -> float:
    """Quantize a 'consumed recently' total DOWN to a whole multiple of `unit`. "For every N consumed recently"
    procs in discrete stacks (Tyra-confirmed): a partial Nth chunk grants nothing — floor(consumed/N) stacks ×
    the per-stack benefit. unit <= 0 (no divisor known) → return consumed unchanged (continuous fallback)."""
    if unit and unit > 0:
        return int(consumed // unit) * unit
    return consumed

# Every typed consume-rate source stat (used to detect "does this build consume?" and to whitelist reads).
CONSUME_SOURCE_KEYS = [f"{p}_consumed_{b}_per_{c}"
                       for p in ("life", "mana", "energy_shield")
                       for b in ("pct_current", "pct_max", "flat")
                       for c in ("sec", "cast")]
CONSUME_SOURCE_KEYS += [f"{p}_consumed_{b}_per_attack_use"
                        for p in ("life", "mana")
                        for b in ("pct_current", "pct_max", "flat")]
# Unsullied Blade's Mystic-Mercury consume is its own (lock-bypassing) source — list it so a pure-Unsullied build
# (no other consume affix) still triggers the consumption stage.
CONSUME_SOURCE_KEYS += ["mana_consumed_pct_current_per_attack_use_mystic"]

# USE vs CAST (Tyra-flagged, FOLLOW-UP): most LIFE-consume mods say "on skill USE" while most MANA-consume mods say
# "on cast". They differ because spells are typically not "used" — they're cast/triggered by Tangle, Spell Burst, etc.
# A triggered/repeated cast counts as a CAST but not a USE. We don't yet model a separate USE rate, so the per-cast
# consume here is multiplied by the cast rate (sps) for BOTH — which OVER-counts "per use" life consume on
# triggered/repeating builds. Surfaced via ConsumptionResult.flags. Real use-vs-cast modeling is a deferred follow-up.


@dataclass
class ConsumptionResult:
    life_per_sec: float = 0.0
    mana_per_sec: float = 0.0
    energy_shield_per_sec: float = 0.0
    consumed_recently_life: float = 0.0
    consumed_recently_mana: float = 0.0
    consumed_recently_energy_shield: float = 0.0
    # Skill COST per second, summed across all active skills (cost ≠ consume — a SEPARATE drain, never added to the
    # consumption figures above; subtracted on its own in engine.recovery's net sustain).
    skill_cost_mana_per_sec: float = 0.0
    skill_cost_life_per_sec: float = 0.0
    window: float = RECENTLY_WINDOW_S
    flags: list = field(default_factory=list)    # surfaced approximations (e.g. the use-vs-cast follow-up)

    @property
    def any_consumption(self) -> bool:
        return (self.life_per_sec > 1e-9 or self.mana_per_sec > 1e-9 or self.energy_shield_per_sec > 1e-9)


def _pool_per_sec(source: BuildSource, pool: str, current: float, pool_max: float, rates: dict) -> float:
    """consumed/sec for one pool from its typed consume-rate stats. `rates` = {"any": generic use/cast rate,
    "attack": attack-skill use rate}. (Use-vs-cast precision + which-skill-rate is refined in Stage C.)"""
    def _amt(suffix):
        return (source.total(f"{pool}_consumed_pct_current_per_{suffix}") * current
                + source.total(f"{pool}_consumed_pct_max_per_{suffix}") * pool_max
                + source.total(f"{pool}_consumed_flat_per_{suffix}"))
    per_sec = _amt("sec")
    per_cast = _amt("cast") * max(0.0, rates.get("any", 0.0))            # unscoped "on skill use" → generic rate
    per_attack = _amt("attack_use") * max(0.0, rates.get("attack", 0.0))  # "Attack Skills" scope → attack-use rate
    return per_sec + per_cast + per_attack


def calculate_consumption(source: BuildSource, *, condition_state: dict | None = None,
                          defense: dict | None = None, rates: dict | None = None,
                          reservation: dict | None = None,
                          skill_cost_mana_per_sec: float = 0.0, skill_cost_life_per_sec: float = 0.0,
                          skill_cost_flags: list | None = None) -> ConsumptionResult:
    cs = condition_state or {}
    d = defense or {}
    rates = rates or {}
    rsv = reservation or {}
    max_life = float(d.get("max_life", source.total("max_life")) or 0.0)
    max_mana = float(d.get("max_mana", source.total("max_mana")) or 0.0)
    max_es = float(d.get("max_energy_shield", source.total("max_energy_shield")) or 0.0)
    # "Current Life/Mana" is the UNRESERVED pool (Max − Reserved) — % of current consume is taken against that, to
    # avoid over-counting when a build seals Life/Mana. "% of Max" bases still use raw Max (per Tyra).
    unres_life = max(0.0, max_life - float(rsv.get("sealed_life", 0.0) or 0.0))
    unres_mana = max(0.0, max_mana - float(rsv.get("sealed_mana", 0.0) or 0.0))
    life_pct = float(cs.get("current_life_pct", 100.0) or 0.0)
    mana_pct = float(cs.get("current_mana_pct", 100.0) or 0.0)
    es_pct = float(cs.get("current_es_pct", 100.0) or 0.0)

    life_ps = _pool_per_sec(source, "life", life_pct / 100.0 * unres_life, max_life, rates)
    cur_mana = mana_pct / 100.0 * unres_mana
    mana_ps = _pool_per_sec(source, "mana", cur_mana, max_mana, rates)
    # Unsullied Blade (Rosa #2) — "Mana can only be consumed by Mystic Mercury": when the lock flag is set (base
    # node active, no Utmost Devotion) every OTHER mana-consume source is blocked. Utmost Devotion clears the flag so
    # external consumers work again. The flag is emitted only by the Unsullied Blade module, so it can't affect other
    # builds.
    if source.total("mana_consume_external_blocked"):
        mana_ps = 0.0
    # Mystic Mercury's own consume BYPASSES the lock (it's the permitted consumer): 10% of unsealed Max Mana per
    # non-channeled attack use → % of current unreserved mana × the attack-use rate (exact at full mana).
    mana_ps += (source.total("mana_consumed_pct_current_per_attack_use_mystic") * cur_mana
                * max(0.0, rates.get("attack", 0.0)))
    # Energy Shield: per-sec bases only (no per-cast ES consume seen). Reuse the per-cast=0 path.
    es_ps = (source.total("energy_shield_consumed_pct_current_per_sec") * (es_pct / 100.0 * max_es)
             + source.total("energy_shield_consumed_pct_max_per_sec") * max_es
             + source.total("energy_shield_consumed_flat_per_sec"))

    # Per-USE consume uses the active skill's base USE rate (correct, one skill at a time — see note above). The only
    # surfaced caveat is PROXY use events (Seething Spirit), which add uses we don't count yet — flag when a proxy
    # use-source is present. (rates["proxy"] is reserved for when proxy use rates are modeled; 0 today.)
    flags = []
    if rates.get("proxy_present"):
        flags.append(_PROXY_USE_FLAG)

    # Skill COST is NOT consumption — cost ≠ consume (Tyra-confirmed). The per-second totals (summed across ALL
    # active skills, each at its own use rate; triggers ignore cost) are computed upstream in engine.compute and
    # passed in here only to be REPORTED + subtracted SEPARATELY in engine.recovery's net sustain. They are NEVER
    # added to mana/life_per_sec ("Mana/Life Consumed") nor to consumed_recently (per-N affixes + threshold gates).
    flags.extend(skill_cost_flags or [])

    w = RECENTLY_WINDOW_S
    return ConsumptionResult(
        life_per_sec=life_ps, mana_per_sec=mana_ps, energy_shield_per_sec=es_ps,
        consumed_recently_life=life_ps * w, consumed_recently_mana=mana_ps * w,
        consumed_recently_energy_shield=es_ps * w,
        skill_cost_mana_per_sec=max(0.0, skill_cost_mana_per_sec),
        skill_cost_life_per_sec=max(0.0, skill_cost_life_per_sec),
        window=w, flags=flags,
    )
