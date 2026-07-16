"""Utility / buff stats — aura buffs (apply_aura_buffs) and mana/life sealing (apply_reservation).

Parallels offense.py / defense.py: both run INSIDE the compute fixed-point loop, after the source is fully
aggregated (gear, talents, custom mods, standard supports), so they read the TRUE totals. apply_aura_buffs
scales the (server-parsed, unscaled) aura buffs by Aura Effect; apply_reservation computes Sealed Mana / Sealed
Life from each sealing skill's base seal × support Mana Multipliers ÷ (1 + Sealed Mana Compensation), per the
Help-DB formulas, and runs after derive_stats so Max Mana / Max Life are final.
"""
from __future__ import annotations

import re

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
            enabled = m.get("enabled", True)   # disabled aura: build summary, don't fold buffs into the engine

            # ── Phase 1: emit this aura's OWN Aura Effect (e.g. per-stack additional), scoped to the aura's
            # slot so it feeds only this aura's factor (and supports scoped to the same slot stack with it).
            # Emitted raw (NOT multiplied by Aura Effect) — Cruelty's per-stack line is "Not affected by
            # Aura Effects", so increased Aura Effect never scales it.
            for b in blist:
                if not b["is_aura_effect"]:
                    continue
                g = _gate_mult(b["condition_expr"], active_booleans, numeric_vals)
                if g == 0.0 or not enabled:
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
                    if g != 0.0 and enabled:
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
                "granted": granted, "nyi": m["nyi"], "review": m.get("review") or [], "enabled": enabled,
                "stack_condition": m["stack_condition"], "max_stacks": m["max_stacks"],
            })
    finally:
        source._recording = prev_rec

    return summaries


def apply_empower_buffs(source, empower_buffs, empower_meta, active_booleans, numeric_vals) -> list[dict]:
    """Scale + emit empower (Euphoria) buffs into `source`; return per-empower summaries. Mirrors apply_aura_buffs:
    Empower Skill Effect is read SLOT-LOCAL (global gear/talents + the skill's own line + its empower supports), but
    the buffs are emitted PLAYER-WIDE (slot=None) so they reach the slot-1 main skill. Increased sums, additional
    multiplies. Recording on so the Empower-Effect reads register as consumed (empower-effect mods badge working)."""
    if not empower_buffs:
        return []

    by_skill: dict[str, list[dict]] = {}
    for b in empower_buffs:
        by_skill.setdefault(b["skill_id"], []).append(b)

    prev_rec = source._recording
    source._recording = True
    summaries: list[dict] = []
    try:
        for sid, m in (empower_meta or {}).items():
            slot = m.get("slot")
            blist = by_skill.get(sid, [])
            enabled = m.get("enabled", True)   # disabled empower: build summary, don't fold buffs into the engine

            # Phase 1: emit this skill's OWN Empower-Effect entries (slot-scoped) — its own line + its supports —
            # so they feed only this empower's factor (not other skills').
            for b in blist:
                if not b["is_empower_effect"]:
                    continue
                g = _gate_mult(b["condition_expr"], active_booleans, numeric_vals)
                if g == 0.0 or not enabled:
                    continue
                amt = b["base_amount"] * g
                _emit(source, b["stat_key"], amt, b.get("scope"),
                      SourceEntry(stat=b["stat_key"], amount=amt, source_type="empower",
                                  label=b["name"], text=b["text"], points=1, slot=slot,
                                  source_name=b["name"]), slot=slot)

            # Slot-local Empower Effect = global + this skill's slot-scoped entries.
            eff = source.materialize_for_skill(set(), slot=slot) if slot is not None else source
            factor = (1.0 + eff.total("empower_effect_inc")) * (1.0 + eff.total("empower_effect_additional"))

            # Phase 2: emit the player-wide buffs (slot=None) scaled by the factor (gated).
            granted: list[dict] = []
            for b in blist:
                g = _gate_mult(b["condition_expr"], active_booleans, numeric_vals)
                base = b["base_amount"] * g
                if b["is_empower_effect"]:
                    amt = base   # the Empower-Effect pool itself is not scaled by Empower Effect
                else:
                    amt = base * factor
                    if g != 0.0 and enabled:
                        _emit(source, b["stat_key"], amt, b.get("scope"),
                              SourceEntry(stat=b["stat_key"], amount=amt, source_type="empower",
                                          label=b["name"], text=b["text"], points=1, source_name=b["name"]))
                granted.append({
                    "stat": b["stat_key"], "base": base, "amount": amt, "text": b["phrase"],
                    "per_stack": b["per_stack"], "is_empower_effect": b["is_empower_effect"],
                })

            summaries.append({
                "skill_id": sid, "name": m["name"], "level": m["level"], "empower_effect_inc": factor - 1.0,
                "granted": granted, "nyi": m["nyi"], "review": m.get("review") or [], "enabled": enabled,
                "stack_condition": m["stack_condition"], "max_stacks": m["max_stacks"],
            })
    finally:
        source._recording = prev_rec

    return summaries


