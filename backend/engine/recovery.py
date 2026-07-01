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
# Baseline Mana Regeneration every character has (Help DB / Battle Mechanics/Base Mechanics/Others/Mana.md):
# "Players regenerate 7 Mana every second by default" + "Players regenerate 1.75% Mana every second by default".
_BASE_MANA_REGEN_FLAT = 7.0
_BASE_MANA_REGEN_PCT = 0.0175    # of Max Mana / sec (scales per level via Max Mana)


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
    restoration_es_per_sec: float = 0.0          # ES restoration from excess Life (Pixie Tear: excess→ES)
    restoration_es_total: float = 0.0
    excess_life_restoration: float = 0.0         # excess (overflow) restoration amount → Temporary Life / ES
    excess_mana_restoration: float = 0.0
    restoration_sources: list = field(default_factory=list)   # [{pool, source, total, duration, per_sec}]
    # Regain (on-hit, missing-based) — per second at the assumed Current Life/ES %
    life_regain_per_sec: float = 0.0
    shield_regain_per_sec: float = 0.0
    # Regen (over time)
    life_regen_per_sec: float = 0.0
    mana_regen_per_sec: float = 0.0
    base_mana_regen_per_sec: float = 0.0   # the always-on baseline (7/s + 1.75% Max Mana/s) portion of mana_regen
    # Temporary pools (separate used-first barrier) + totals
    temporary_life: float = 0.0
    temporary_mana: float = 0.0
    total_max_life: float = 0.0                  # Base Max Life + Temporary Life (display / EHP barrier)
    total_max_mana: float = 0.0
    # Consumption (self-consume drains: Mana Boil, life-consume affixes) per second
    consumption_life_per_sec: float = 0.0
    consumption_mana_per_sec: float = 0.0
    consumption_es_per_sec: float = 0.0
    # Active skill's intrinsic per-cast COST per second (cost ≠ consume — a SEPARATE drain that still reduces net
    # recovery / sustain). Shown on its own line, never lumped into the consumption figures above.
    skill_cost_mana_per_sec: float = 0.0
    skill_cost_life_per_sec: float = 0.0
    # Rolling "consumed recently" totals (per-sec × 4s window) — what per-N-consumed affixes + threshold gates read
    consumed_recently_life: float = 0.0
    consumed_recently_mana: float = 0.0
    consumed_recently_energy_shield: float = 0.0
    # Net sustain (recovery − consumption). Still excludes the skill's intrinsic Life/Mana COST (no skill-cost model)
    net_life_per_sec: float = 0.0
    net_mana_per_sec: float = 0.0
    net_es_per_sec: float = 0.0
    # Sustainability verdict (per pool): can recovery keep up at the assumed/solved pool %? time_to_empty in seconds
    # from the current pool when net is negative (None when sustainable).
    life_sustainable: bool = True
    mana_sustainable: bool = True
    es_sustainable: bool = True
    life_time_to_empty: float | None = None
    mana_time_to_empty: float | None = None
    es_time_to_empty: float | None = None
    # Steady-state ("stable") pool: the % you settle at (solved for consume builds, 100 otherwise) and that as a
    # flat pool. = the (unreserved) max when nothing consumes that pool.
    steady_life_pct: float = 100.0
    steady_life: float = 0.0
    steady_mana_pct: float = 100.0
    steady_mana: float = 0.0
    steady_es_pct: float = 100.0
    steady_es: float = 0.0
    # Effective HP (Life + Temporary Life vs the calc target's average mitigation)
    ehp_life: float = 0.0
    nyi: list = field(default_factory=list)   # skill Life/Mana cost now folded in via engine.skill_cost


