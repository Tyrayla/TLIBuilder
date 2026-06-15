"""Utility / buff stats — auras now, reservation & sealing (Phase 2) later.

Parallels offense.py / defense.py: it runs INSIDE the compute fixed-point loop, after the source is fully
aggregated (gear, talents, custom mods, standard supports), so it can read the TRUE total Aura Effect and scale
the (server-parsed, unscaled) aura buffs correctly. An aura's own Aura Effect is emitted first so it feeds the
same-pass factor (self-feedback), and per-stack buffs are gated by their `<skill>_stacks` condition.
"""
from __future__ import annotations

from engine.aggregator import _eval_condition, _emit
from engine.models import SourceEntry

_AURA_EFFECT_KEYS = ("aura_effect_inc", "aura_effect_additional")


def _gate_mult(cond, active_booleans, numeric_vals) -> float:
    """Condition → multiplier: 1.0 when satisfied/absent, 0.0 when failed, or the numeric value for 'per' gates."""
    if cond is None:
        return 1.0
    r = _eval_condition(cond, active_booleans, numeric_vals)
    if isinstance(r, bool):
        return 1.0 if r else 0.0
    return float(r)


def apply_aura_buffs(source, aura_buffs, aura_meta, active_booleans, numeric_vals) -> list[dict]:
    """Scale + emit the unscaled aura buffs into `source`, and return per-aura summaries for the UI.
    Call once per fixed-point iteration, after standard supports are folded in.

    Aura Effect is computed PER AURA from its slot-local pool (global gear/talent/custom Aura Effect PLUS the
    aura's own per-stack additional AND any support's "Aura effect for the supported skill" — both slot-scoped
    to that aura's slot). Reads run with recording on so `aura_effect_inc/additional` register as consumed
    (so an aura support badges working, not Inactive)."""
    if not aura_buffs:
        return []

    by_skill: dict[str, list[dict]] = {}
    for b in aura_buffs:
        by_skill.setdefault(b["skill_id"], []).append(b)

    prev_rec = source._recording
    source._recording = True   # record the Aura-Effect reads → consumed_stats → correct support badges
    summaries: list[dict] = []
    try:
        for sid, m in (aura_meta or {}).items():
            slot = m.get("slot")
            blist = by_skill.get(sid, [])

            # ── Phase 1: emit this aura's OWN Aura Effect (e.g. per-stack additional), scoped to the aura's
            # slot so it feeds only this aura's factor (and supports scoped to the same slot stack with it).
            # Emitted raw (NOT multiplied by Aura Effect) — Cruelty's per-stack line is "Not affected by
            # Aura Effects", so increased Aura Effect never scales it.
            for b in blist:
                if not b["is_aura_effect"]:
                    continue
                g = _gate_mult(b["condition_expr"], active_booleans, numeric_vals)
                if g == 0.0:
                    continue
                amt = b["base_amount"] * g
                _emit(source, b["stat_key"], amt, b.get("scope"),
                      SourceEntry(stat=b["stat_key"], amount=amt, source_type="aura",
                                  label=b["name"], text=b["text"], points=1, slot=slot,
                                  source_name=b["name"]), slot=slot)

            # Slot-local Aura Effect = global + this aura's slot-scoped entries (own per-stack + its supports).
            eff = source.materialize_for_skill(set(), slot=slot) if slot is not None else source
            # Help-DB formula: Base × (1 + Σ increased) × (1 + Σ additional) — separate factors, so increased
            # does not scale additional. 40 Cruelty stacks (+100% additional) with +30% increased → ×1.3 × 2.0.
            factor = (1.0 + eff.total("aura_effect_inc")) * (1.0 + eff.total("aura_effect_additional"))

            # ── Phase 2: emit the player-wide (global) buffs scaled by the factor (gated). ──
            granted: list[dict] = []
            for b in blist:
                g = _gate_mult(b["condition_expr"], active_booleans, numeric_vals)
                base = b["base_amount"] * g   # pre-Aura-Effect value (after condition/stack gating)
                if b["is_aura_effect"]:
                    amt = base   # the Aura Effect pool itself is NOT scaled by Aura Effect (emitted in phase 1)
                else:
                    amt = base * factor
                    if g != 0.0:
                        _emit(source, b["stat_key"], amt, b.get("scope"),
                              SourceEntry(stat=b["stat_key"], amount=amt, source_type="aura",
                                          label=b["name"], text=b["text"], points=1,
                                          source_name=b["name"]))
                granted.append({
                    "stat": b["stat_key"], "base": base, "amount": amt, "text": b["phrase"],
                    "per_stack": b["per_stack"], "is_aura_effect": b["is_aura_effect"],
                })

            summaries.append({
                "skill_id": sid, "name": m["name"], "level": m["level"], "aura_effect_inc": factor - 1.0,
                "granted": granted, "nyi": m["nyi"], "review": m.get("review") or [],
                "stack_condition": m["stack_condition"], "max_stacks": m["max_stacks"],
            })
    finally:
        source._recording = prev_rec

    return summaries
