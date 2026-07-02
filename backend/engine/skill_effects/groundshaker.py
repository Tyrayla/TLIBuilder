"""Groundshaker canvas-support mechanics + the Demolisher Charge subsystem's per-slot emissions.

Groundshaker is a Demolisher skill: it regains a single Demolisher Charge over time (base every 3s, sped by
Demolisher Charge Speed increased) and consumes it on cast to add the secondary explosion. The cast cadence and
the charge restoration/breakpoint math live in engine/offense (compute_demolisher_rate) + engine/compute (mode
detection). This module emits the SUPPORT-specific damage effects + flags that feed the demolisher dict:

  - Cripple (noble, 5th slot): the consuming cast gets +(44–46)% additional damage (demolisher_consume_dmg_additional,
    charged-cast share, applied in offense). "-90% additional damage while the fissure spreads" → a Cripple
    spread-penalty flag: offense applies −90% to the primary fissure (and, with Frequent Quake, the fissure
    ticks); the secondary EXPLOSION is EXEMPT (fires at max spread). Paralysis + the +30% consume area are NYI.
  - Epicenter (mag, 3rd slot): +(31–33)% additional damage to enemies "at the Center" → at_center_dmg_additional
    (generic full-uptime, folded into every hit). Knockback is NYI.
  - Frequent Quake (mag, 3rd slot): the max-spread fissure lasts 1.5s and, instead of exploding, deals 5 fissure
    hits (1 + 4×0.4s) → frequent_quake flag. Its +(66–68)% additional Hit Damage resolves generically.
  - Wrathful Vault (noble, 5th slot): forces manual jump-cast (handled in compute) + "75% of Movement Speed
    bonuses → additional Attack Speed (cap +60%)". The stat is emitted/surfaced; its APPLICATION is a follow-up
    (movement→AS is not yet wired into the aggregator). +(16–18)% additional damage resolves generically.
  - Collapse (noble, 5th slot): re-activates lingering max-spread fissures, amping their ticks by +(60–70)%
    (the Collapse roll). Only meaningful with Frequent-Quake persistence + auto/rhythm overlap; the step-function
    magnitude (floor(1.6/R)·0.5·roll) is computed in offense. Here we just surface the roll as collapse_roll.
"""
from __future__ import annotations
import re

from engine.models import SourceEntry
from engine.support_resolver import _progression_for_tier, _tier_value, _explicit_roll

SKILL_ID = "groundshaker"
CRIPPLE = "groundshaker_cripple_noble"
EPICENTER = "groundshaker_epicenter_magnificent"
FREQUENT_QUAKE = "groundshaker_frequent_quake_magnificent"
WRATHFUL_VAULT = "groundshaker_wrathful_vault_noble"
COLLAPSE = "groundshaker_collapse_noble"

_R = r"\(?\s*([\d.]+)\s*[–−\-]\s*([\d.]+)\s*\)?"
_CONSUME_RE = re.compile(r"\+" + _R + r"\s*%\s*additional\s+damage\s+for\s+that\s+cast", re.I)
_AT_CENTER_RE = re.compile(r"up to\s*\+" + _R + r"\s*%\s*additional\s+damage\s+to\s+enemies\s+at\s+the\s+Center", re.I)
_COLLAPSE_RE = re.compile(r"\+" + _R + r"\s*%\s*additional\s+Hit\s+Damage\s+for\s+fissures\s+activated", re.I)

# Wrathful Vault: fraction of Movement-Speed bonus applied to additional Attack Speed, and its cap.
_WV_MOVE_TO_AS = 0.75
_WV_MOVE_TO_AS_CAP = 0.60
# Frequent Quake: the max-spread fissure fires this many hits (1 immediate + 4 every 0.4s) instead of exploding.
_FQ_TICKS = 5


def _tier_line(data: dict, sup: dict) -> str:
    e = _progression_for_tier((data or {}).get("progression"), _tier_value(sup.get("level")))
    return str((e.get("values") or {}).get("name", "")) if e else ""


def _roll(sup: dict, data: dict, range_re: "re.Pattern", raw_text: str = "") -> float:
    """The tier's roll for a range line: an explicit user roll if set, else the tier-line midpoint (falling back
    to the support's raw_text when the value lives outside progression). Returns a fraction (e.g. 0.45)."""
    line = _tier_line(data, sup)
    r = _explicit_roll(sup, line)
    if r is not None:
        return r
    m = range_re.search(line) or (range_re.search(raw_text) if raw_text else None)
    return (float(m.group(1)) + float(m.group(2))) / 200.0 if m else 0.0


def _slot_sups(attached_supports, slot: int, skills_by_id) -> dict[str, tuple[dict, dict]]:
    out: dict[str, tuple[dict, dict]] = {}
    for s in (attached_supports or []):
        if s.get("slot", 1) == slot and skills_by_id and s.get("item_id") in skills_by_id:
            out[s["item_id"]] = (s, skills_by_id[s["item_id"]])
    return out


# Cripple / Epicenter / Collapse specific tier lines are bespoke → skip the generic parser (it would apply them
# to every hit ungated). Their universal +20% rank line still applies. Frequent Quake + Wrathful Vault are NOT
# guarded — FQ's "+additional Hit Damage for the supported skill" now resolves generically (support_resolver),
# and WV's "+additional damage for the supported skill" is an ordinary generic bonus; only their behavioral
# pieces (the FQ flag, WV movement→AS + Mobility tag) are emitted here.
GUARD_IDS = frozenset({CRIPPLE, EPICENTER, COLLAPSE})
CONTRIB_HOOKS: dict = {}