def _pool_recovery(inputs, pool, pool_max, restoration_factor, duration_factor, missing, at_full, ignore_recast=False):
    """(total, per_sec, excess, sources[]) for one pool ('life'|'mana') from the restoration inputs. Each input is
    {pool, mode: pct|flat, base_amount (× Elixir Effect), window (× Elixir Duration), recast, source}; pct resolves
    against the pool's max, then × Restoration Effect.

    per-sec = total ÷ max(duration, recast) in Effective (real) uptime — the recast cadence (charge/cooldown) gaps
    the heal so you can't sustain faster than you can recast. In Full Uptime (`ignore_recast`) it's total ÷ duration:
    100% uptime regardless of realistic charge/cooldown constraints."""
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
        eff_recast = 0.0 if ignore_recast else recast
        divisor = max(dur, eff_recast)
        ps = t / divisor if divisor > 0 else 0.0
        total += t
        per_sec += ps
        # `recast` = the (un-suppressed) charge/cooldown cadence; `divisor` = what per-sec actually divides by
        # (= duration in Full Uptime, = max(duration, recast) in Effective) — both surfaced so the UI can show
        # "X over Ws, recast every Rs → P/s".
        sources.append({"pool": pool, "source": r.get("source", ""), "total": t, "duration": dur,
                        "recast": recast, "divisor": divisor, "per_sec": ps})
    # Excess (overflow → Temporary pools / ES): at full Life/Mana ALL restoration is excess; below full it refills
    # the assumed deficit first (effective) — a planner-input convention, not a combat sim.
    excess = total if at_full else max(0.0, total - missing)
    return total, per_sec, excess, sources


def restoration_excess(source: BuildSource, restoration_inputs: list | None, condition_state: dict | None = None):
    """(life_excess, mana_excess) restoration amounts — the IN-LOOP input to Temporary Life/Mana (Elixir of
    Immortality). Same effective/excess split calculate_recovery uses; exposed so compute.py can stash it for the
    next pass's hero-trait apply() (which converts excess → Temporary pools → damage)."""
    cs = condition_state or {}
    max_life = source.total("max_life")
    max_mana = source.total("max_mana")
    life_pct = float(cs.get("current_life_pct", 100.0) or 0.0)
    mana_pct = float(cs.get("current_mana_pct", 100.0) or 0.0)
    rf = _restoration_effect_factor(source)
    df = _restoration_duration_factor(source)
    _, _, life_excess, _ = _pool_recovery(restoration_inputs, "life", max_life, rf, df,
                                          max(0.0, (1.0 - life_pct / 100.0) * max_life), life_pct >= 100.0)
    _, _, mana_excess, _ = _pool_recovery(restoration_inputs, "mana", max_mana, rf, df,
                                          max(0.0, (1.0 - mana_pct / 100.0) * max_mana), mana_pct >= 100.0)
    return life_excess, mana_excess


