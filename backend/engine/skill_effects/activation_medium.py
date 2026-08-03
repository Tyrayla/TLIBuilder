"""Activation Medium roll parsing + wiring.

Activation mediums trigger the supported skill on a condition/cadence and carry a handful of rolled values on
ONE concatenated progression line per tier. This module:
  1. `parse_am_rolls(data)` — a GENERAL parser: scan every tier's line for `(lo–hi)` ranges, classify each by the
     surrounding text into a canonical roll (stable identity across tiers, unit/scale, per-tier ranges, the engine
     stat it maps to or None, and a selector `group`). Drives the support panel's dynamic sliders + the wiring below.
  2. `apply_slot_effects(...)` — emit the WIRED stats for an equipped medium from the user's selected rolls/tiers/
     group choice (values in `specific_rolls`, tiers in `specific_roll_tiers`, choice in `roll_group_choice`).

Tyra-confirmed conventions:
  - `"every (X) s"` = real trigger cadence → `trigger_interval` (overrides cast rate, any skill). `"Interval: (X) s"`
    = a rate-limit (CAN occur) → recorded, not wired.
  - Wind Rhythm converts Cast Speed → CDR against a per-tier base cooldown; handled by the Wind Rhythm rate helper.
  - Duration/Cooldown are a mutually-exclusive selector (`group="cdr_or_duration"`).
Every activation medium is GUARDed (its concatenated line is behavioral / handled here, not the generic resolver).
"""
from __future__ import annotations
import re

from engine.models import SourceEntry

# Wind Rhythm per-tier base cooldown (seconds) — L0 0.5 / L1 0.6 / L2 0.7 / L3 0.8 (Tyra + calculator).
WIND_RHYTHM_BASE_COOLDOWN = {0: 0.5, 1: 0.6, 2: 0.7, 3: 0.8}

# One range: optional sign, (lo – hi), optional trailing unit (%, s, m). s/m guarded so "skill"/"m"-words don't match.
_RANGE = re.compile(r"([+\-−]?)\(\s*(-?[\d.]+)\s*[–—−\-]\s*(-?[\d.]+)\s*\)\s*(%|s(?![A-Za-z])|m(?![A-Za-z]))?")

# The FIXED (non-ranged) per-meter rate that precedes the "up to +(lo-hi)%" cap on the same progression line,
# e.g. "...+3 % additional damage for every 1m of movement made during the trigger interval, up to +(18-21) %."
# Data-driven so a future season/tier retune of the rate (it dropped 3%->2% at Rhythm L2, per SS12 _skills.json
# activation_medium_rhythm.progression) can't silently desync from the hardcoded constant this replaces.
_RHYTHM_RATE_RE = re.compile(r"([+\-−]?[\d.]+)\s*%\s*additional damage for every 1m")
_RHYTHM_RATE_FALLBACK = 0.03   # Rhythm's own base (level 0) rate — last-resort default if a level's line can't be parsed.


def _rhythm_move_rate_by_level(data: dict) -> dict[int, float]:
    """Per-level %/meter movement-damage rate for an activation medium using the `rhythm_move_cap` special,
    parsed from the item's OWN crawled progression text — the same sentence the "up to +(lo-hi)%" cap `val`
    is selected from (see `apply_slot_effects`'s `rhythm_move_cap` branch). Returns {} if nothing parses."""
    rates: dict[int, float] = {}
    for entry in (data or {}).get("progression") or []:
        lvl = entry.get("level")
        if lvl is None:
            continue
        line = str((entry.get("values") or {}).get("name", ""))
        m = _RHYTHM_RATE_RE.search(line)
        if not m:
            continue
        try:
            rates[int(lvl)] = float(m.group(1)) / 100.0
        except (TypeError, ValueError):
            continue
    return rates


def _parse_range(sign: str, lo_s: str, hi_s: str, scale: float) -> dict:
    lo, hi = float(lo_s), float(hi_s)
    if sign in ("-", "−") and lo > 0:      # a leading "-(X–Y)" negates both bounds
        lo, hi = -lo, -hi
    lo, hi = sorted((lo / scale, hi / scale))
    return {"min": lo, "max": hi, "mid": (lo + hi) / 2.0}


