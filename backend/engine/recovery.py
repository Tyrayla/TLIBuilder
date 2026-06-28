"""Recovery / sustain (Restoration, Regain, Regen, Temporary pools, EHP).

Mirrors engine.defense: a POST-LOOP reader of converged `source` totals (recovery is a derived display output; it
doesn't feed derive_stats). The Temporary Life/Mana pools + excess restoration are computed IN-LOOP and stashed
(see compute.py / engine.recovery.temporary_pools) because Elixir of Immortality's damage reads them; this module
re-reads the converged values for the display result.

Model (Help DB + owner-confirmed quirks):
- Restoration total per cast is FIXED: `base × (1 + Σ restoration_effect_inc) × Π(1 + restoration_effect_additional)`
  (Bonus = increased / Additional Bonus = additional). For elixir tonics the input `total` is ALSO already
  × Elixir Effect (applied upstream in apply_elixir_buffs).
- Recovery/second = total ÷ max(restoration_duration, recast_interval) — shortening duration concentrates,
  lengthening spreads, and recasting refreshes (discards the tail), so going below the recast cadence only gaps.
- Restoration duration = base window × (1 + Σ restoration_duration_inc) × Π(1 + additional); for tonics the input
  `window` is already × Elixir Duration (which carries skill-effect duration).
- Regain = on-hit recovery of MISSING Life/Shield, 0.5 s base interval, 30% cap each.
- Effective vs Excess is a planner input, NOT a combat sim: at the assumed Current Life % (current_life_pct,
  default 100) restoration fills the deficit first (effective); at full Life it's all excess (→ Temporary Life / ES).
- Temporary Life/Mana is a SEPARATE used-first barrier (NOT folded into max_life): total_max_life = max_life + temp.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from engine.models import BuildSource
from engine.offense import additional_total_product

_REGAIN_BASE_INTERVAL = 0.5      # s (Help DB)
_REGAIN_CAP = 0.30               # 30% of missing per tick (Life Regain / Shield Regain)


def _restoration_effect_factor(source: BuildSource) -> float:
    return (1.0 + source.total("restoration_effect_inc")) * additional_total_product(source, "restoration_effect_additional")


def _restoration_duration_factor(source: BuildSource) -> float:
    return (1.0 + source.total("restoration_duration_inc")) * additional_total_product(source, "restoration_duration_additional")


@dataclass
class RecoveryResult:
    # Restoration (heal-over-time), split by pool
    restoration_life_per_sec: float = 0.0
    restoration_mana_per_sec: float = 0.0
    restoration_life_total: float = 0.0          # total restored per cast (all sources summed)
    restoration_mana_total: float = 0.0
    excess_life_restoration: float = 0.0         # excess (overflow) restoration amount → Temporary Life / ES
    excess_mana_restoration: float = 0.0
    restoration_sources: list = field(default_factory=list)   # [{pool, source, total, duration, per_sec}]
    # Regain (on-hit, missing-based) — per second at the assumed Current Life/ES %
    life_regain_per_sec: float = 0.0
    shield_regain_per_sec: float = 0.0
    # Regen (over time)
    life_regen_per_sec: float = 0.0
    mana_regen_per_sec: float = 0.0
    # Temporary pools (separate used-first barrier) + totals
    temporary_life: float = 0.0
    temporary_mana: float = 0.0
    total_max_life: float = 0.0                  # Base Max Life + Temporary Life (display / EHP barrier)
    total_max_mana: float = 0.0
    # Net sustain (recovery − consumption); consumption from skill life-cost is NYI (reservation only for now)
    net_life_per_sec: float = 0.0
    net_mana_per_sec: float = 0.0
    # Effective HP (Life + Temporary Life vs the calc target's average mitigation)
    ehp_life: float = 0.0
    nyi: list = field(default_factory=lambda: ["Net sustain excludes skill Life cost (no skill-cost model yet)"])


def _pool_recovery(inputs, pool, pool_max, restoration_factor, duration_factor, missing, at_full):
    """(total, per_sec, excess, sources[]) for one pool ('life'|'mana') from the restoration inputs. Each input is
    {pool, mode: pct|flat, base_amount (× Elixir Effect), window (× Elixir Duration), recast, source}; pct resolves
    against the pool's max, then × Restoration Effect; per-sec = total ÷ max(duration, recast)."""
    total = 0.0
    per_sec = 0.0
    sources = []
    for r in inputs or []:
        if r.get("pool") != pool:
            continue
        amount = float(r.get("base_amount", 0.0)) * (pool_max if r.get("mode") == "pct" else 1.0)
        t = amount * restoration_factor
        dur = max(float(r.get("window", 0.0)) * duration_factor, 1e-9)
        recast = float(r.get("recast", 0.0) or 0.0)
        ps = t / max(dur, recast) if max(dur, recast) > 0 else 0.0
        total += t
        per_sec += ps
        sources.append({"pool": pool, "source": r.get("source", ""), "total": t, "duration": dur, "per_sec": ps})
    # Excess (overflow → Temporary pools / ES): at full Life/Mana ALL restoration is excess; below full it refills
    # the assumed deficit first (effective) — a planner-input convention, not a combat sim.
    excess = total if at_full else max(0.0, total - missing)
    return total, per_sec, excess, sources