def apply_elixir_buffs(source, elixir_buffs, elixir_meta, active_booleans, numeric_vals) -> list[dict]:
    """Scale + emit elixir buffs into `source`; return per-elixir summaries. Mirrors apply_empower_buffs:
    Elixir Effect is read SLOT-LOCAL (global gear/talents/core-talents like Tailored Remedy + any slot-scoped
    elixir-effect), buffs are emitted PLAYER-WIDE (slot=None). Increased sums, additional multiplies. Flag stats
    (lucky_<type>, es_uninterruptible, es_bypass) carry no_scale and are emitted at base. Full uptime → buffs
    apply at full value; timing (duration/cooldown/charges) is display-only. Recording on so the Elixir-Effect
    reads register as consumed (elixir-effect mods badge working)."""
    if not elixir_buffs and not elixir_meta:
        return []   # nothing equipped. (A pure-restoration tonic has meta + restoration but no buffs → still process.)

    by_skill: dict[str, list[dict]] = {}
    for b in elixir_buffs:
        by_skill.setdefault(b["skill_id"], []).append(b)

    prev_rec = source._recording
    source._recording = True
    summaries: list[dict] = []
    try:
        for sid, m in (elixir_meta or {}).items():
            slot = m.get("slot")
            blist = by_skill.get(sid, [])
            # DISABLED elixir: still build the summary (so the Skill panel shows its stats marked disabled), but do
            # NOT fold its buffs into the engine.
            enabled = m.get("enabled", True)

            # Phase 1: emit this elixir's OWN Elixir-Effect entries (slot-scoped), if any.
            for b in blist:
                if not b["is_elixir_effect"]:
                    continue
                g = _gate_mult(b["condition_expr"], active_booleans, numeric_vals)
                if g == 0.0 or not enabled:
                    continue
                amt = b["base_amount"] * g
                _emit(source, b["stat_key"], amt, b.get("scope"),
                      SourceEntry(stat=b["stat_key"], amount=amt, source_type="elixir",
                                  label=b["name"], text=b["text"], points=1, slot=slot,
                                  source_name=b["name"]), slot=slot)

            # Slot-local Elixir Effect = global (gear/talents/Tailored Remedy) + this elixir's slot-scoped entries.
            eff = source.materialize_for_skill(set(), slot=slot) if slot is not None else source
            factor = (1.0 + eff.total("elixir_effect_inc")) * (1.0 + eff.total("elixir_effect_additional"))

            # Phase 2: emit the player-wide buffs (slot=None), scaled by the factor (gated); flags stay at base.
            granted: list[dict] = []
            for b in blist:
                g = _gate_mult(b["condition_expr"], active_booleans, numeric_vals)
                base = b["base_amount"] * g
                if b["is_elixir_effect"]:
                    amt = base   # the Elixir-Effect pool itself is not scaled by Elixir Effect
                else:
                    amt = base if b.get("no_scale") else base * factor
                    if g != 0.0 and enabled:
                        _emit(source, b["stat_key"], amt, b.get("scope"),
                              SourceEntry(stat=b["stat_key"], amount=amt, source_type="elixir",
                                          label=b["name"], text=b["text"], points=1, source_name=b["name"]))
                granted.append({
                    "stat": b["stat_key"], "base": base, "amount": amt, "text": b["phrase"],
                    "no_scale": bool(b.get("no_scale")), "is_elixir_effect": b["is_elixir_effect"],
                })

            # Timing (display-only). Duration scales with general Skill Effect Duration (increased + additional) AND
            # the elixir-specific Elixir Duration pool; cooldown is reduced by Cooldown Recovery Speed; max charges
            # fold the global "+N Max Charge" pool + the elixir's support gems. The component fields (base_*,
            # *_global, support_sources) drive the per-row source breakdowns on the Skill panel.
            t = m.get("timing") or {}
            dur_inc = source.total("skill_effect_duration_inc")
            dur_add_general = source.total("skill_effect_duration_additional")
            dur_add_elixir = source.total("elixir_duration_additional")
            base_dur = t.get("base_duration")
            duration = (base_dur * (1.0 + dur_inc) * (1.0 + dur_add_general) * (1.0 + dur_add_elixir)
                        if base_dur is not None else None)
            base_cd = t.get("cooldown")
            cdr = source.total("cdr_speed_inc")
            cooldown = (base_cd / (1.0 + cdr)) if base_cd is not None else None
            charges = t.get("charges") or 0.0
            global_max_charge = source.total("max_charge_flat")
            global_charge_ps = source.total("elixir_charging_progress_flat")
            support_charge_ps = t.get("support_charge_per_second") or 0.0
            support_max_charge = t.get("support_max_charge") or 0.0
            # Restoration tonics: amount × Elixir Effect, window × Elixir Duration. Recast cadence = max(cooldown,
            # charge-regen time) — sustained recast is usually CHARGE-limited (charge_threshold ÷ charge/sec from
            # Hyper Metabolism / Steel Vanguard / Omni-elixir belt; on-defeat charge excluded for single-target),
            # falling back to cooldown when charge gen is fast. No charge gen → not sustainable (recast → huge → ~0
            # recovery). The general Restoration Effect/Duration + pct→max-pool resolution happen in engine.recovery.
            elixir_dur_factor = (1.0 + dur_inc) * (1.0 + dur_add_general) * (1.0 + dur_add_elixir)
            charge_ps = support_charge_ps + global_charge_ps
            charge_threshold = t.get("charge_threshold")
            if charge_threshold and charge_ps > 0:
                charge_regen = charge_threshold / charge_ps
            elif charge_threshold:
                charge_regen = 1.0e9   # has a charge cost but no charge generation → unsustainable
            else:
                charge_regen = 0.0     # no charge gating → cooldown-limited
            recast = max(cooldown or 0.0, charge_regen)
            restoration_out = [] if not enabled else [{
                "pool": r["pool"], "mode": r["mode"], "base_amount": r["base_amount"] * factor,
                "window": r["base_window"] * elixir_dur_factor, "recast": recast, "source": m["name"],
            } for r in (m.get("restoration") or [])]
            summaries.append({
                "restoration": restoration_out,
                "skill_id": sid, "name": m["name"], "level": m["level"], "elixir_effect_inc": factor - 1.0,
                "granted": granted, "nyi": m["nyi"], "review": m.get("review") or [], "has_blur": m.get("has_blur"),
                "enabled": enabled,
                # Duration = base × (1 + Skill Duration) × (1 + Additional Skill Duration) × (1 + Elixir Duration).
                "duration": duration, "base_duration": base_dur,
                "duration_inc": dur_inc, "duration_additional": dur_add_general + dur_add_elixir,
                # Cooldown = base ÷ (1 + Cooldown Recovery Speed).
                "cooldown": cooldown, "base_cooldown": base_cd, "cdr": cdr,
                # Charge/sec = support gems + global charging pool; max charges = base + global pool + support gems.
                "charge_per_second": support_charge_ps + global_charge_ps,
                "global_charge_per_second": global_charge_ps,
                "base_charges": charges, "global_max_charge": global_max_charge,
                "max_charges": charges + global_max_charge + support_max_charge,
                "support_sources": t.get("support_sources") or [],
                # Recast cadence for restoration tonics (Effective uptime): the time to refill, = max(cooldown,
                # charge time). charge time = charge threshold ÷ charge/sec (or unsustainable with no charge gen).
                "charge_threshold": charge_threshold,
                "charge_regen": charge_regen if charge_threshold else None,
                "recast": recast if (m.get("restoration") or []) else None,
            })
    finally:
        source._recording = prev_rec

    return summaries


