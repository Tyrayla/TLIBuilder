"""Chromatic Shot canvas supports — Lightchaser (magnificent) + Splendor (noble).

Lightchaser: +30% **additional** Projectile Speed (ADDITIONAL — so Gale's projectile-speed→projectile-damage, which
reads INCREASED only, ignores it), +25% main-attribute damage ratio (main_stat_dmg_bonus_inc → 0.5%/pt becomes
0.625%/pt), homing so ALL projectiles land (sets chromatic_shots_on_target to the full count), and a tunable
+(1–4)% additional damage roll.
Splendor: fixed Cold→Fire→Lightning rotation (DPS = the same expected average; informational), auto-inflicts
Frostbite / Numbed / Ignite (sets + surfaces those enemy conditions; the Ignite is a 0-damage 100%-chance apply),
and a tunable +(33–37)% additional HIT damage vs enemies that have all three ailments.
The universal +20% additional damage (Magnificent/Noble rank line) is emitted by support_resolver — not re-modeled
here. The shots-on-target shotgun count is consumed in offense (compulsory path).
"""
from __future__ import annotations
import re

from engine.models import SourceEntry
from engine.support_resolver import _progression_for_tier, _tier_value, _explicit_roll

SKILL_ID = "chromatic_shot"
LIGHTCHASER = "chromatic_shot_lightchaser_magnificent"
SPLENDOR = "chromatic_shot_splendor_noble"
CS_SUPPORT_IDS = frozenset({LIGHTCHASER, SPLENDOR})

_PROJ_SPEED_ADDITIONAL = 0.30
_MAIN_STAT_INC = 0.25
_AILMENTS = ("enemy_frostbitten", "enemy_numbed", "enemy_ignited")
_ALL_HIT = 999  # Lightchaser homing → all fired projectiles land (offense caps this at the projectile count)

# Lightchaser's additional-damage roll is SIGNED and tier-dependent: tier 2 = (-6–-4)%, tier 1 = (-3–-1)%,
# tier 0 = +(1–4)%. So both bounds can carry a leading minus — capture the sign (the separator is an en-dash,
# distinct from the numbers' hyphen-minus, so this stays unambiguous).
_RANGE = r"\(?\s*(-?[\d.]+)\s*[–−]\s*(-?[\d.]+)\s*\)?"
_LC_ROLL_RE = re.compile(_RANGE + r"\s*%\s*additional\s+damage", re.I)
_SP_ROLL_RE = re.compile(_RANGE + r"\s*%\s*additional\s+Hit\s+Damage", re.I)


def _mid(m: "re.Match") -> float:
    return (float(m.group(1)) + float(m.group(2))) / 2.0


def _tier_line(data: dict, sup: dict) -> str:
    entry = _progression_for_tier(data.get("progression"), _tier_value(sup.get("level")))
    return str((entry.get("values") or {}).get("name", "")) if entry else ""


def _roll_frac(sup: dict, data: dict, rx: "re.Pattern") -> float | None:
    line = _tier_line(data, sup)
    m = rx.search(line)
    if not m:
        return None
    roll = _explicit_roll(sup, line)
    return roll if roll is not None else _mid(m) / 100.0


# ── Type-A contributions: the tunable damage rolls (the universal +20% is auto via support_resolver) ──
def lightchaser_contribution(sup: dict, data: dict) -> dict | None:
    amt = _roll_frac(sup, data, _LC_ROLL_RE)
    if amt is None:
        return None
    return {"stat_key": "dmg_additional", "amount": amt,
            "text": f"+{amt * 100:.2f}% additional damage |{LIGHTCHASER}|lightchaser_roll",
            "label": data.get("name") or LIGHTCHASER, "slot": sup.get("slot", 1)}


def splendor_contribution(sup: dict, data: dict) -> dict | None:
    amt = _roll_frac(sup, data, _SP_ROLL_RE)
    if amt is None:
        return None
    return {"stat_key": "hit_dmg_additional", "amount": amt,
            "text": f"+{amt * 100:.2f}% additional Hit Damage vs enemies with Frostbite + Numbed + Ignite "
                    f"|{SPLENDOR}|splendor_roll",
            "label": data.get("name") or SPLENDOR,
            "condition": {"and": list(_AILMENTS)}, "slot": sup.get("slot", 1)}


GUARD_IDS = CS_SUPPORT_IDS
CONTRIB_HOOKS = {LIGHTCHASER: lightchaser_contribution, SPLENDOR: splendor_contribution}


def _slot_support_ids(attached_supports, slot) -> set:
    return {s.get("item_id") for s in (attached_supports or [])
            if s.get("slot", 1) == slot and s.get("enabled", True)}