# Canonical roll classifier. Each rule: keyword test on (before, after, unit) → the canonical roll shape.
# `stat_key` is the engine stat for a plain additive emit; a `special` marker routes to bespoke wiring; None = record.
def _classify(before: str, after: str, unit: str) -> dict | None:
    b, a = before.lower(), after.lower()
    # `label` is a SHORT panel name; `desc` is the fuller phrase (shown on hover).
    if unit == "s":
        if b.rstrip().endswith("interval:") or re.search(r"interval:\s*$", b):
            return dict(identity="trigger_rate_limit", label="Rate Limit", desc="Minimum interval between triggers",
                        unit="s", scale=1.0, stat_key=None, special=None, group=None, wired=False)
        if re.search(r"every\s*$", b) or "prepares the supported skill every" in b:
            return dict(identity="trigger_interval", label="Interval", desc="Trigger interval (cast rate = 1 ÷ interval)",
                        unit="s", scale=1.0, stat_key="trigger_interval", special="trigger_interval", group=None, wired=True)
        return dict(identity="time", label="Time", desc="Time", unit="s", scale=1.0,
                    stat_key=None, special=None, group=None, wired=False)
    if unit == "m":
        return dict(identity="radius", label="Radius", desc="Trigger radius (metres)", unit="m", scale=1.0,
                    stat_key=None, special=None, group=None, wired=False)
    if "additional duration" in a:
        return dict(identity="duration_additional", label="Duration", desc="Additional Duration for the supported skill",
                    unit="%", scale=100.0, stat_key="skill_effect_duration_additional", special=None, group="cdr_or_duration", wired=True)
    if "additional cooldown recovery" in a:
        return dict(identity="cdr_additional", label="Cooldown Recovery", desc="Additional Cooldown Recovery Speed",
                    unit="%", scale=100.0, stat_key="cdr_speed_additional", special=None, group="cdr_or_duration", wired=True)
    if "additional hit damage for skills cast by spell burst" in a:
        return dict(identity="spell_burst_hit_dmg_additional", label="Spell-Burst Hit Dmg",
                    desc="Additional Hit Damage for skills cast by Spell Burst", unit="%", scale=100.0,
                    stat_key="spell_burst_hit_dmg_additional", special=None, group=None, wired=True)
    if "additional hit damage for the supported skill" in a:
        return dict(identity="hit_dmg_additional", label="Hit Damage", desc="Additional Hit Damage for the supported skill",
                    unit="%", scale=100.0, stat_key="hit_dmg_additional", special=None, group=None, wired=True)
    if "damage for minions" in a:
        return dict(identity="minion_dmg_additional", label="Minion Damage", desc="Additional damage for Minions",
                    unit="%", scale=100.0, stat_key="minion_dmg_additional", special=None, group=None, wired=True)
    if "additional damage for the supported skill" in a:
        return dict(identity="dmg_additional", label="Damage", desc="Additional damage for the supported skill",
                    unit="%", scale=100.0, stat_key="dmg_additional", special=None, group=None, wired=True)
    if "cast speed" in a and "cooldown recovery" in a:   # Wind Rhythm: cast-speed → CDR share
        return dict(identity="wind_cast_to_cdr", label="Cast→CDR",
                    desc="% of Cast Speed applied to Cooldown Recovery Speed", unit="%", scale=100.0,
                    stat_key=None, special="wind_share", group=None, wired=True)
    if "movement made during the trigger interval" in a or "movement made during the trigger interval" in b:
        return dict(identity="rhythm_move_cap", label="Move Cap", desc="Movement damage cap (per-meter bonus, up to this)",
                    unit="%", scale=100.0, stat_key=None, special="rhythm_move_cap", group=None, wired=True)
    if "willpower" in a:   # Still Attack grants a Willpower support at level N — surfaced; injection is a follow-up.
        return dict(identity="willpower_level", label="Willpower Lv", desc="Grants a Willpower support at this level",
                    unit="", scale=1.0, stat_key=None, special="willpower_level", group=None, wired=False)
    if "attach range" in a:
        return dict(identity="tangle_attach_range", label="Attach Range", desc="Tangle attach range",
                    unit="%", scale=100.0, stat_key="tangle_attach_range_inc", special=None, group=None, wired=False)
    if "instruction" in a:
        return dict(identity="instruction_dmg", label="Per-Instruction", desc="Per-Instruction damage",
                    unit="%", scale=100.0, stat_key=None, special=None, group=None, wired=False)
    seg = re.split(r"[.,;]|\(", after)[0].strip()
    return dict(identity="misc:" + re.sub(r"[^a-z0-9]+", "_", (seg or "value").lower())[:24],
                label=(seg[:24] or "Value"), desc=(seg[:80] or "Value"), unit=unit or "%",
                scale=100.0 if unit == "%" else 1.0, stat_key=None, special=None, group=None, wired=False)


def parse_am_rolls(data: dict) -> list[dict]:
    """All rolled values of an activation medium, grouped across tiers.
    Returns [{identity, label, unit, scale, ranges_by_tier:{tier:{min,max,mid}}, stat_key, special, group, wired}]."""
    prog = (data or {}).get("progression") or []
    by_id: dict[str, dict] = {}
    order: list[str] = []
    for entry in prog:
        tier = entry.get("level")
        line = str((entry.get("values") or {}).get("name", ""))
        for m in _RANGE.finditer(line):
            sign, lo_s, hi_s, unit = m.group(1), m.group(2), m.group(3), (m.group(4) or "")
            # classify on the phrase up to the NEXT range only (a range's stat words sit right after it; the full
            # tail would leak a later roll's keyword — e.g. the CDR range's tail also contains "Duration").
            after_head = line[m.end():].split("(")[0]
            rule = _classify(line[:m.start()], after_head, unit)
            if rule is None:
                continue
            rng = _parse_range(sign, lo_s, hi_s, rule["scale"])
            rid = rule["identity"]
            if rid not in by_id:
                by_id[rid] = {**rule, "ranges_by_tier": {}}
                order.append(rid)
            by_id[rid]["ranges_by_tier"].setdefault(tier, rng)
    return [by_id[i] for i in order]


