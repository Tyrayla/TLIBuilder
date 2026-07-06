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
        spirit_magi_physique_inc, spirit_magi_skill_area_inc,
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

    def _add(stat: str, amt: float, text: str) -> None:
        buffed.add_with_source(stat, amt, SourceEntry(
            stat=stat, amount=amt, source_type="minion", label="Thunder Magus", source_name="Thunder Magus", text=text))

    empower = by_role.get("Empower")
    empower_uptime = 1.0
    if empower:
        from engine.skill_resolver import _parse_cast_time as _pct
        # True uptime — the buff is up (duration ÷ cooldown) of the time (6 s / 10 s = 60%). There are no
        # realistic minion CDR / skill-effect-duration sources, so model it directly: for a linear rate buff,
        # buff × uptime IS the DPS-weighted average. FLAG: at Stage 4+ the AS and damage buffs share the same
        # window, so scaling each independently slightly under-counts their PRODUCT vs the exact time-weighted
        # average — an accepted approximation (per the plan).
        _dur = float(empower.get("duration") or 0.0)
        _cd = _pct(empower.get("cooldown", "")) or 0.0
        empower_uptime = min(1.0, _dur / _cd) if (_dur > 0 and _cd > 0) else 1.0
        _pct_txt = f"{round(empower_uptime * 100)}% uptime"
        _add("minion_attack_speed_additional", 0.35 * empower_uptime,
             f"Thundercloud Surge: +35% additional Attack Speed (Euphoria) × {_pct_txt}")
        if stage >= 4:
            _add("minion_dmg_additional", 0.25 * empower_uptime,
                 f"Thundercloud Surge: +25% additional damage (Growth Stage 4+) × {_pct_txt}")
    if stage >= 5:
        _add("minion_dmg_additional", 0.50, "Growth Stage 5: +50% additional damage")

    results = []
    base = by_role.get("Base")
    enhanced = by_role.get("Enhanced")
    if base:
        results.append(calculate_minion_offense(buffed, base, base_stats, level, count, rate_multiplier=1.0 - enh_chance))
    if enhanced:
        # Thunderlight Arrow (Enhanced) projectile mechanics — makes it correctly STRONGER than Base at Stage 3+.
        #  • +1 Base Projectile Quantity at Stage 3+ → 2 projectiles that "can hit the same enemy" = a same-target
        #    Shotgun (70% falloff → each extra hit deals 30% → ×1.30 for 2). External +Proj does NOT add firing
        #    projectiles for this skill, so the shotgun count uses only the skill's own quantity.
        #  • +5% additional Damage per +1 Projectile Quantity — counts the Stage-3 +1 AND external minion +Proj
        #    (multiple-projectile supports on the link / a +Proj weapon shared to the minion → the new pool).
        #  • Projectiles always Penetrate/track — multi-target / clear only, no single-target DPS effect.
        stage3 = stage >= 3
        q_base_bonus = 1 if stage3 else 0                                   # the skill's own +1 (firing) projectile
        q_external = source.total("minion_projectile_quantity_flat")        # external → additional dmg only
        fire_projectiles = 1 + q_base_bonus                                 # shotgun count (external excluded)
        proj_quantity_bonus = q_base_bonus + q_external                     # each +1 above base → +5% additional
        enh_additional = 0.05 * proj_quantity_bonus
        results.append(calculate_minion_offense(
            buffed, enhanced, base_stats, level, count, rate_multiplier=enh_chance,
            shotgun_hits=fire_projectiles, shotgun_falloff=0.70,
            extra_additional=enh_additional,
            extra_additional_label=f"Thunderlight Arrow: +5% additional damage × {proj_quantity_bonus:g} Projectile Quantity",
            penetrates=True))
    if empower:
        r = nyi_offense(empower, level)
        r.nyi = [f"Thundercloud Surge is an Empower buff (Euphoria +35% Attack Speed"
                 + (", +25% damage at Growth Stage 4+" if stage >= 4 else ", +25% damage once at Growth Stage 4+")
                 + f") — folded into the attacks above at {round(empower_uptime * 100)}% uptime "
                 + "(6 s buff ÷ 10 s cooldown), no direct hit."]
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
    return combined
