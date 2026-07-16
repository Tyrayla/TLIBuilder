"""Thunder Magus (Spirit Magus) — bespoke minion DPS module.

Kit (from _skills.json / Help DB):
  • Lightning Star (Base, 232% of Base Damage, Attack) — the always-on attack.
  • Thunderlight Arrow (Enhanced, 189% at L20) — REPLACES the Base on a chance (proc/replace, like Steep Strike;
    base chance 0%, +30% at Growth Stage 2, plus spirit_magi_enhanced_skill_chance from gear/talents). At 100%
    the Base never fires. Modelled by splitting the shared attack rate: Base at (1−chance), Enhanced at chance,
    so summing the two = the true blended DPS. Its lower coefficient is offset by projectile mechanics that make
    it STRONGER at Stage 3+: +1 Base Projectile Quantity (Stage 3+) → 2 same-target projectiles = Shotgun (70%
    falloff → ×1.30); +5% additional damage per +1 Projectile Quantity (Stage-3 +1 AND external minion +Proj);
    always Penetrates/tracks (multi-target only). Net ≈ 258% at Stage 3+ vs Base's 232% (189 × 1.30 × 1.05).
  • Thundercloud Surge (Empower) — a self-buff (Euphoria +35% additional Attack Speed; +25% additional damage
    at Growth Stage 4+). No direct hit; folded into the attacks at its TRUE uptime (6 s buff ÷ 10 s cd = 60%),
    since there are no realistic minion CDR / buff-duration sources (buff × uptime = the DPS-weighted average).
  • Lightning Surge (Ultimate) — only fires in Full Bloom, which requires Iris (Growing Breeze). Left NYI until
    Iris/Full Bloom is modelled (Tyra's call).

Growth Stage 5 grants +50% additional damage — applied to all the attacks. All damage is Physical, 100%
converted to Lightning by the owner (nets to Lightning; the coefficient already lands on the Lightning tag).
"""
from dataclasses import replace

from engine.models import SourceEntry

OWNER_ID = "summon_thunder_magus"

_ROLE_TAGS = {"base skill": "Base", "enhanced skill": "Enhanced", "empower": "Empower", "ultimate": "Ultimate"}


def _role(ability: dict) -> str:
    tl = {str(t).lower() for t in (ability.get("skill_tags") or [])}
    for tag, role in _ROLE_TAGS.items():
        if tag in tl:
            return role
    return ""


