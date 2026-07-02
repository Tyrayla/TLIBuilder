"""Howling Gale canvas-support mechanics.

Four bound supports, all carrying the universal "+20% additional damage for the supported skill" rank line
(handled generically by support_resolver's rank table — NOT here). Their SPECIFIC lines are bespoke:

  - Eye of the Gale (Noble, 5th):  GLOBAL +(20-22)% additional Attack & Cast Speed + 20% Projectile Speed
        while within the Gale. Tyra-confirmed these buff the WHOLE character (not just the Gale), so they are
        emitted globally (add_with_source), gated on the `within_gale` condition (default ON). Cast Speed also
        feeds the Gale's strike rate (offense's channeled attack_frequency × cast-speed mult). Gale-follows is
        informational. NOTE: a global emit from one slot's hook reaches the Gale's own slot (it materializes
        after this runs) and any slot computed later; slots computed earlier in the loop won't see it. Fine for
        single-skill verification — flagged for a future global pre-pass if multi-skill builds need it.
  - Furious Sweep (Noble, 5th):    +(7.2-7.6)% additional Gale Attack Frequency PER channeled stack (replacing
        the per-stack Skill Area). At REFRESH the channel holds at max, so this = per_stack × Max Channeled
        Stacks. Emitted SLOT-LOCAL as `channeled_attack_frequency_additional`; offense multiplies the Gale rate.
  - Headwind (Magnificent, 3rd):   +50% Knockback Chance + (22-24)% additional damage taken by enemies recently
        knocked back. This support IS the knockback source, so `preseed` forces `enemy_knocked_back` ON when it's
        socketed; the damage-taken is a GLOBAL enemy-vulnerability pool (`knockback_dmg_taken`) gated on that
        condition. Knockback Chance is surfaced (`knockback_chance`, non-DPS — future stats-screen redo). Applies
        vs the boss-style target (knockback-able per Help DB Monster Immunity; Supreme Showdown bosses are immune,
        handled when the target-type selector becomes functional).
  - Rapid Sweep (Magnificent, 3rd): +(3.4-3.7)% additional damage per 1 s the Gale lasts, cap 10 stacks. At
        sustained REFRESH steady state assume the cap. A type-A `dmg_additional` gated per-`rapid_sweep_stacks`.

All values come from the support's equipped tier (progression[tier], default tier 1), honoring an explicit roll.
"""
from __future__ import annotations
import re

from engine.models import SourceEntry
from engine.support_resolver import _progression_for_tier, _tier_value, _explicit_roll

SKILL_ID = "howling_gale"

EYE      = "howling_gale_eye_of_the_gale_noble"
FURIOUS  = "howling_gale_furious_sweep_noble"
HEADWIND = "howling_gale_headwind_magnificent"
RAPID    = "howling_gale_rapid_sweep_magnificent"
HG_SUPPORT_IDS = frozenset({EYE, FURIOUS, HEADWIND, RAPID})

# Range like "(20–22)" / "20-22" (en-dash, minus, or hyphen).
_RANGE = r"\(?\s*([\d.]+)\s*[–−\-]\s*([\d.]+)\s*\)?"
_EYE_ATKCAST_RE = re.compile(_RANGE + r"\s*%\s*additional Attack and Cast Speed", re.I)
_EYE_PROJ_RE    = re.compile(r"\+?\s*([\d.]+)\s*%\s*Projectile Speed", re.I)
_FURIOUS_RE     = re.compile(_RANGE + r"\s*%\s*additional Attack Frequency", re.I)
_HEADWIND_DMG_RE = re.compile(_RANGE + r"\s*%\s*additional damage taken", re.I)
_HEADWIND_KB_RE  = re.compile(r"\+?\s*([\d.]+)\s*%\s*Knockback Chance", re.I)
_RAPID_RE       = re.compile(_RANGE + r"\s*%\s*additional damage for every 1\s*s", re.I)


def _mid(m: "re.Match") -> float:
    return (float(m.group(1)) + float(m.group(2))) / 2.0


def _tier_line(data: dict, sup: dict) -> str:
    entry = _progression_for_tier(data.get("progression"), _tier_value(sup.get("level")))
    return str((entry.get("values") or {}).get("name", "")) if entry else ""


