"""Split Shot canvas supports — Collaboration/Rapid Advance (Noble, 5th slot) + Diversion/Volley (Magnificent,
3rd slot). All four are Noble/Magnificent, so their universal "+20% additional damage" rides the rank path in
support_resolver; everything below is bespoke (the generic parser never reads a Noble/Mag support's non-rank
lines). All four are guarded so their specific tier line is skipped by the generic resolver.

  - Collaboration (Noble):  +(4.2–4.4)% additional damage for every +1 Projectile Quantity. The count is
        2 (the skill's intrinsic "+2 Projectile Quantity") + all +Projectile Quantity (Diversion/Volley/gear) —
        Tyra's call, to re-verify in-game. Computed in apply_slot_effects (needs the aggregated quantity), NOT a
        CONTRIB_HOOK.
  - Diversion (Magnificent): Projectile Quantity +5; projectiles aim at different targets (stays spread → no
        Shotgun Effect); +(11–13)% additional damage (CONTRIB_HOOK).
  - Volley (Magnificent): Projectile Quantity +2; grants Shotgun Effect (same_target_shotgun_grant → the base
        form, which "cannot hit the same enemy", now shotguns one target at the 77% falloff); (−39…−38)%
        additional damage (CONTRIB_HOOK).
  - Rapid Advance (Noble): turns Split Shot into a CHANNELED attack — installs a ChanneledSpec (max 5 stacks,
        hold-at-max) + the "+(22–23)% additional damage per +1 ADDITIONAL Max Channeled Stack (cap 15)" intrinsic;
        emits +100% additional Attack Speed and −50% additional damage; adds the "channeled" damage-mod tag. The
        channel fires at the normal WEAPON attack rate (weapon APS × attack-speed mods incl. the +100%; a stock
        1.5 base weapon APS × 2 = 3/s), hard-rounded to 30 Hz tick breakpoints (offense; see engine/tick.py).
        −30% Move Speed and the on-kill split are non-DPS/clear-only (badge-only).
"""
from __future__ import annotations
import re

from engine.models import SourceEntry
from engine.skill_resolver import ChanneledSpec, IntrinsicAdditional
from engine.support_resolver import _progression_for_tier, _tier_value, _explicit_roll

SKILL_ID = "split_shot"
COLLABORATION = "split_shot_collaboration_noble"
DIVERSION = "split_shot_diversion_magnificent"
RAPID_ADVANCE = "split_shot_rapid_advance_noble"
VOLLEY = "split_shot_volley_magnificent"
SS_SUPPORT_IDS = frozenset({COLLABORATION, DIVERSION, RAPID_ADVANCE, VOLLEY})

# Diversion / Volley +Projectile Quantity (from the data lines).
_DIVERSION_PROJ = 5.0
_VOLLEY_PROJ = 2.0
# Rapid Advance channel constants. The channel fires at the normal weapon attack rate (× the +100% below),
# 30 Hz-quantized — NOT a fixed base frequency; a stock 1.5 weapon APS × 2 = 3/s.
_CHANNEL_MAX_STACKS = 5
_CHANNEL_ATTACK_SPEED_ADDITIONAL = 1.0    # +100% additional Attack Speed
_CHANNEL_DMG_ADDITIONAL = -0.5            # −50% additional damage
_PER_ADD_MAX_STACK_CAP_STACKS = 15        # "stacking up to 15 time(s)"
_COLLAB_INTRINSIC_QUANTITY = 2.0          # the skill's own "+2 Projectile Quantity" (counted by Collaboration)

# Range like "+(11–13)" / "(-39.0–-38.0)" → signed fraction. Separator is an en-dash/minus (distinct from the
# numbers' hyphen-minus), so a leading "-" on a bound is its sign.
_RANGE = r"\(?\s*(-?[\d.]+)\s*[–−]\s*(-?[\d.]+)\s*\)?"
_ADD_DMG_RE = re.compile(_RANGE + r"\s*%\s*additional damage for the supported skill", re.I)


def _tier_line(data: dict, sup: dict) -> str:
    entry = _progression_for_tier(data.get("progression"), _tier_value(sup.get("level")))
    return str((entry.get("values") or {}).get("name", "")) if entry else ""


def _mid(m: "re.Match") -> float:
    return (float(m.group(1)) + float(m.group(2))) / 2.0


def _roll_frac(sup: dict, data: dict, rx: "re.Pattern") -> float | None:
    """The rolled fraction for a `(lo–hi)%` tier line: the user's explicit roll if set, else the tier midpoint."""
    line = _tier_line(data, sup)
    m = rx.search(line)
    if not m:
        return None
    roll = _explicit_roll(sup, line)
    return roll if roll is not None else _mid(m) / 100.0