def handler(source, owner, base_stats, level, count):
    """Return ONE OffenseResult for a Thunder Magus whose hit forms are its damage abilities (Base + Enhanced,
    uptime-split shares) — like a player multi-form skill. Empower/Ultimate are buffs/locked (folded in as NYI
    notes, not forms)."""
    from engine.minion_offense import (
        calculate_minion_offense, nyi_offense, spirit_magi_growth, growth_stage, combine_minion_forms,
        spirit_magi_physique_inc, spirit_magi_skill_area_inc, fold_spirit_magi_pools, ability_label,
    )
    by_role: dict[str, dict] = {}
    for a in owner.get("minion_skills") or []:
        by_role.setdefault(_role(a), a)

    growth = spirit_magi_growth(source)
    stage = growth_stage(growth)
    # Enhanced-Skill chance: gear/talent pool + Growth Stage 2 (+30%), capped at 100%.
    enh_chance = source.total("spirit_magi_enhanced_skill_chance") + (0.30 if stage >= 2 else 0.0)
    enh_chance = max(0.0, min(1.0, enh_chance))

    # Fold the Empower buff + Growth stage bonuses into a COPY of the source (never mutate the shared one).
    buffed = replace(source, _entries=list(source._entries), source_log=list(source.source_log))
    # Spirit-Magi-scoped damage/crit gear/talents carry the `spirit_magi` tag (not `minion`) and would otherwise
    # be dropped — fold them into the generic minion pools so a magus consumes them. Also folds the per-Growth
    # pools (Talons of Abyss) scaled by this magus's Growth.
    fold_spirit_magi_pools(buffed, growth)

    def _add(stat: str, amt: float, text: str) -> None:
        buffed.add_with_source(stat, amt, SourceEntry(
            stat=stat, amount=amt, source_type="minion", label="Thunder Magus", source_name="Thunder Magus", text=text))

    # Empower Effect scales the Euphoria buff magnitudes — the MINION/magi Empower Effect only (spirit_magi_*),
    # never the player's Empower Effect.
    emp_eff = 1.0 + source.total("spirit_magi_empower_effect_additional")

    empower = by_role.get("Empower")
    empower_uptime = 1.0
    _dur_eff = _cd_eff = _emp_cast_time = 0.0
    empower_display: dict | None = None
    if empower:
        from engine.skill_resolver import _parse_cast_time as _pct
        # True uptime = effective duration ÷ effective cooldown, clamped ≤ 1 (base 6 s / 10 s = 60%). Now driven
        # by GENERIC minion mods so it responds to Cooldown Recovery / Extended Duration (from gear, talents, or
        # supports converted to minion stats): duration ×(1 + Minion Skill Effect Duration), cooldown ÷(1 + Minion
        # CDR). For a linear rate buff, buff × uptime IS the DPS-weighted average. FLAG: at Stage 4+ the AS and
        # damage buffs share the same window, so scaling each independently slightly under-counts their PRODUCT.
        _dur_inc = source.total("minion_skill_effect_duration_inc")
        _cdr_inc = source.total("minion_cdr_speed_inc")
        _dur0 = float(empower.get("duration") or 0.0)
        _dur = _dur0 * (1.0 + _dur_inc)
        _cd0 = _pct(empower.get("cooldown", "")) or 0.0
        _cd = _cd0 / (1.0 + _cdr_inc) if _cd0 > 0 else 0.0
        _emp_cast_time = _pct(empower.get("cast_speed", "")) or 0.0    # cast-slot: attacking paused while casting it
        _dur_eff, _cd_eff = _dur, _cd
        empower_uptime = min(1.0, _dur / _cd) if (_dur > 0 and _cd > 0) else 1.0
        _pct_txt = f"{round(empower_uptime * 100)}% uptime"
        _eff_txt = f" × {round(emp_eff * 100)}% Empower Effect" if abs(emp_eff - 1.0) > 1e-9 else ""
        _add("minion_attack_speed_additional", 0.35 * emp_eff * empower_uptime,
             f"Thundercloud Surge: +35% additional Attack Speed (Euphoria){_eff_txt} × {_pct_txt}")
        if stage >= 4:
            _add("minion_dmg_additional", 0.25 * emp_eff * empower_uptime,
                 f"Thundercloud Surge: +25% additional damage (Growth Stage 4+){_eff_txt} × {_pct_txt}")

        # Surface the Empower like a normal player empower skill: Empower Effect, base→effective cooldown/duration,
        # an uptime box, and each Euphoria buff's base → effective magnitude. Effective magnitude = base × Empower
        # Effect × uptime (the same value folded into the attacks above). Frontend renders each with its breakdown.
        _buffs = [{
            "label": "Attack Speed (Euphoria)", "stat": "attack_speed", "base": 0.35,
            "value": 0.35 * emp_eff * empower_uptime, "active": True,
        }, {
            "label": "Damage (Growth Stage 4+)", "stat": "damage", "base": 0.25,
            "value": (0.25 * emp_eff * empower_uptime) if stage >= 4 else 0.0, "active": stage >= 4,
            "note": None if stage >= 4 else "Unlocks at Growth Stage 4",
        }]
        empower_display = {
            # MUST equal the empower hit_form's name (ability_label → "Thundercloud Surge (Empower)") so the
            # frontend can match the selected NYI form to this display block; a bare skill name would not match.
            "name": ability_label(empower),
            "empower_effect": emp_eff,
            "empower_effect_inc": source.total("spirit_magi_empower_effect_additional"),
            "base_cooldown": _cd0,
            "cooldown": _cd,
            "cdr_inc": _cdr_inc,
            "base_duration": _dur0,
            "duration": _dur,
            "duration_inc": _dur_inc,
            "uptime": empower_uptime,
            "buffs": _buffs,
        }
    if stage >= 5:
        _add("minion_dmg_additional", 0.50, "Growth Stage 5: +50% additional damage")

    # Empower cast-slot: the magus visibly stops attacking to cast Thundercloud Surge, losing its cast time each
    # cooldown. Scales BOTH Base and Enhanced rates down by (1 − cast_time ÷ effective_cooldown). CDR shortens the
    # cooldown → more frequent casts → MORE slot loss, which correctly dampens CDR's uptime gain (Extended Duration,
    # which adds no casts, stays strictly more efficient — matches Tyra's 202→207 CDR vs 202→215 CDR+Duration tests).
    # The nominal 0.6 s cast overlaps the attack's recovery frames, so the EFFECTIVE attacking time lost is ~half
    # (the visible pause). 0.5 calibrated to the magus-only base-only 202 (full cast time would over-count to ~196).
    _CAST_SLOT_EFFICIENCY = 0.5
    cast_slot_factor = (1.0 - _CAST_SLOT_EFFICIENCY * (_emp_cast_time / _cd_eff)
                        if (_emp_cast_time > 0 and _cd_eff > 0) else 1.0)
    cast_slot_factor = max(0.0, cast_slot_factor)

    results = []
    base = by_role.get("Base")
    enhanced = by_role.get("Enhanced")
    if base:
        results.append(calculate_minion_offense(buffed, base, base_stats, level, count,
                                                 rate_multiplier=(1.0 - enh_chance) * cast_slot_factor))
    if enhanced:
        # Thunderlight Arrow (Enhanced) — reverse-engineered + validated in-game (Tyra, 2026-07-06) against
        # magus-only DPS at 0/18/47/100 % Enhanced chance (202 / 265 / 346 / 588), all reproduced within ~1 %.
        #  • Deals 2 FULL hits per cast: the arrow passes THROUGH the target, tracks back, and hits AGAIN for equal
        #    damage (no falloff). Innate at every Growth stage — this REPLACES the old Stage-3 same-target-shotgun
        #    guess. (Help DB: Enhanced REPLACES the Base skill on proc.)
        #  • Fires with a much shorter recovery ONLY when it follows a Base attack ("fast insert"); chained
        #    Enhanced→Enhanced runs at the normal cadence (confirmed by the 100 % clip). The net DPS boost scales
        #    as p(1−p): large at low chance (every Enhanced follows a Base), vanishing at 100 % (no Base to insert
        #    after). Modelled as an effective fire-rate bump on the Enhanced form — rate ×= (1 + F·(1−p)) — so the
        #    p(1−p) curve falls out of (1−p) base attacks × the boosted Enhanced rate, no special-casing.
        #    F=0.90 calibrated to the 18 % point; it then PREDICTS 47 %→346 and 100 %→588 (measured 346 / 588).
        #  • The Stage-3 "+1 Projectile" and external +Proj are multi-target only (extra arrows) → +5% additional
        #    per projectile, NOT a single-target shotgun.
        _F_INSERT = 0.90
        p = enh_chance
        enh_rate_mult = p * (1.0 + _F_INSERT * (1.0 - p)) * cast_slot_factor
        proj_quantity_bonus = (1 if stage >= 3 else 0) + source.total("minion_projectile_quantity_flat")
        enh_additional = 0.05 * proj_quantity_bonus
        results.append(calculate_minion_offense(
            buffed, enhanced, base_stats, level, count, rate_multiplier=enh_rate_mult,
            shotgun_hits=2, shotgun_falloff=0.0,          # through + return = 2 full-damage hits
            extra_additional=enh_additional,
            extra_additional_label=f"Thunderlight Arrow: +5% additional damage × {proj_quantity_bonus:g} Projectile Quantity"))
    if empower:
        r = nyi_offense(empower, level)
        _win = (f"{_dur_eff:g} s buff ÷ {_cd_eff:g} s cooldown" if _cd_eff and abs(_dur_eff - 6.0) + abs(_cd_eff - 10.0) > 1e-9
                else "6 s buff ÷ 10 s cooldown")
        r.nyi = [f"Thundercloud Surge is an Empower buff (Euphoria: +35% additional Attack Speed"
                 + (", and +25% additional damage at Stage 4+" if stage >= 4 else "; +25% additional damage unlocks at Stage 4+")
                 + f") — folded into the attacks above at {round(empower_uptime * 100)}% uptime ({_win}), no direct hit. "
                 + "Uptime responds to Minion Cooldown Recovery Speed / Skill Effect Duration."]
        results.append(r)
    ultimate = by_role.get("Ultimate")
    if ultimate:
        r = nyi_offense(ultimate, level)
        r.nyi = ["Lightning Surge (Ultimate) only fires in Full Bloom, which requires Iris (Growing Breeze). "
                 "NYI until Iris / Full Bloom is modelled."]
        results.append(r)

    combined = combine_minion_forms(owner.get("name") or "Thunder Magus", results, count)
    # Surface the Spirit Magus Growth state (glossary 759) for the minion info panel. Physique & Skill Area are
    # display-only (don't change single-target hit DPS); the DPS-relevant stage bonuses are already folded above.
    combined.spirit_magi_growth = growth
    combined.spirit_magi_stage = stage
    combined.spirit_magi_physique_inc = spirit_magi_physique_inc(source, growth)
    combined.skill_area_inc = spirit_magi_skill_area_inc(stage)   # +10% additional per stage (display only)
    combined.spirit_magi_enhanced_chance = enh_chance
    combined.spirit_magi_max = count
    combined.minion_empower = empower_display
    return combined