def _frac_from(sup: dict, line: str, rex: "re.Pattern") -> float | None:
    """The rolled fraction for a `(lo-hi)%` line: explicit user roll if set, else the tier midpoint."""
    roll = _explicit_roll(sup, line)
    if roll is not None:
        return roll
    m = rex.search(line)
    return _mid(m) / 100.0 if m else None


# ── Rapid Sweep: type-A support-path contribution (slot-local dmg_additional) ──────────────────
def rapid_sweep_contribution(sup: dict, data: dict) -> dict | None:
    """+X% additional damage per 1 s the Gale lasts, capped at 10 stacks. Modeled as a per-stack additional
    gated on `rapid_sweep_stacks` (default 10 = the sustained-REFRESH cap). The universal +20% rides the rank
    path separately."""
    line = _tier_line(data, sup)
    per = _frac_from(sup, line, _RAPID_RE)
    if per is None:
        return None
    return {
        "stat_key": "dmg_additional",
        "amount": per,
        "text": f"+{per * 100:.2f}% additional damage per 1 s the Gale lasts (cap 10) |{sup.get('item_id')}|rapid_sweep",
        "label": data.get("name") or sup.get("item_id"),
        "condition": {"key": "rapid_sweep_stacks", "op": "per", "divisor": 1.0, "cap": per * 10.0},
        "slot": sup.get("slot", 1),
    }


# ── Modeled-line specs (badge stat-keys + roll ranges) ────────────────────────
# One spec per bespoke clause: `phrase` recognizes the rendered/raw clause → its engine stat key(s) (so the
# coverage badge shows Consumed instead of NYI); `range_re` (capturing the (lo–hi) roll group on the FULL tier
# line) drives the per-line roll slider — None = a fixed value (no slider). Consumed by the skill_effects
# registry (engine.skill_effects.resolve_line_keys / modeled_rolls). Single source of truth for these lines.
LINE_SPECS = [
    {"support_ids": {EYE}, "phrase": re.compile(r"additional Attack and Cast Speed", re.I),
     "keys": ["attack_speed_additional", "cast_speed_additional"], "range_re": _EYE_ATKCAST_RE},
    {"support_ids": {EYE}, "phrase": re.compile(r"Projectile Speed", re.I),
     "keys": ["projectile_speed_inc"], "range_re": None},
    {"support_ids": {FURIOUS}, "phrase": re.compile(r"additional Attack Frequency", re.I),
     "keys": ["channeled_attack_frequency_additional"], "range_re": _FURIOUS_RE},
    {"support_ids": {HEADWIND}, "phrase": re.compile(r"additional damage taken", re.I),
     "keys": ["knockback_dmg_taken"], "range_re": _HEADWIND_DMG_RE},
    {"support_ids": {HEADWIND}, "phrase": re.compile(r"Knockback Chance", re.I),
     "keys": ["knockback_chance"], "range_re": None},
    {"support_ids": {RAPID}, "phrase": re.compile(r"additional damage for every 1\s*s", re.I),
     "keys": ["dmg_additional"], "range_re": _RAPID_RE},
]


# ── skill_effects registry interface ──────────────────────────────────────────
GUARD_IDS = HG_SUPPORT_IDS                          # specific lines handled here, not the generic parser
CONTRIB_HOOKS = {RAPID: rapid_sweep_contribution}   # type-A support-path contribution


def _slot_supports(attached_supports, slot) -> dict[str, dict]:
    """{item_id: support} for the Howling Gale canvas supports enabled on THIS slot."""
    out: dict[str, dict] = {}
    for sup in attached_supports or []:
        iid = sup.get("item_id")
        if iid in HG_SUPPORT_IDS and sup.get("slot", 1) == slot and sup.get("enabled", True):
            out[iid] = sup
    return out