# ── Type-A support-path contributions (Diversion / Volley: the plain specific damage roll) ──────────────
def diversion_contribution(sup: dict, data: dict) -> dict | None:
    amt = _roll_frac(sup, data, _ADD_DMG_RE)
    if amt is None:
        return None
    return {"stat_key": "dmg_additional", "amount": amt,
            "text": f"+{amt * 100:.2f}% additional damage for the supported skill |{DIVERSION}|specific",
            "label": data.get("name") or DIVERSION, "slot": sup.get("slot", 1)}


def volley_contribution(sup: dict, data: dict) -> dict | None:
    amt = _roll_frac(sup, data, _ADD_DMG_RE)
    if amt is None:
        return None
    return {"stat_key": "dmg_additional", "amount": amt,
            "text": f"{amt * 100:+.2f}% additional damage for the supported skill |{VOLLEY}|specific",
            "label": data.get("name") or VOLLEY, "slot": sup.get("slot", 1)}


GUARD_IDS = SS_SUPPORT_IDS
CONTRIB_HOOKS = {DIVERSION: diversion_contribution, VOLLEY: volley_contribution}


def _slot_sups(attached_supports, slot) -> dict[str, dict]:
    """{item_id: support} for the Split Shot canvas supports enabled on THIS slot."""
    out: dict[str, dict] = {}
    for sup in attached_supports or []:
        iid = sup.get("item_id")
        if iid in SS_SUPPORT_IDS and sup.get("slot", 1) == slot and sup.get("enabled", True):
            out[iid] = sup
    return out


# ── Type-B slot-local emissions (projectile quantity / shotgun grant / channel transform) ──────────────
def apply_slot_effects(*, source, resolved, slot, condition_state, mod_tags, attached_supports,
                       skills_by_id, **_) -> dict:
    sups = _slot_sups(attached_supports, slot)
    if not sups:
        return {}
    overrides: dict = {}

    # Diversion / Volley: +Projectile Quantity (slot-local → offense's n_proj picks it up). Volley also grants
    # Shotgun Effect so the base "cannot hit the same enemy" form shotguns one target.
    if DIVERSION in sups:
        _div_name = (skills_by_id.get(DIVERSION) or {}).get("name") or "Split Shot: Diversion"
        source.add_slotted("projectile_quantity_flat", _DIVERSION_PROJ, slot, None, SourceEntry(
            stat="projectile_quantity_flat", amount=_DIVERSION_PROJ, source_type="support",
            label="Split Shot: Diversion", source_name=_div_name,
            text=f"Projectile Quantity of the supported skill +{int(_DIVERSION_PROJ)} |{DIVERSION}|proj", points=1))
    if VOLLEY in sups:
        _vol_name = (skills_by_id.get(VOLLEY) or {}).get("name") or "Split Shot: Volley"
        source.add_slotted("projectile_quantity_flat", _VOLLEY_PROJ, slot, None, SourceEntry(
            stat="projectile_quantity_flat", amount=_VOLLEY_PROJ, source_type="support",
            label="Split Shot: Volley", source_name=_vol_name,
            text=f"Projectile Quantity of the supported skill +{int(_VOLLEY_PROJ)} |{VOLLEY}|proj", points=1))
        source.add_slotted("same_target_shotgun_grant", 1.0, slot, None, SourceEntry(
            stat="same_target_shotgun_grant", amount=1.0, source_type="support",
            label="Split Shot: Volley", source_name=_vol_name,
            text=f"The supported skill has Shotgun Effect |{VOLLEY}|shotgun", points=1))

    # Collaboration: +roll% additional damage per +1 Projectile Quantity. Count = the skill's intrinsic +2 plus
    # ALL +Projectile Quantity (gear/global read from source.total, + Diversion/Volley since their slot emissions
    # aren't folded into source._entries yet at this point). Emitted as one slot-local additional factor.
    if COLLABORATION in sups:
        data = skills_by_id.get(COLLABORATION) or {}
        per = _roll_frac(sups[COLLABORATION], data, _ADD_DMG_RE)
        if per:
            qty = source.total("projectile_quantity_flat")            # gear/global (+quantity)
            if DIVERSION in sups:
                qty += _DIVERSION_PROJ
            if VOLLEY in sups:
                qty += _VOLLEY_PROJ
            count = _COLLAB_INTRINSIC_QUANTITY + qty
            amt = per * count
            if amt:
                source.add_slotted("dmg_additional", amt, slot, None, SourceEntry(
                    stat="dmg_additional", amount=amt, source_type="support", label="Split Shot: Collaboration",
                    source_name=data.get("name") or "Split Shot: Collaboration",
                    text=f"+{amt * 100:.2f}% additional damage ({per * 100:.2f}% × {count:.0f} Projectile Quantity)"
                         f" |{COLLABORATION}|collab", points=1))

    # Rapid Advance: transform Split Shot into a channeled attack + emit its stat lines. Mutate the (per-slot)
    # resolved once (idempotency-guarded on channeled).
    if RAPID_ADVANCE in sups:
        if resolved.channeled is None:
            resolved.channeled = ChanneledSpec(
                max_stacks=_CHANNEL_MAX_STACKS, min_stacks=0, behavior="refresh")
            # "channeled" so Channeled-scoped damage mods apply and the skill reports as channeled.
            if "channeled" not in [t.lower() for t in resolved.tags]:
                resolved.tags = list(resolved.tags) + ["Channeled"]
            # +(22–23)% additional damage per +1 ADDITIONAL Max Channeled Stack (base 5 give none), cap 15 stacks.
            data = skills_by_id.get(RAPID_ADVANCE) or {}
            per = _roll_frac(sups[RAPID_ADVANCE], data, _ADD_DMG_RE) or 0.225
            resolved.intrinsic_additional = list(resolved.intrinsic_additional) + [IntrinsicAdditional(
                per=per, rating_key="max_channeled_stacks_flat", rating_source="stat", per_n=1.0,
                cap=per * _PER_ADD_MAX_STACK_CAP_STACKS)]
        _ra_name = (skills_by_id.get(RAPID_ADVANCE) or {}).get("name") or "Split Shot: Rapid Advance"
        source.add_slotted("attack_speed_additional", _CHANNEL_ATTACK_SPEED_ADDITIONAL, slot, None, SourceEntry(
            stat="attack_speed_additional", amount=_CHANNEL_ATTACK_SPEED_ADDITIONAL, source_type="support",
            label="Split Shot: Rapid Advance", source_name=_ra_name,
            text=f"+{_CHANNEL_ATTACK_SPEED_ADDITIONAL * 100:.0f}% additional Attack Speed for the supported skill"
                 f" |{RAPID_ADVANCE}|as", points=1))
        source.add_slotted("dmg_additional", _CHANNEL_DMG_ADDITIONAL, slot, None, SourceEntry(
            stat="dmg_additional", amount=_CHANNEL_DMG_ADDITIONAL, source_type="support",
            label="Split Shot: Rapid Advance", source_name=_ra_name,
            text=f"{_CHANNEL_DMG_ADDITIONAL * 100:.0f}% additional damage for the supported skill"
                 f" |{RAPID_ADVANCE}|dmg", points=1))
        overrides["add_mod_tags"] = {"channeled"}

    return overrides


