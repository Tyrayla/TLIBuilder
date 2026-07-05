"""Thunder Magus (Spirit Magus) — bespoke minion DPS module.

Kit (from _skills.json / Help DB):
  • Lightning Star (Base, 232% of Base Damage, Attack) — the always-on attack.
  • Thunderlight Arrow (Enhanced, 189% at L20) — REPLACES the Base on a chance (proc/replace, like Steep Strike;
    base chance 0%, +30% at Growth Stage 2, plus spirit_magi_enhanced_skill_chance from gear/talents). At 100%
    the Base never fires. Modelled by splitting the shared attack rate: Base at (1−chance), Enhanced at chance,
    so summing the two = the true blended DPS.
  • Thundercloud Surge (Empower) — a self-buff (Euphoria +35% additional Attack Speed; +25% additional damage
    at Growth Stage 4+). No direct hit; folded into the attacks (full-uptime assumption — FLAGGED).
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
    """Return the per-ability OffenseResults for a Thunder Magus. Supported abilities' DPS sums to the minion's
    true DPS (Base + Enhanced are uptime-split shares; Empower/Ultimate are NYI/0)."""
    from engine.minion_offense import (
        calculate_minion_offense, nyi_offense, spirit_magi_growth, growth_stage,
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
    if empower:
        # Thundercloud Surge Euphoria — full-uptime assumption (has a 10s cd / 6s duration in game); FLAGGED.
        _add("minion_attack_speed_additional", 0.35, "Thundercloud Surge: +35% additional Attack Speed (Euphoria)")
        if stage >= 4:
            _add("minion_dmg_additional", 0.25, "Thundercloud Surge: +25% additional damage (Growth Stage 4+)")
    if stage >= 5:
        _add("minion_dmg_additional", 0.50, "Growth Stage 5: +50% additional damage")

    results = []
    base = by_role.get("Base")
    enhanced = by_role.get("Enhanced")
    if base:
        results.append(calculate_minion_offense(buffed, base, base_stats, level, count, rate_multiplier=1.0 - enh_chance))
    if enhanced:
        results.append(calculate_minion_offense(buffed, enhanced, base_stats, level, count, rate_multiplier=enh_chance))
    if empower:
        r = nyi_offense(empower, level)
        r.nyi = ["Thundercloud Surge is an Empower buff (Euphoria +35% Attack Speed"
                 + (", +25% damage at Growth Stage 4+" if stage >= 4 else ", +25% damage once at Growth Stage 4+")
                 + ") — folded into the attacks above, no direct hit. (Full-uptime assumption.)"]
        results.append(r)
    ultimate = by_role.get("Ultimate")
    if ultimate:
        r = nyi_offense(ultimate, level)
        r.nyi = ["Lightning Surge (Ultimate) only fires in Full Bloom, which requires Iris (Growing Breeze). "
                 "NYI until Iris / Full Bloom is modelled."]
        results.append(r)
    return results