def apply_slot_effects(*, source, resolved, slot, condition_state, mod_tags, attached_supports,
                       skills_by_id, **_) -> dict:
    """Eye of the Gale (global character buffs), Furious Sweep (Gale attack-frequency-additional, slot-local),
    and Headwind (global knockback enemy-vuln + surfaced knockback chance). No offense overrides."""
    sups = _slot_supports(attached_supports, slot)

    # Eye of the Gale — GLOBAL: additional Attack & Cast Speed + Projectile Speed, gated on `within_gale`.
    sup = sups.get(EYE)
    if sup and condition_state.get("within_gale", True):
        data = skills_by_id.get(EYE) or {}
        line = _tier_line(data, sup)
        atkcast = _frac_from(sup, line, _EYE_ATKCAST_RE)
        if atkcast:
            for stat in ("attack_speed_additional", "cast_speed_additional"):
                source.add_with_source(stat, atkcast, SourceEntry(
                    stat=stat, amount=atkcast, source_type="support",
                    label="Howling Gale: Eye of the Gale",
                    text=f"+{atkcast * 100:.2f}% additional {'Attack' if 'attack' in stat else 'Cast'} Speed while within the Gale |{EYE}|eye",
                    points=1))
        pm = _EYE_PROJ_RE.search(line)
        if pm:
            proj = float(pm.group(1)) / 100.0
            source.add_with_source("projectile_speed_inc", proj, SourceEntry(
                stat="projectile_speed_inc", amount=proj, source_type="support",
                label="Howling Gale: Eye of the Gale",
                text=f"+{proj * 100:.0f}% Projectile Speed while within the Gale |{EYE}|eye",
                points=1))

    # Furious Sweep — SLOT-LOCAL: per-stack additional Gale Attack Frequency × current channeled stacks (REFRESH
    # holds at max = base Max Channeled Stacks + flat). offense multiplies the Gale's strike rate by (1 + this).
    sup = sups.get(FURIOUS)
    if sup:
        data = skills_by_id.get(FURIOUS) or {}
        line = _tier_line(data, sup)
        per_stack = _frac_from(sup, line, _FURIOUS_RE)
        if per_stack:
            base_max = int(getattr(resolved.channeled, "max_stacks", 0)) if resolved.channeled else 0
            stacks = max(1, base_max + int(source.total("max_channeled_stacks_flat")))
            amt = per_stack * stacks
            source.add_slotted("channeled_attack_frequency_additional", amt, slot, None, SourceEntry(
                stat="channeled_attack_frequency_additional", amount=amt, source_type="support",
                label="Howling Gale: Furious Sweep", source_name=data.get("name", "Furious Sweep"),
                text=f"+{per_stack * 100:.2f}% additional Gale Attack Frequency per channeled stack ×{stacks} |{FURIOUS}|furious",
                points=1))

    # Headwind — GLOBAL enemy-vuln (gated on enemy_knocked_back, which preseed forces ON when socketed) +
    # surfaced Knockback Chance (non-DPS).
    sup = sups.get(HEADWIND)
    if sup:
        data = skills_by_id.get(HEADWIND) or {}
        line = _tier_line(data, sup)
        if condition_state.get("enemy_knocked_back"):
            dmg = _frac_from(sup, line, _HEADWIND_DMG_RE)
            if dmg:
                source.add_with_source("knockback_dmg_taken", dmg, SourceEntry(
                    stat="knockback_dmg_taken", amount=dmg, source_type="support",
                    label="Howling Gale: Headwind",
                    text=f"Knocked-back enemies take +{dmg * 100:.2f}% additional damage |{HEADWIND}|headwind",
                    points=1))
        km = _HEADWIND_KB_RE.search(line)
        if km:
            chance = float(km.group(1)) / 100.0
            source.add_with_source("knockback_chance", chance, SourceEntry(
                stat="knockback_chance", amount=chance, source_type="support",
                label="Howling Gale: Headwind",
                text=f"+{chance * 100:.0f}% Knockback Chance |{HEADWIND}|headwind",
                points=1))
    return {}


def preseed(*, slot, condition_state, attached_supports, skills_by_id, **_) -> None:
    """Seed conditions before aggregation:
      - Headwind is the knockback source → force `enemy_knocked_back` ON when socketed (so the 'vs knocked back'
        enemy-vuln emits). For now the boss target is knockback-able; immune target tiers will suppress this once
        the target-type selector is functional.
      - Rapid Sweep ramps to a 10-stack cap at sustained REFRESH steady state → default `rapid_sweep_stacks` to
        the cap when socketed and the user hasn't set it (mirrors Berserking Blade defaulting buff stacks to max)."""
    sups = _slot_supports(attached_supports, slot)
    if sups.get(HEADWIND):
        condition_state["enemy_knocked_back"] = True
    if sups.get(RAPID):
        condition_state.setdefault("rapid_sweep_stacks", 10)
