"""Chromatic Shot canvas supports — Lightchaser (magnificent) + Splendor (noble) + the SS13 "Condensed"
elemental Noble quartet (Fire/Cold/Lightning/Erosion).

Lightchaser: +30% **additional** Projectile Speed (ADDITIONAL — so Gale's projectile-speed→projectile-damage, which
reads INCREASED only, ignores it), +25% main-attribute damage ratio (main_stat_dmg_bonus_inc → 0.5%/pt becomes
0.625%/pt), homing so ALL projectiles land (sets chromatic_shots_on_target to the full count), and a tunable
+(1–4)% additional damage roll.
Splendor: fixed Cold→Fire→Lightning rotation (DPS = the same expected average; informational), auto-inflicts
Frostbite / Numbed / Ignite (sets + surfaces those enemy conditions; the Ignite is a 0-damage 100%-chance apply),
and a tunable +(33–37)% additional HIT damage vs enemies that have all three ailments.
Condensed (Fire/Cold/Lightning/Erosion, SS13): replaces SS13's deleted forced-elemental-conversion line on the
skill itself (see engine.skill_resolver._resolve_chromatic_shot) with player choice — each Condensed support
converts 100% of the supported skill's Physical Damage to its element (reuses the general
`{type}_convert_to_{type}` conversion pool — engine.offense._conversion_fracs — the SAME cascade a gear/talent
conversion line drives, per the 2026-06-11 conversion system), grants the skill that element's Tag (so
element-scoped mods apply — routed through the existing `add_mod_tags` override, per Split Shot's precedent), and
inflicts an ailment: Fire→Ignite / Erosion→Wilt carry a real "+40% chance" roll + "Adds 1-1 Base X Damage" (both
emitted onto the SAME stat keys a gear/talent line of that wording would use — ignite_dmg_flat_min/max,
ignite_chance, etc.; the base-damage pool has no DoT-tick consumer anywhere in the engine yet, so it's tracked,
not silently dropped, and does not move total_dps — a pre-existing gap, not special-cased here); Cold→Frostbite /
Lightning→Numbed are DETERMINISTIC ("Inflicts X when the supported skill deals Hit Y Damage" — no chance roll,
no base-damage line, since Frostbite/Numbed aren't base-damage-scaled ailments). All 4 auto-set their enemy
condition True (preseed, same floor-style auto-derive `ailment_inflict.py`/`map_autoderive_line` use everywhere
else in the engine for a supports-attached-package's chance/deterministic inflict line — user can still turn it
off). Element/ailment names + every number (convert %, chance %, base range) are PARSED off each support's own
description text (`_parse_condensed`), not hardcoded per element — a future season's rebalance changes only the
data, never this file.
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
CONDENSED_FIRE = "chromatic_shot_condensed_fire_noble"
CONDENSED_COLD = "chromatic_shot_condensed_cold_noble"
CONDENSED_LIGHTNING = "chromatic_shot_condensed_lightning_noble"
CONDENSED_EROSION = "chromatic_shot_condensed_erosion_noble"
CONDENSED_IDS = frozenset({CONDENSED_FIRE, CONDENSED_COLD, CONDENSED_LIGHTNING, CONDENSED_EROSION})
CS_SUPPORT_IDS = frozenset({LIGHTCHASER, SPLENDOR}) | CONDENSED_IDS

# ── Condensed: structural parse of the support's OWN text — element/ailment names + every number come
# from the data, never hardcoded per element (a rebalance next season changes only the JSON). ──
_CONDENSED_CONVERT_RE = re.compile(
    r"converts\s+([\d.]+)\s*%\s*of the supported skill'?s?\s+physical\s+damage\s+to\s+(\w+)\s+damage", re.I)
_CONDENSED_TAG_RE = re.compile(r"the supported skill gains the (\w+) tag", re.I)
_CONDENSED_BASE_AILMENT_RE = re.compile(
    r"adds\s+([\d.]+)\s*-\s*([\d.]+)\s+base\s+(\w+)\s+damage\s+to\s+the\s+supported\s+skill", re.I)
_CONDENSED_CHANCE_RE = re.compile(
    r"\+\s*([\d.]+)\s*%\s*(\w+)\s+chance\s+for\s+the\s+supported\s+skill", re.I)
_CONDENSED_DETERMINISTIC_RE = re.compile(
    r"inflicts\s+(\w+)\s+when\s+the\s+supported\s+skill\s+deals\s+hit\s+(\w+)\s+damage", re.I)
# Ailment name → the enemy-status condition key it sets (data/conditions.json keys — not this module's invention).
_CONDENSED_ENEMY_COND = {"ignite": "enemy_ignited", "wilt": "enemy_wilted",
                          "frostbite": "enemy_frostbitten", "numbed": "enemy_numbed"}


def _condensed_text(data: dict) -> str:
    lines = data.get("description_lines") or []
    joined = " ".join(str(l.get("text", "")) for l in lines if isinstance(l, dict))
    return joined or str(data.get("raw_text", ""))


def _parse_condensed(data: dict) -> dict:
    """Structural parse of a Condensed support's own text → {element, convert_frac, tag, ailment, base_min,
    base_max, chance_frac, deterministic}. Missing keys when a clause isn't present/doesn't match (defensive —
    the caller no-ops on what it can't find rather than guessing a number)."""
    text = _condensed_text(data)
    out: dict = {}
    m = _CONDENSED_CONVERT_RE.search(text)
    if m:
        out["convert_frac"] = float(m.group(1)) / 100.0
        out["element"] = m.group(2).lower()
    m = _CONDENSED_TAG_RE.search(text)
    if m:
        out["tag"] = m.group(1).lower()
    m = _CONDENSED_BASE_AILMENT_RE.search(text)
    if m:
        out["ailment"] = m.group(3).lower()
        out["base_min"] = float(m.group(1))
        out["base_max"] = float(m.group(2))
    m = _CONDENSED_CHANCE_RE.search(text)
    if m:
        out["chance_frac"] = float(m.group(1)) / 100.0
        out.setdefault("ailment", m.group(2).lower())
    m = _CONDENSED_DETERMINISTIC_RE.search(text)
    if m:
        out["ailment"] = m.group(1).lower()
        out["deterministic"] = True
    return out


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


def condensed_hit_dmg_contribution(sup: dict, data: dict) -> dict | None:
    """Condensed's own tunable roll — same phrase Splendor uses ('+(lo-hi)% additional Hit Damage'), so
    `_SP_ROLL_RE` matches it too (shared regex, not Splendor-specific despite the name), but UNCONDITIONAL:
    Condensed's line has no "vs enemies with …" gate, unlike Splendor's. One function covers all 4 Condensed
    ids — element/label come from `data`, never hardcoded per id here.
    2026-07-16 regression fix: adding CONDENSED_IDS to GUARD_IDS (below) made support_resolver skip this
    line for the generic parser, but no CONTRIB_HOOKS entry existed to replace it — the tunable roll was
    silently dropped while the universal +20% (resolved before the guard check) kept working. This hook
    closes that gap the same way Lightchaser/Splendor's own tunable rolls are resolved."""
    amt = _roll_frac(sup, data, _SP_ROLL_RE)
    if amt is None:
        return None
    item_id = sup.get("item_id")
    return {"stat_key": "hit_dmg_additional", "amount": amt,
            "text": f"+{amt * 100:.2f}% additional Hit Damage for the supported skill |{item_id}|condensed_roll",
            "label": data.get("name") or item_id, "slot": sup.get("slot", 1)}


GUARD_IDS = CS_SUPPORT_IDS
CONTRIB_HOOKS = {LIGHTCHASER: lightchaser_contribution, SPLENDOR: splendor_contribution,
                 **{cid: condensed_hit_dmg_contribution for cid in CONDENSED_IDS}}


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

    overrides: dict = {}
    for cid in ids & CONDENSED_IDS:
        data = (skills_by_id or {}).get(cid) or {}
        info = _parse_condensed(data)
        # The support's own `name` already reads "Chromatic Shot: Condensed <Element> (Noble)" (unlike
        # Lightchaser/Splendor's `data`, which carries a bare "Lightchaser"/"Splendor" `name` — those two
        # hardcode the "Chromatic Shot: " prefix themselves).
        label = data.get("name") or cid

        elem = info.get("element")
        if elem and info.get("convert_frac"):
            frac = info["convert_frac"]
            # Reuses the GENERAL gear/talent conversion pool (engine.offense._conversion_fracs reads
            # physical_convert_to_<elem> the same way a "Converts N% of Physical Damage to <X> Damage" gear
            # line would) — not a bespoke conversion path.
            source.add_slotted(f"physical_convert_to_{elem}", frac, slot, None, SourceEntry(
                stat=f"physical_convert_to_{elem}", amount=frac, source_type="support", label=label,
                text=f"Converts {frac * 100:.0f}% of the supported skill's Physical Damage to "
                     f"{elem.capitalize()} Damage |{cid}|convert", points=1))

        tag = info.get("tag")
        if tag:
            overrides["add_mod_tags"] = (overrides.get("add_mod_tags") or set()) | {tag}

        ailment = info.get("ailment")
        if ailment and "base_min" in info:
            for which in ("min", "max"):
                val = info[f"base_{which}"]
                source.add_slotted(f"{ailment}_dmg_flat_{which}", val, slot, None, SourceEntry(
                    stat=f"{ailment}_dmg_flat_{which}", amount=val, source_type="support", label=label,
                    text=f"Adds {info['base_min']:g}-{info['base_max']:g} Base {ailment.capitalize()} Damage "
                         f"to the supported skill |{cid}|base_{which}", points=1))
        if ailment and "chance_frac" in info:
            frac = info["chance_frac"]
            source.add_slotted(f"{ailment}_chance", frac, slot, None, SourceEntry(
                stat=f"{ailment}_chance", amount=frac, source_type="support", label=label,
                text=f"+{frac * 100:.0f}% {ailment.capitalize()} chance for the supported skill "
                     f"|{cid}|chance", points=1))
        if ailment in _CONDENSED_ENEMY_COND:
            source.referenced_conditions.add(_CONDENSED_ENEMY_COND[ailment])
    return overrides


# ── Type-C preseed: Splendor auto-inflicts the three Elemental Ailments; each Condensed support
# auto-inflicts its own single ailment (chance-based Ignite/Wilt included — same floor-style "enable the
# gate by default" policy engine.ailment_inflict / support_mapper.map_autoderive_line use everywhere else
# for a %-chance or deterministic inflict line; never estimated as EV/uptime). ──
_SRC = "Chromatic Shot: Splendor"


def preseed(*, slot, condition_state, attached_supports, skills_by_id,
            auto_sources=None, auto_values=None, manual_keys=None, **_) -> None:
    ids = _slot_support_ids(attached_supports, slot)
    manual = manual_keys or set()

    def _record(key, value, src):
        if auto_sources is not None:
            auto_sources[key] = src
        if auto_values is not None:
            auto_values[key] = value

    if SPLENDOR in ids:
        # Numbed: inflicting it applies ≥1 stack — UNLESS the user explicitly set the stack count (0 = opt out
        # of Numbed entirely). The auto intent (1) is recorded regardless so the Config field can fall back to it.
        if "numbed_stacks" not in manual and float(condition_state.get("numbed_stacks") or 0.0) < 1.0:
            condition_state["numbed_stacks"] = 1.0
        _record("numbed_stacks", 1.0, _SRC)
        numbed_on = float(condition_state.get("numbed_stacks") or 0.0) >= 1.0

        # Frostbite + Ignite are always inflicted; Numbed only when there's ≥1 stack (so a user-set 0 turns it
        # off, which then drops Splendor's all-three-ailment Hit Damage gate).
        for a, on in (("enemy_frostbitten", True), ("enemy_ignited", True), ("enemy_numbed", numbed_on)):
            _record(a, on, _SRC)
            if a not in manual:
                condition_state[a] = bool(on)

    for cid in ids & CONDENSED_IDS:
        data = (skills_by_id or {}).get(cid) or {}
        info = _parse_condensed(data)
        ailment = info.get("ailment")
        cond_key = _CONDENSED_ENEMY_COND.get(ailment)
        if not cond_key:
            continue
        src = data.get("name") or cid
        _record(cond_key, True, src)
        if cond_key not in manual:
            condition_state[cond_key] = True
        if ailment == "numbed":
            if "numbed_stacks" not in manual and float(condition_state.get("numbed_stacks") or 0.0) < 1.0:
                condition_state["numbed_stacks"] = 1.0
            _record("numbed_stacks", 1.0, src)


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
# Condensed quartet: one spec per clause × element, generated from the same data so a rebalance never needs a
# LINE_SPECS edit — element/ailment names come from the (verbatim, hardcoded-by-id-only) SS13 support text below,
# used ONLY to pick which stat keys a given clause resolves to (never a coefficient).
_CONDENSED_ELEMENT_AILMENT = {
    CONDENSED_FIRE: ("fire", "ignite"), CONDENSED_COLD: ("cold", "frostbite"),
    CONDENSED_LIGHTNING: ("lightning", "numbed"), CONDENSED_EROSION: ("erosion", "wilt"),
}
for _cid, (_elem, _ailment) in _CONDENSED_ELEMENT_AILMENT.items():
    LINE_SPECS.append({"support_ids": {_cid}, "phrase": re.compile(r"Converts.*Physical Damage to", re.I),
                        "keys": [f"physical_convert_to_{_elem}"], "range_re": None})
    LINE_SPECS.append({"support_ids": {_cid}, "phrase": re.compile(r"gains the \w+ Tag", re.I),
                        "keys": [], "range_re": None})
    if _ailment in ("ignite", "wilt"):
        LINE_SPECS.append({"support_ids": {_cid},
                            "phrase": re.compile(rf"Adds .* Base {_ailment} Damage", re.I),
                            "keys": [f"{_ailment}_dmg_flat_min", f"{_ailment}_dmg_flat_max"], "range_re": None})
        LINE_SPECS.append({"support_ids": {_cid}, "phrase": re.compile(rf"{_ailment} chance", re.I),
                            "keys": [f"{_ailment}_chance"], "range_re": None})
    else:
        LINE_SPECS.append({"support_ids": {_cid}, "phrase": re.compile(rf"Inflicts {_ailment}", re.I),
                            "keys": [], "range_re": None})