def calculate_recovery(source: BuildSource, *, condition_state: dict | None = None,
                       restoration_inputs: list | None = None, reservation: dict | None = None,
                       defense: dict | None = None, uptime_mode=None, consumption: dict | None = None,
                       rates: dict | None = None, burst_rate: float = 0.0) -> RecoveryResult:
    from engine.uptime import is_real
    ignore_recast = not is_real(uptime_mode)   # Full Uptime (max) ignores recast cadence; Effective (real) honors it
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
        restoration_inputs, "life", max_life, r_factor, dur_factor, missing_life, life_pct >= 100.0, ignore_recast)
    mana_total, mana_ps, mana_excess, mana_src = _pool_recovery(
        restoration_inputs, "mana", max_mana, r_factor, dur_factor, missing_mana, mana_pct >= 100.0, ignore_recast)

    # Realm of Mercury (Unsullied Blade, Rosa #2): restores 15% of unsealed Max Mana per non-channeled attack use
    # (Born to Cleanse's −30% additional restoration is already folded into the emitted fraction by the trait). % of
    # current unreserved mana × the attack-use rate (exact at full mana) → a steady mana restoration feeding Net Mana
    # Recovery. The stat is emitted only in the Realm phase, so it's 0 in Mystic / for any other build.
    _rates = rates or {}
    _unres_mana = max(0.0, max_mana - float((reservation or {}).get("sealed_mana", 0.0) or 0.0))
    realm_restore_ps = (source.total("mana_restored_pct_current_per_attack_use")
                        * (mana_pct / 100.0 * _unres_mana) * max(0.0, float(_rates.get("attack", 0.0))))
    if realm_restore_ps > 1e-9:
        mana_ps += realm_restore_ps
        mana_src.append({"pool": "mana", "source": "Realm of Mercury (restore on attack)",
                         "total": 0.0, "duration": 0.0, "per_sec": realm_restore_ps})

    # Pixie Tear: a portion of EXCESS Life restoration is also applied to ES restoration ("unable to Charge or
    # Regain Energy Shield" — a separate restoration line). Total = excess Life × pct; rate follows the Life
    # restoration cadence scaled by the excess fraction.
    es_conv = source.total("excess_restoration_to_es_pct")
    es_restore_total = life_excess * es_conv if es_conv > 0 else 0.0
    es_restore_ps = (life_ps * (life_excess / life_total) * es_conv) if (es_conv > 0 and life_total > 1e-9) else 0.0
    if es_restore_total > 1e-9:
        life_src.append({"pool": "energy_shield", "source": "Pixie Tear (excess Life → ES)",
                         "total": es_restore_total, "duration": 0.0, "per_sec": es_restore_ps})

    # Regain (on-hit, missing-based): per-tick = min(missing × Σregain_inc, 30% of missing); per-sec / interval.
    life_regain_interval = _REGAIN_BASE_INTERVAL * (1.0 + source.total("regain_interval_additional")
                                                    + source.total("life_regain_interval_additional"))
    es_regain_interval = _REGAIN_BASE_INTERVAL * (1.0 + source.total("regain_interval_additional")
                                                  + source.total("energy_shield_regain_interval_additional"))
    life_regain_tick = min(missing_life * source.total("life_regain_inc"), _REGAIN_CAP * missing_life)
    es_regain_tick = min(missing_es * source.total("energy_shield_regain_inc"), _REGAIN_CAP * missing_es)
    life_regain_ps = life_regain_tick / life_regain_interval if life_regain_interval > 0 else 0.0
    shield_regain_ps = es_regain_tick / es_regain_interval if es_regain_interval > 0 else 0.0

    # Rebirth: "Converts N% of Life/ES Regain to Restoration Over Time". The converted fraction LEAVES the Regain
    # line (it's no longer missing-pool recovery) and becomes a steady Restoration rate (already reflects the
    # -N% additional Regain Interval applied above). Surfaced as its own restoration source.
    conv_life = source.total("life_regain_to_restoration")
    conv_es = source.total("es_regain_to_restoration")
    if conv_life > 0 and life_regain_ps > 0:
        moved = life_regain_ps * conv_life
        life_regain_ps -= moved
        life_ps += moved
        life_src.append({"pool": "life", "source": "Rebirth (converted Regain)", "total": 0.0,
                         "duration": 0.0, "per_sec": moved})
    if conv_es > 0 and shield_regain_ps > 0:
        moved = shield_regain_ps * conv_es
        shield_regain_ps -= moved
        es_restore_ps += moved
        life_src.append({"pool": "energy_shield", "source": "Rebirth (converted Regain)", "total": 0.0,
                         "duration": 0.0, "per_sec": moved})

    # Regen (over time): flat + %-of-max, × speed.
    life_regen_ps = (source.total("life_regen_flat") + source.total("life_regen_inc") * max_life) * (1.0 + source.total("life_regen_speed_inc"))
    # Baseline Mana Regen every character has (Help DB / Mana.md): 7 Mana/sec flat + 1.75% of Max Mana/sec. The %
    # component scales per level via Max Mana (which grows +5/level). Added on top of gear/talent regen sources.
    base_mana_regen = _BASE_MANA_REGEN_FLAT + _BASE_MANA_REGEN_PCT * max_mana
    # Mana Regeneration Speed (mana_regen_speed_inc) is a MULTIPLIER on the whole regen rate — mirrors Life's
    # life_regen_speed_inc — NOT a flat %-of-max/sec addition. (Values reach the hundreds of % via Compensatory et al.,
    # which only makes sense as a rate multiplier; in-game recount pending to confirm it also scales the innate base,
    # the TLI "speed"-stat convention assumed here.)
    mana_regen_ps = ((base_mana_regen + source.total("mana_regen_flat") + source.total("mana_regen_pct") * max_mana)
                     * (1.0 + source.total("mana_regen_speed_inc")))

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

    # Net sustain (recovery − consumption − skill cost). Self-consume drains AND the active skill's intrinsic per-cast
    # cost are both subtracted, but kept SEPARATE (cost ≠ consume): consumption arg carries each independently. Sealed
    # pools shrink the pool, not the rate.
    cons = consumption or {}
    cons_life = float(cons.get("life_per_sec", 0.0) or 0.0)
    cons_mana = float(cons.get("mana_per_sec", 0.0) or 0.0)
    cons_es = float(cons.get("energy_shield_per_sec", 0.0) or 0.0)
    sc_mana = float(cons.get("skill_cost_mana_per_sec", 0.0) or 0.0)   # skill cost — separate drain, NOT consumption
    sc_life = float(cons.get("skill_cost_life_per_sec", 0.0) or 0.0)
    cr_life = float(cons.get("consumed_recently_life", 0.0) or 0.0)
    cr_mana = float(cons.get("consumed_recently_mana", 0.0) or 0.0)
    cr_es = float(cons.get("consumed_recently_energy_shield", 0.0) or 0.0)
    # Burst-activation sustain (Surging Inspiration / Solid River kismet gear): these fire ONCE per burst TRIGGER (a
    # whole burst sequence), so per-second = per-burst × the burst-trigger rate (bursts/sec). Folded straight into Net
    # (no separate panel) with descriptive sources so the effect is visible. Mana lost = % of CURRENT mana; Life/ES
    # restored = % of LOST (missing) pool.
    _br = float(burst_rate or 0.0)
    _cur_mana_now = mana_pct / 100.0 * max_mana
    burst_mana_lost_ps = source.total("mana_lost_pct_current_per_burst") * _cur_mana_now * _br
    burst_life_restore_ps = source.total("life_restored_pct_lost_per_burst") * missing_life * _br
    burst_es_restore_ps = source.total("energy_shield_restored_pct_lost_per_burst") * missing_es * _br
    burst_src = []
    if burst_mana_lost_ps:
        burst_src.append({"pool": "mana", "source": "Spell Burst activation cost", "total": 0.0,
                          "duration": 0.0, "per_sec": -burst_mana_lost_ps})
    if burst_life_restore_ps:
        burst_src.append({"pool": "life", "source": "Spell Burst activation restore", "total": 0.0,
                          "duration": 0.0, "per_sec": burst_life_restore_ps})
    if burst_es_restore_ps:
        burst_src.append({"pool": "energy_shield", "source": "Spell Burst activation restore", "total": 0.0,
                          "duration": 0.0, "per_sec": burst_es_restore_ps})

    net_life = life_ps + life_regain_ps + life_regen_ps - cons_life - sc_life + burst_life_restore_ps
    net_mana = mana_ps + mana_regen_ps - cons_mana - sc_mana - burst_mana_lost_ps
    # ES recovery = restoration (Pixie excess→ES + Rebirth-converted) + missing-based Shield Regain. No ES regen modeled.
    net_es = es_restore_ps + shield_regain_ps - cons_es + burst_es_restore_ps

    # Sustainability verdict: net ≥ 0 → sustainable; else time-to-empty from the current pool. (Once C/F solve the
    # steady-state pool %, net AT that % is the honest verdict; a clamp-to-0 equilibrium = unsustainable.)
    max_es = source.total("max_energy_shield")
    cur_life = life_pct / 100.0 * max_life
    cur_mana = mana_pct / 100.0 * max_mana
    cur_es = es_pct / 100.0 * max_es
    # A clamped-to-0 steady state is a death spiral: net is ~0 there (nothing left to consume), but the pool is
    # empty, so it's unsustainable. Treat pool% ≤ 0 as unsustainable even when net ≈ 0.
    life_sustainable = net_life >= -1e-9 and life_pct > 1e-9
    mana_sustainable = net_mana >= -1e-9 and mana_pct > 1e-9
    es_sustainable = net_es >= -1e-9 and es_pct > 1e-9
    life_tte = 0.0 if (life_pct <= 1e-9 and cons_life > 0) else (
        (cur_life / -net_life) if (not life_sustainable and net_life < 0) else None)
    mana_tte = 0.0 if (mana_pct <= 1e-9 and cons_mana > 0) else (
        (cur_mana / -net_mana) if (not mana_sustainable and net_mana < 0) else None)
    es_tte = 0.0 if (es_pct <= 1e-9 and cons_es > 0) else (
        (cur_es / -net_es) if (not es_sustainable and net_es < 0) else None)

    # Effective hit pool: the STEADY-STATE current Life pool = life_pct × UNRESERVED Life (Max − Sealed; solved for
    # consume builds, = unreserved Max at 100% otherwise) + Temporary Life, vs the calc target's average armour
    # mitigation. "Current Life" is the unreserved pool — the honest base for a consume build (never at full Life).
    rsv = reservation or {}
    unres_life = max(0.0, max_life - float(rsv.get("sealed_life", 0.0) or 0.0))
    unres_mana = max(0.0, max_mana - float(rsv.get("sealed_mana", 0.0) or 0.0))
    steady_life_base = life_pct / 100.0 * unres_life
    steady_life = steady_life_base + temp_life
    steady_mana_base = mana_pct / 100.0 * unres_mana
    steady_es_base = es_pct / 100.0 * max_es
    avg_mit = 0.5 * (float(d.get("armor_phys_mitigation", 0.0)) + float(d.get("armor_nonphys_mitigation", 0.0)))
    ehp_life = steady_life / (1.0 - avg_mit) if avg_mit < 1.0 else steady_life

    return RecoveryResult(
        restoration_life_per_sec=life_ps, restoration_mana_per_sec=mana_ps,
        restoration_life_total=life_total, restoration_mana_total=mana_total,
        restoration_es_per_sec=es_restore_ps, restoration_es_total=es_restore_total,
        excess_life_restoration=life_excess, excess_mana_restoration=mana_excess,
        restoration_sources=life_src + mana_src + burst_src,
        life_regain_per_sec=life_regain_ps, shield_regain_per_sec=shield_regain_ps,
        life_regen_per_sec=life_regen_ps, mana_regen_per_sec=mana_regen_ps,
        base_mana_regen_per_sec=base_mana_regen,
        temporary_life=temp_life, temporary_mana=temp_mana,
        total_max_life=max_life + temp_life, total_max_mana=max_mana + temp_mana,
        consumption_life_per_sec=cons_life, consumption_mana_per_sec=cons_mana, consumption_es_per_sec=cons_es,
        skill_cost_mana_per_sec=sc_mana, skill_cost_life_per_sec=sc_life,
        consumed_recently_life=cr_life, consumed_recently_mana=cr_mana, consumed_recently_energy_shield=cr_es,
        net_life_per_sec=net_life, net_mana_per_sec=net_mana, net_es_per_sec=net_es,
        life_sustainable=life_sustainable, mana_sustainable=mana_sustainable, es_sustainable=es_sustainable,
        life_time_to_empty=life_tte, mana_time_to_empty=mana_tte, es_time_to_empty=es_tte,
        steady_life_pct=life_pct, steady_life=steady_life_base,
        steady_mana_pct=mana_pct, steady_mana=steady_mana_base,
        steady_es_pct=es_pct, steady_es=steady_es_base,
        ehp_life=ehp_life,
    )