# ── Mana / Life sealing & reservation ───────────────────────────────────────────────
_PCT = lambda s: float(str(s).rstrip("%")) / 100.0   # noqa: E731 — "110.0%" -> 1.10, "50%" -> 0.5
# Lunar Eclipse's damage-per-Mana-sealed cap: "... up to +(57-60) % additional damage" (Noble rank range).
_UP_TO_RANGE_RE = re.compile(r"up to\s*\+?\(?\s*([\d.]+)\s*[-–]\s*([\d.]+)\s*\)?\s*%", re.I)


def _mana_multiplier(support_data: dict, otbt: bool) -> float:
    """A support's Mana Multiplier (its `mana_cost`, e.g. '110.0%' -> 1.10). Off the Beaten Track forces it
    to a fixed 95%."""
    if otbt:
        return 0.95
    mc = support_data.get("mana_cost")
    return _PCT(mc) if mc else 1.0


def _seal_dmg_cap(desc: str, rank) -> float:
    """Lunar Eclipse cap: parse 'up to +(min-max)%' and interpolate by the support's rank (1-5) within the
    range; default to the midpoint. Returns a fraction (e.g. 0.585)."""
    m = _UP_TO_RANGE_RE.search(desc or "")
    if not m:
        return 0.0
    lo, hi = float(m.group(1)), float(m.group(2))
    try:
        r = max(1, min(5, int(rank)))
        frac = (r - 1) / 4.0
    except (TypeError, ValueError):
        frac = 0.5
    return (lo + (hi - lo) * frac) / 100.0