# ── Type-B slot-local emissions (proj speed / main-stat ratio / shots-on-target) ──
def apply_slot_effects(*, source, resolved, slot, condition_state, mod_tags, attached_supports, skills_by_id, **_) -> dict:
    ids = _slot_support_ids(attached_supports, slot)
    # Shots on target (the shotgun hit count offense uses): surface the condition; emit its value. By default ALL
    # fired projectiles land (large value → offense caps it at the actual projectile count); the user can override
    # downward. Lightchaser homing always forces all to land.
    source.referenced_conditions.add("chromatic_shots_on_target")
    raw = condition_state.get("chromatic_shots_on_target")
    shots = float(raw) if raw is not None else float(_ALL_HIT)
    if LIGHTCHASER in ids:
        shots = float(_ALL_HIT)
    source.add_with_source("chromatic_shots_on_target_flat", shots, SourceEntry(
        stat="chromatic_shots_on_target_flat", amount=shots, source_type="skill", label="Chromatic Shot",
        text="shots that hit the target (shotgun count) |chromatic_shot|shots", points=1))

    if LIGHTCHASER in ids:
        source.add_with_source("projectile_speed_additional", _PROJ_SPEED_ADDITIONAL, SourceEntry(
            stat="projectile_speed_additional", amount=_PROJ_SPEED_ADDITIONAL, source_type="support",
            label="Chromatic Shot: Lightchaser",
            text=f"+{_PROJ_SPEED_ADDITIONAL * 100:.0f}% additional Projectile Speed |{LIGHTCHASER}|lightchaser",
            points=1))
        source.add_with_source("main_stat_dmg_bonus_inc", _MAIN_STAT_INC, SourceEntry(
            stat="main_stat_dmg_bonus_inc", amount=_MAIN_STAT_INC, source_type="support",
            label="Chromatic Shot: Lightchaser",
            text=f"+{_MAIN_STAT_INC * 100:.0f}% additional damage ratio from main attribute |{LIGHTCHASER}|lightchaser",
            points=1))

    if SPLENDOR in ids:
        for a in _AILMENTS:
            source.referenced_conditions.add(a)
    return {}


# ── Type-C preseed: Splendor auto-inflicts the three Elemental Ailments ──
_SRC = "Chromatic Shot: Splendor"


def preseed(*, slot, condition_state, attached_supports, skills_by_id,
            auto_sources=None, auto_values=None, manual_keys=None, **_) -> None:
    if SPLENDOR not in _slot_support_ids(attached_supports, slot):
        return
    manual = manual_keys or set()

    def _record(key, value):
        if auto_sources is not None:
            auto_sources[key] = _SRC
        if auto_values is not None:
            auto_values[key] = value

    # Numbed: inflicting it applies ≥1 stack — UNLESS the user explicitly set the stack count (0 = opt out of
    # Numbed entirely). The auto intent (1) is recorded regardless so the Config field can fall back to it.
    if "numbed_stacks" not in manual and float(condition_state.get("numbed_stacks") or 0.0) < 1.0:
        condition_state["numbed_stacks"] = 1.0
    _record("numbed_stacks", 1.0)
    numbed_on = float(condition_state.get("numbed_stacks") or 0.0) >= 1.0

    # Frostbite + Ignite are always inflicted; Numbed only when there's ≥1 stack (so a user-set 0 turns it off,
    # which then drops Splendor's all-three-ailment Hit Damage gate).
    for a, on in (("enemy_frostbitten", True), ("enemy_ignited", True), ("enemy_numbed", numbed_on)):
        _record(a, on)
        if a not in manual:
            condition_state[a] = bool(on)


# ── Coverage badges + roll sliders ──
LINE_SPECS = [
    {"support_ids": {LIGHTCHASER}, "phrase": re.compile(r"additional Projectile Speed", re.I),
     "keys": ["projectile_speed_additional"], "range_re": None},
    {"support_ids": {LIGHTCHASER}, "phrase": re.compile(r"damage ratio.*main attribute", re.I),
     "keys": ["main_stat_dmg_bonus_inc"], "range_re": None},
    {"support_ids": {LIGHTCHASER}, "phrase": re.compile(r"tracking ability", re.I),
     "keys": [], "range_re": None},
    {"support_ids": {LIGHTCHASER}, "phrase": _LC_ROLL_RE,
     "keys": ["dmg_additional"], "range_re": _LC_ROLL_RE},
    {"support_ids": {SPLENDOR}, "phrase": re.compile(r"fixed order", re.I),
     "keys": [], "range_re": None},
    {"support_ids": {SPLENDOR}, "phrase": re.compile(r"inflicts Frostbite", re.I),
     "keys": [], "range_re": None},
    {"support_ids": {SPLENDOR}, "phrase": _SP_ROLL_RE,
     "keys": ["hit_dmg_additional"], "range_re": _SP_ROLL_RE},
]