# ── Modeled-line specs (coverage badges + roll sliders) ────────────────────────
LINE_SPECS = [
    {"support_ids": {COLLABORATION}, "phrase": _ADD_DMG_RE,
     "keys": ["dmg_additional"], "range_re": _ADD_DMG_RE},
    {"support_ids": {DIVERSION}, "phrase": re.compile(r"Projectile Quantity of the supported skill", re.I),
     "keys": ["projectile_quantity_flat"], "range_re": None},
    {"support_ids": {DIVERSION}, "phrase": re.compile(r"aim at different targets", re.I),
     "keys": [], "range_re": None},
    {"support_ids": {DIVERSION}, "phrase": _ADD_DMG_RE,
     "keys": ["dmg_additional"], "range_re": _ADD_DMG_RE},
    {"support_ids": {VOLLEY}, "phrase": re.compile(r"Projectile Quantity of the supported skill", re.I),
     "keys": ["projectile_quantity_flat"], "range_re": None},
    {"support_ids": {VOLLEY}, "phrase": re.compile(r"fired as a volley", re.I),
     "keys": [], "range_re": None},
    {"support_ids": {VOLLEY}, "phrase": re.compile(r"has Shotgun Effect", re.I),
     "keys": ["same_target_shotgun_grant"], "range_re": None},
    {"support_ids": {VOLLEY}, "phrase": _ADD_DMG_RE,
     "keys": ["dmg_additional"], "range_re": _ADD_DMG_RE},
    {"support_ids": {RAPID_ADVANCE}, "phrase": re.compile(r"becomes a Channeled Skill", re.I),
     "keys": [], "range_re": None},
    {"support_ids": {RAPID_ADVANCE}, "phrase": re.compile(r"additional Attack Speed for the supported skill", re.I),
     "keys": ["attack_speed_additional"], "range_re": None},
    {"support_ids": {RAPID_ADVANCE}, "phrase": re.compile(r"Movement Speed while channeling", re.I),
     "keys": [], "range_re": None},
    {"support_ids": {RAPID_ADVANCE}, "phrase": re.compile(r"for every \+1 to additional Max Channeled Stack", re.I),
     "keys": ["dmg_additional"], "range_re": _ADD_DMG_RE},
]