def apply_reservation(source, skills_input, skills_by_id, attached_supports,
                      active_booleans, numeric_vals) -> dict:
    """Compute Sealed Mana / Sealed Life from every equipped sealing skill (ANY slot — auras, Focus, and
    active skills a support makes seal, e.g. Moon Strike + Lunar Eclipse). Per skill:
        amount = base_seal_frac × Max Mana × Π(support Mana Multiplier) / (1 + Sealed Mana Compensation)
    Compensation is per-skill (global + slot-local support comp + class-scoped focus/magus pools). A Seal
    Conversion support routes the amount to Sealed Life instead of Mana. Returns totals + per-skill pseudo-
    source breakdowns; emits Ward ES (from sealed pools) and Lunar Eclipse's per-Mana-sealed damage."""
    from engine.support_lines import parse_support
    from engine.support_mapper import map_line
    from engine.support_resolver import _tier_value, _support_level_bonus

    skills_input = skills_input or []
    max_mana = source.total("max_mana")
    max_life = source.total("max_life")
    otbt = "core_support_mana_mult_95" in (active_booleans or set())

    prev_rec = source._recording
    source._recording = True
    per_skill: list[dict] = []
    total_sealed_mana = 0.0
    total_sealed_life = 0.0
    lunar: list[tuple[int | None, float]] = []   # (slot, cap_frac) — damage-per-Mana-sealed, 2nd pass
    # Global Sealed Mana Compensation (gear/talents); per-support comp is read per skill below. Increased and
    # additional are SEPARATE multiplicative pools — the denominator is (1 + Σinc) × (1 + Σadd), NOT (1+Σ both)
    # summed (matches the engine's flat×(1+inc)×Π(1+add) model in derive.py; verified in-game: a +37.5% inc /
    # −66.25% add seal overflows Life because 1.375 × 0.3375 = 0.464 < 0.5, not 0.7125).
    comp_global_inc = source.total("sealed_mana_compensation_inc")
    comp_global_add = source.total("sealed_mana_compensation_additional")
    try:
        for sk in skills_input:
            if sk.get("enabled") is False:
                continue
            slot = sk.get("slot")
            data = skills_by_id.get(sk.get("skill_id")) or {}
            tags = {t.lower() for t in (data.get("skill_tags") or [])}

            # ── This skill's attached supports: read seal-modifiers DIRECTLY (works for every support type,
            #    incl. Noble/Magnificent which skip resolve_standard_supports): Mana Multiplier (mana_cost),
            #    Sealed-Mana-Compensation, Seal Conversion (→ Life), an imparted seal (Lunar Eclipse), and the
            #    per-Mana-sealed damage cap. Parsed via the same parse_support/map_line the badges use. ──
            sups = [s for s in (attached_supports or [])
                    if s.get("slot") == slot and s.get("enabled", True) and s.get("item_id")]
            mult = 1.0
            mult_breakdown: list[dict] = []
            comp_support_inc = 0.0
            comp_support_add = 0.0
            comp_sources: list[dict] = []
            imparted = 0.0
            to_life = False
            for s in sups:
                sd = skills_by_id.get(s["item_id"]) or {}
                eff_level = _tier_value(s.get("level")) + _support_level_bonus(source, sd.get("skill_tags"))
                for ln in parse_support(sd).lines:
                    for c in map_line(ln, eff_level, None, {}):
                        if c.stat_key == "sealed_mana_compensation_inc":
                            comp_support_inc += c.amount
                            comp_sources.append({"label": sd.get("name") or s["item_id"], "value": c.amount, "kind": "increased"})
                            source.consumed_stats.add(c.stat_key)
                        elif c.stat_key == "sealed_mana_compensation_additional":
                            comp_support_add += c.amount
                            comp_sources.append({"label": sd.get("name") or s["item_id"], "value": c.amount, "kind": "additional"})
                            source.consumed_stats.add(c.stat_key)
                        elif c.stat_key == "seal_to_life":
                            to_life = True
                            source.consumed_stats.add("seal_to_life")
                        elif c.stat_key == "imparted_seal_mana_pct":
                            imparted = max(imparted, c.amount)
                            source.consumed_stats.add("imparted_seal_mana_pct")
                m = _mana_multiplier(sd, otbt)
                mult *= m
                mult_breakdown.append({"name": sd.get("name") or s["item_id"], "mult": m})
                desc = " ".join(sd.get("description_lines") or [])
                if "mana sealed" in desc.lower() and "up to" in desc.lower():
                    lunar.append((slot, _seal_dmg_cap(desc, s.get("rank"))))

            # Class-scoped global compensation (Focus / Spirit Magus pools — gear/talents/spirits, not supports).
            comp_class = 0.0
            if "focus" in tags:
                comp_class += source.total("focus_skill_sealed_mana_comp_inc")
            if "spirit magus" in tags:
                comp_class += source.total("spirit_magi_sealed_mana_comp_inc")

            raw = data.get("sealed_mana")
            if raw:
                # A skill's OWN base seal scales with its supports (Mana Multipliers + per-support compensation).
                base_frac = _PCT(raw)
                comp_inc = comp_global_inc + comp_class + comp_support_inc
                comp_add = comp_global_add + comp_support_add
            else:
                # A support-IMPARTED seal (Lunar Eclipse & similar) is a fixed reservation that scales ONLY with
                # the GLOBAL Sealed Mana Compensation pool — NOT support Mana Multipliers, NOT per-support comp
                # (verified in-game). Mana Cost % and Sealed Mana are distinct.
                base_frac = imparted
                mult, mult_breakdown, comp_sources = 1.0, [], []
                comp_inc = comp_global_inc + comp_class
                comp_add = comp_global_add
            if base_frac <= 0.0:
                continue

            # Increased and additional compensation are SEPARATE multiplicative factors: the denominator is
            # (1 + Σincreased) × (1 + Σadditional). `compensation` (net) is reported as denom − 1 so the displayed
            # "÷ (1 + Sealed Mana Compensation)" stays exact while the breakdown rows carry each pool's own value.
            denom = (1.0 + comp_inc) * (1.0 + comp_add)
            comp = denom - 1.0
            # Seal Conversion replaces the seal's POOL: a 50% seal becomes 50% of Max LIFE (not 50% of Mana
            # re-labeled), then the compensation penalty applies. So the base scales off the target pool's max.
            pool_max = max_life if to_life else max_mana
            amount = base_frac * pool_max * mult / denom if denom != 0 else 0.0
            if to_life:
                total_sealed_life += amount
            else:
                total_sealed_mana += amount

            per_skill.append({
                "skill_id": sk.get("skill_id"), "name": data.get("name") or sk.get("skill_id"), "slot": slot,
                "base_fraction": base_frac, "pool_max": pool_max, "support_mults": mult_breakdown,
                "comp_sources": comp_sources, "compensation": comp,
                "comp_increased": comp_inc, "comp_additional": comp_add, "amount": amount,
                "pool": "life" if to_life else "mana",
            })

        # Ward — Energy Shield from sealed pools. Bump the ALREADY-DERIVED max_energy_shield directly (scaled
        # by ES inc/additional), since derive_stats already ran this pass and isn't idempotent.
        ward_flat = (source.total("energy_shield_per_sealed_mana") * total_sealed_mana
                     + source.total("energy_shield_per_sealed_life") * total_sealed_life)
        if ward_flat:
            inc = source.total("max_energy_shield_inc")
            add = source.total("max_energy_shield_additional")
            source.add_with_source("max_energy_shield", ward_flat * (1.0 + inc) * (1.0 + add), SourceEntry(
                stat="max_energy_shield", amount=ward_flat, source_type="condition",
                label="Ward", text="Energy Shield from Sealed Mana/Life", points=1, source_name="Ward"))

        # Lunar Eclipse — "+1% additional damage per 100 Mana sealed, up to the cap" (slot-local to the host;
        # offense reads it from the final source after the loop).
        for slot, cap in lunar:
            bonus = min(total_sealed_mana / 100.0 * 0.01, cap) if cap > 0 else 0.0
            if bonus > 0:
                _emit(source, "dmg_additional", bonus, None,
                      SourceEntry(stat="dmg_additional", amount=bonus, source_type="support",
                                  label="Lunar Eclipse", text="+1% additional damage per 100 Mana sealed",
                                  points=1, slot=slot, source_name="Lunar Eclipse"), slot=slot)
    finally:
        source._recording = prev_rec

    return {
        "max_mana": max_mana, "sealed_mana": total_sealed_mana, "unsealed_mana": max_mana - total_sealed_mana,
        "max_life": max_life, "sealed_life": total_sealed_life, "unsealed_life": max_life - total_sealed_life,
        "sealed_mana_compensation": (1.0 + comp_global_inc) * (1.0 + comp_global_add) - 1.0,
        "insufficient_mana": total_sealed_mana > max_mana,
        "insufficient_life": total_sealed_life > max_life,
        "per_skill": per_skill,
    }