# Modeled-line specs (badge stat-keys + roll ranges). keys=[] = a recognized behavioral line (flag/cap, no stat).
LINE_SPECS = [
    {"support_ids": {CRIPPLE}, "phrase": re.compile(r"additional\s+damage\s+for\s+that\s+cast", re.I),
     "keys": ["demolisher_consume_dmg_additional"], "range_re": _CONSUME_RE},
    {"support_ids": {CRIPPLE}, "phrase": re.compile(r"while\s+the\s+fissure.*spreads", re.I),
     "keys": [], "range_re": None},
    {"support_ids": {CRIPPLE}, "phrase": re.compile(r"Paralysis", re.I),
     "keys": [], "range_re": None},
    {"support_ids": {EPICENTER}, "phrase": re.compile(r"enemies\s+at\s+the\s+Center", re.I),
     "keys": ["at_center_dmg_additional"], "range_re": _AT_CENTER_RE},
    {"support_ids": {EPICENTER}, "phrase": re.compile(r"knocks\s+back", re.I),
     "keys": [], "range_re": None},
    {"support_ids": {COLLAPSE}, "phrase": re.compile(r"activated\s+in\s+this\s+way", re.I),
     "keys": [], "range_re": None},
    {"support_ids": {FREQUENT_QUAKE}, "phrase": re.compile(r"instead\s+of\s+causing\s+explosions", re.I),
     "keys": [], "range_re": None},
    {"support_ids": {WRATHFUL_VAULT}, "phrase": re.compile(r"Movement\s+Speed.*additional\s+Attack\s+Speed", re.I),
     "keys": ["movement_bonus_to_attack_speed"], "range_re": None},
]


def apply_slot_effects(*, source, resolved, slot, condition_state, mod_tags, attached_supports,
                       skills_by_id, **_) -> dict:
    """Emit Groundshaker's slot-local demolisher effects + return the demolisher flag bundle for compute."""
    # Scope the Demolisher Config conditions to slots that actually run a Demolisher skill (Config auto-hide).
    source.referenced_conditions.update(
        {"groundshaker_area_selector", "demolisher_meters_moved", "demolisher_rhythm_interval"})

    sups = _slot_sups(attached_supports, slot, skills_by_id)
    flags: dict = {"fq_ticks": _FQ_TICKS}

    if CRIPPLE in sups:
        sup, data = sups[CRIPPLE]
        consume = _roll(sup, data, _CONSUME_RE, (data or {}).get("raw_text", ""))
        if consume:
            source.add_slotted("demolisher_consume_dmg_additional", consume, slot, None, SourceEntry(
                stat="demolisher_consume_dmg_additional", amount=consume, source_type="support",
                label="Groundshaker: Cripple",
                text=f"+{consume * 100:.0f}% additional damage on the consuming cast |cripple", points=1))
        flags["cripple_spread_penalty"] = True

    if EPICENTER in sups:
        sup, data = sups[EPICENTER]
        at_center = _roll(sup, data, _AT_CENTER_RE, (data or {}).get("raw_text", ""))
        if at_center:
            source.add_slotted("at_center_dmg_additional", at_center, slot, None, SourceEntry(
                stat="at_center_dmg_additional", amount=at_center, source_type="support",
                label="Groundshaker: Epicenter",
                text=f"+{at_center * 100:.0f}% additional damage at the Center |epicenter", points=1))

    if COLLAPSE in sups:
        sup, data = sups[COLLAPSE]
        flags["collapse_roll"] = _roll(sup, data, _COLLAPSE_RE, (data or {}).get("raw_text", ""))

    if FREQUENT_QUAKE in sups:
        # The +66-68% "additional Hit Damage for the supported skill" now resolves generically (support_resolver);
        # here we only set the mechanic flag (explosion → 5 fissure ticks).
        flags["frequent_quake"] = True

    if WRATHFUL_VAULT in sups:
        # Movement-Speed → additional Attack Speed (cap +60%), applied in offense's APS calc. Also makes the skill
        # a Mobility skill (flag → compute adds the "mobility" mod tag). Manual jump-cast mode is forced in compute.
        source.add_slotted("movement_bonus_to_attack_speed", _WV_MOVE_TO_AS, slot, None, SourceEntry(
            stat="movement_bonus_to_attack_speed", amount=_WV_MOVE_TO_AS, source_type="support",
            label="Groundshaker: Wrathful Vault",
            text=f"{_WV_MOVE_TO_AS * 100:.0f}% of Movement Speed → additional Attack Speed "
                 f"(cap +{_WV_MOVE_TO_AS_CAP * 100:.0f}%) |wrathful_vault", points=1))
        source.add_slotted("movement_bonus_to_attack_speed_cap", _WV_MOVE_TO_AS_CAP, slot, None, SourceEntry(
            stat="movement_bonus_to_attack_speed_cap", amount=_WV_MOVE_TO_AS_CAP, source_type="support",
            label="Groundshaker: Wrathful Vault",
            text=f"Movement→Attack Speed capped at +{_WV_MOVE_TO_AS_CAP * 100:.0f}% |wrathful_vault", points=1))
        flags["wrathful_vault"] = True

    return {"demolisher_flags": flags}