def is_activation_medium(item_id: str | None) -> bool:
    return bool(item_id) and item_id.startswith("activation_medium_")


# Every activation medium is guarded (its concatenated line is handled here, not the generic resolver). The
# guard is by prefix, via is_activation_medium() in support_resolver — no per-id list needed.
CONTRIB_HOOKS: dict = {}
GUARD_IDS = frozenset()   # prefix-guarded (see support_resolver); no per-id list needed


def _sel(rolls: dict, tiers: dict, group_choice: dict, r: dict):
    """The user's selected (value, tier) for a roll r, honoring the Duration/Cooldown group choice; None if the
    roll is the UNSELECTED option of its group."""
    ident = r["identity"]
    if r.get("group") and group_choice.get(r["group"], _default_group_choice(r)) != ident:
        return None
    rbt = r["ranges_by_tier"]
    tier = tiers.get(ident)
    rng = rbt.get(tier) if tier is not None else None
    if rng is None:
        # default tier: prefer 0, else lowest available
        dk = 0 if 0 in rbt else (min(rbt) if rbt else None)
        rng = rbt.get(dk)
    val = rolls.get(ident)
    if val is None:
        val = rng["mid"] if rng else 0.0
    return float(val)


def _default_group_choice(r: dict) -> str:
    # Duration is the default of the CDR/Duration selector (more universally useful than CDR).
    return "duration_additional" if r.get("group") == "cdr_or_duration" else r["identity"]


def apply_slot_effects(*, source, resolved, slot, condition_state, mod_tags, attached_supports,
                       skills_by_id, **_) -> dict:
    """Emit the WIRED stats for the equipped activation medium(s) on this slot from the user's selected rolls.
    Stat-driven: additive rolls → `source.add_slotted`; cadence → `trigger_interval` / `wind_rhythm_*` stats read
    by compute_skill_rates; Rhythm movement bonus → `dmg_additional`. Willpower injection is returned for compute
    (deferred wiring). Returns {'inject_supports': [...]} or {}."""
    out: dict = {}
    for s in (attached_supports or []):
        if s.get("slot", 1) != slot or not s.get("enabled", True):
            continue
        item_id = s.get("item_id")
        if not is_activation_medium(item_id):
            continue
        data = (skills_by_id or {}).get(item_id) or {}
        rolls = s.get("specific_rolls") or {}
        tiers = s.get("specific_roll_tiers") or {}
        gchoice = s.get("roll_group_choice") or {}
        label = data.get("name", item_id)

        def emit(stat_key, val, note):
            if val:
                source.add_slotted(stat_key, val, slot, None, SourceEntry(
                    stat=stat_key, amount=val, source_type="support",
                    label=label, text=f"{label}: {note} |activation_medium", points=1))

        for r in parse_am_rolls(data):
            val = _sel(rolls, tiers, gchoice, r)
            if val is None:
                continue
            special, stat_key = r.get("special"), r.get("stat_key")
            if special == "trigger_interval":
                emit("trigger_interval", val, r["label"])
            elif special == "wind_share":
                emit("wind_rhythm_share", val, "Cast Speed → CDR share")
                # Base cooldown is a medium property → the SUPPORT tier (top selector), independent of the share roll.
                try:
                    _lvl = int(s.get("level", 0) or 0)
                except (TypeError, ValueError):
                    _lvl = 0
                emit("wind_rhythm_base_cooldown", WIND_RHYTHM_BASE_COOLDOWN.get(_lvl, 0.5), "Base Cooldown")
            elif special == "rhythm_move_cap":
                try:
                    meters = float(condition_state.get("demolisher_meters_moved", 0) or 0)
                except (TypeError, ValueError):
                    meters = 0.0
                try:
                    _lvl = int(s.get("level", 0) or 0)
                except (TypeError, ValueError):
                    _lvl = 0
                rates = _rhythm_move_rate_by_level(data)
                rate = rates.get(_lvl, rates.get(0, _RHYTHM_RATE_FALLBACK))
                emit("dmg_additional", min(rate * meters, val), "Rhythm movement damage")
            elif special == "willpower_level":
                out.setdefault("inject_supports", []).append({"item_id": "willpower", "level": int(round(val))})
            elif stat_key and r.get("wired"):
                emit(stat_key, val, r["label"])
    return out