def calculate_recovery(source: BuildSource, *, condition_state: dict | None = None,
                       restoration_inputs: list | None = None, reservation: dict | None = None,
                       defense: dict | None = None) -> RecoveryResult:
    cs = condition_state or {}
    d = defense or {}
    max_life = source.total("max_life")
    max_mana = source.total("max_mana")
    life_pct = float(cs.get("current_life_pct", 100.0) or 0.0)
    mana_pct = float(cs.get("current_mana_pct", 100.0) or 0.0)
    es_pct = float(cs.get("current_es_pct", 100.0) or 0.0)
    missing_life = max(0.0, (1.0 - life_pct / 100.0) * max_life)
    missing_mana = max(0.0, (1.0 - mana_pct / 100.0) * max_mana)
    missing_es = max(0.0, (1.0 - es_pct / 100.0) * source.total("max_energy_shield"))

    r_factor = _restoration_effect_factor(source)
    dur_factor = _restoration_duration_factor(source)

    life_total, life_ps, life_excess, life_src = _pool_recovery(
        restoration_inputs, "life", max_life, r_factor, dur_factor, missing_life, life_pct >= 100.0)
    mana_total, mana_ps, mana_excess, mana_src = _pool_recovery(
        restoration_inputs, "mana", max_mana, r_factor, dur_factor, missing_mana, mana_pct >= 100.0)

    # Regain (on-hit, missing-based): per-tick = min(missing × Σregain_inc, 30% of missing); per-sec / interval.
    life_regain_interval = _REGAIN_BASE_INTERVAL * (1.0 + source.total("regain_interval_additional")
                                                    + source.total("life_regain_interval_additional"))
    es_regain_interval = _REGAIN_BASE_INTERVAL * (1.0 + source.total("regain_interval_additional")
                                                  + source.total("energy_shield_regain_interval_additional"))
    life_regain_tick = min(missing_life * source.total("life_regain_inc"), _REGAIN_CAP * missing_life)
    es_regain_tick = min(missing_es * source.total("energy_shield_regain_inc"), _REGAIN_CAP * missing_es)
    life_regain_ps = life_regain_tick / life_regain_interval if life_regain_interval > 0 else 0.0
    shield_regain_ps = es_regain_tick / es_regain_interval if es_regain_interval > 0 else 0.0

    # Regen (over time): flat + %-of-max, × speed.
    life_regen_ps = (source.total("life_regen_flat") + source.total("life_regen_inc") * max_life) * (1.0 + source.total("life_regen_speed_inc"))
    mana_regen_ps = source.total("mana_regen_flat") + source.total("mana_regen_pct") * max_mana + source.total("mana_regen_inc") * max_mana

    # Temporary pools (computed in-loop, emitted as temporary_life_flat/pct + capped; re-read here for display).
    base_max_life = max_life      # max_life is Base (temp is a separate barrier, never folded in)
    base_max_mana = max_mana
    temp_life = source.total("temporary_life_flat") + source.total("temporary_life_pct") * base_max_life
    temp_mana = source.total("temporary_mana_flat") + source.total("temporary_mana_pct") * base_max_mana
    cap_life = source.total("max_temporary_life_pct") * base_max_life
    cap_mana = source.total("max_temporary_mana_pct") * base_max_mana
    if cap_life > 0:
        temp_life = min(temp_life, cap_life)
    if cap_mana > 0:
        temp_mana = min(temp_mana, cap_mana)

    # Net sustain (recovery − consumption). Consumption: reservation drains the usable pool (sealed); skill
    # life-cost is NYI. Net here = recovery rate (positive); sealed pools shrink the pool, not the rate.
    net_life = life_ps + life_regain_ps + life_regen_ps
    net_mana = mana_ps + mana_regen_ps

    # EHP: (Base Max Life + Temporary Life) vs the calc target's average armour mitigation.
    avg_mit = 0.5 * (float(d.get("armor_phys_mitigation", 0.0)) + float(d.get("armor_nonphys_mitigation", 0.0)))
    ehp_life = (max_life + temp_life) / (1.0 - avg_mit) if avg_mit < 1.0 else (max_life + temp_life)

    return RecoveryResult(
        restoration_life_per_sec=life_ps, restoration_mana_per_sec=mana_ps,
        restoration_life_total=life_total, restoration_mana_total=mana_total,
        excess_life_restoration=life_excess, excess_mana_restoration=mana_excess,
        restoration_sources=life_src + mana_src,
        life_regain_per_sec=life_regain_ps, shield_regain_per_sec=shield_regain_ps,
        life_regen_per_sec=life_regen_ps, mana_regen_per_sec=mana_regen_ps,
        temporary_life=temp_life, temporary_mana=temp_mana,
        total_max_life=max_life + temp_life, total_max_mana=max_mana + temp_mana,
        net_life_per_sec=net_life, net_mana_per_sec=net_mana,
        ehp_life=ehp_life,
    )
