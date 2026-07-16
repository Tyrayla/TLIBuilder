"""Moon Strike canvas-support mechanics.

  - Rainbow (mag):     +1% Steep Strike chance per 100 Max Mana, capped. Reads the derived max_mana stat.
  - Lunar Ring (mag):  a "circular attack" proc on Steep Strike, chance scaling with Max Mana. The circular
                       form is just a Steep Strike that hits around you — DPS-NEUTRAL for single target — so
                       we only TRACK the proc chance (moon_strike_circular_chance) for later surfacing.
  - Lunar Eclipse (noble): WIRED — seals 10% Max Mana (removes the skill's Mana cost) and grants +1% additional
                       damage per 100 Mana sealed, up to a per-rank cap. The mana-sealing/reservation system
                       (engine/utility.py `apply_reservation`) detects this support's "mana sealed" + "up to"
                       description, computes the cap via `_seal_dmg_cap`, and emits the `dmg_additional` bonus
                       (utility.py:462-470). Guarded here only so the generic tier-line parser doesn't ALSO try
                       to read its progression line (which would double-count); the universal rank line still
                       applies on top, unaffected by the guard.
  - Wax and Wane (noble):  DEFERRED — Spell Burst interaction (Spell Burst is itself NYI in the engine).
"""
from __future__ import annotations
import math
import re

from engine.models import SourceEntry
from engine.support_resolver import _progression_for_tier, _tier_value, _explicit_roll

SKILL_ID = "moon_strike"
LUNAR_RING = "moon_strike_lunar_ring_magnificent"
RAINBOW = "moon_strike_rainbow_magnificent"
LUNAR_ECLIPSE = "moon_strike_lunar_eclipse_noble"
WAX_AND_WANE = "moon_strike_wax_and_wane_noble"

_RANGE = r"\(?\s*([\d.]+)\s*[–−\-]\s*([\d.]+)\s*\)?"
_CAP_RE = re.compile(r"up to\s*\+?" + _RANGE + r"\s*%", re.I)
_RING_BASE_RE = re.compile(r"there is a\s*" + _RANGE + r"\s*%\s*chance", re.I)


def _mid(m: "re.Match") -> float:
    return (float(m.group(1)) + float(m.group(2))) / 2.0


def _tier_line(data: dict, sup: dict) -> str:
    e = _progression_for_tier(data.get("progression"), _tier_value(sup.get("level")))
    return str((e.get("values") or {}).get("name", "")) if e else ""


def _slot_sups(attached_supports, slot: int, skills_by_id) -> dict[str, tuple[dict, dict]]:
    out: dict[str, tuple[dict, dict]] = {}
    for s in (attached_supports or []):
        if s.get("slot", 1) == slot and skills_by_id and s.get("item_id") in skills_by_id:
            out[s["item_id"]] = (s, skills_by_id[s["item_id"]])
    return out


# All four specific lines are bespoke, handled elsewhere (apply_slot_effects below, or — Lunar Eclipse —
# engine/utility.py's mana-sealing pass) or still deferred (Wax and Wane) → keep them out of the generic
# parser (the universal rank line still applies to each regardless).
GUARD_IDS = frozenset({LUNAR_RING, RAINBOW, LUNAR_ECLIPSE, WAX_AND_WANE})
CONTRIB_HOOKS: dict = {}


def apply_slot_effects(*, source, resolved, slot, condition_state, mod_tags, attached_supports,
                       skills_by_id, **_) -> dict:
    sups = _slot_sups(attached_supports, slot, skills_by_id)
    if not (RAINBOW in sups or LUNAR_RING in sups):
        return {}
    max_mana = source.materialize_for_skill(mod_tags, slot).total("max_mana")

    if RAINBOW in sups:
        sup, data = sups[RAINBOW]
        line = _tier_line(data, sup)
        cm = _CAP_RE.search(line)
        roll = _explicit_roll(sup, line)
        cap = roll if roll is not None else (_mid(cm) / 100.0 if cm else 0.0)
        chance = min(math.floor(max_mana / 100.0) * 0.01, cap)
        if chance:
            source.add_slotted("steep_strike_chance", chance, slot, None, SourceEntry(
                stat="steep_strike_chance", amount=chance, source_type="support",
                label="Moon Strike: Rainbow",
                text=f"+{chance * 100:.0f}% Steep Strike chance (1%/100 Max Mana) |rainbow", points=1))

    if LUNAR_RING in sups:
        sup, data = sups[LUNAR_RING]
        line = _tier_line(data, sup)
        bm = _RING_BASE_RE.search(line)
        cm = _CAP_RE.search(line)
        base = _mid(bm) / 100.0 if bm else 0.0
        add_cap = _mid(cm) / 100.0 if cm else 0.0
        chance = min(base + math.floor(max_mana / 150.0) * 0.01, base + add_cap)
        if chance:
            source.add_slotted("moon_strike_circular_chance", chance, slot, None, SourceEntry(
                stat="moon_strike_circular_chance", amount=chance, source_type="support",
                label="Moon Strike: Lunar Ring",
                text=f"{chance * 100:.0f}% circular-attack chance on Steep Strike (tracked; DPS-neutral) "
                     f"|lunar_ring", points=1))

    return {}
