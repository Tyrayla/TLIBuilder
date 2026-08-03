"""Focused Slash canvas-support mechanics.

  - Duel (mag):     +X% additional damage when only 1 enemy nearby — handled by the GENERIC resolver
                    (conditional line), not here.
  - Tranquility (mag): while standing still, Fervor's bonus to this skill gains an ADDITIONAL +roll per
                    0.1s stack, up to 10. Modeled at full uptime, scoped to the skill's intrinsic Fervor
                    bonus (fervor_effect_additional), NOT the global Fervor→crit.
  - Behead (noble): guaranteed Steep Strike + removes the Area tag (Area-scoped damage mods stop applying)
                    + only hits 1 enemy. Its small +X% additional damage resolves via the generic path.
  - Fervor (noble): Steep Strikes deal +(62–65)% additional damage (consumes 5 Fervor — consumption not
                    modeled; the bonus applies while Fervor Rating ≥ 5). Reuses steep_strike_additional_dmg.
"""
from __future__ import annotations
import re

from engine.models import SourceEntry
from engine.support_resolver import _progression_for_tier, _tier_value, _explicit_roll

SKILL_ID = "focused_slash"
TRANQUILITY = "focused_slash_tranquility_magnificent"
BEHEAD = "focused_slash_behead_noble"
FERVOR = "focused_slash_fervor_noble"

_RANGE = r"\(?\s*([\d.]+)\s*[–−\-]\s*([\d.]+)\s*\)?"
_FERVOR_RE = re.compile(r"deal\s*\+?" + _RANGE + r"\s*%\s*additional damage", re.I)
_TRANQ_RE = re.compile(r"additionally\s*\+?" + _RANGE + r"\s*%", re.I)
_TRANQ_MAX_STACKS = 10.0


def _mid(m: "re.Match") -> float:
    return (float(m.group(1)) + float(m.group(2))) / 2.0


def _tier_line(data: dict, sup: dict) -> str:
    e = _progression_for_tier(data.get("progression"), _tier_value(sup.get("level")))
    return str((e.get("values") or {}).get("name", "")) if e else ""


def _slot_sups(attached_supports, slot: int) -> dict[str, dict]:
    return {s.get("item_id"): s for s in (attached_supports or []) if s.get("slot", 1) == slot}


def fervor_contribution(sup: dict, data: dict) -> dict | None:
    line = _tier_line(data, sup)
    m = _FERVOR_RE.search(line)
    roll = _explicit_roll(sup, line)
    amt = roll if roll is not None else (_mid(m) / 100.0 if m else 0.0)
    if not amt:
        return None
    return {
        "stat_key": "steep_strike_additional_dmg",
        "amount": amt,
        "text": f"Steep Strike +{amt * 100:.0f}% additional damage (consumes Fervor; cost NYI) "
                f"|{sup.get('item_id')}|fervor",
        "label": data.get("name") or sup.get("item_id"),
        "condition": {"key": "fervor_rating", "op": ">=", "value": 5.0},
        "slot": sup.get("slot", 1),
    }


GUARD_IDS = frozenset({TRANQUILITY, FERVOR})   # Behead & Duel resolve their +X% via the generic path
CONTRIB_HOOKS = {FERVOR: fervor_contribution}


def apply_slot_effects(*, source, resolved, slot, condition_state, mod_tags, attached_supports,
                       skills_by_id, **_) -> dict:
    overrides: dict = {}
    sups = _slot_sups(attached_supports, slot)

    if BEHEAD in sups:
        # Guaranteed Steep Strike (offense caps steep chance at 1.0) + remove the Area tag.
        source.add_slotted("steep_strike_chance", 1.0, slot, None, SourceEntry(
            stat="steep_strike_chance", amount=1.0, source_type="support",
            label="Focused Slash: Behead", text="Guaranteed Steep Strike |behead", points=1))
        mod_tags.discard("area")
        overrides["remove_mod_tags"] = {"area"}

    if TRANQUILITY in sups:
        sup = sups[TRANQUILITY]
        data = skills_by_id.get(TRANQUILITY) if skills_by_id else None
        line = _tier_line(data, sup) if data else ""
        m = _TRANQ_RE.search(line)
        roll = _explicit_roll(sup, line)
        per = roll if roll is not None else (_mid(m) / 100.0 if m else 0.0)
        # Stacks ADD: +per per 0.1s up to 10 = +10·per, contributed as SKILL-LOCAL increased Fervor Effect
        # (adds into the same increased pool as global Fervor Effect for this skill's bonus; does NOT scale
        # global crit). Verified increased-not-additional vs the in-game recount (the +40%-Fervor-Effect
        # run made Tranquility's multiplier SHRINK, which only the increased pool can do). Full uptime = 10.
        amt = per * _TRANQ_MAX_STACKS
        if amt:
            source.add_slotted("fervor_effect_skill_inc", amt, slot, None, SourceEntry(
                stat="fervor_effect_skill_inc", amount=amt, source_type="support",
                label="Focused Slash: Tranquility",
                text=f"Fervor's bonus +{amt * 100:.0f}% (10 stacks, standing still) |tranquility",
                points=1))

    return overrides
