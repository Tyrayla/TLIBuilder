"""Spirit Magus "Origin of Spirit Magus" summoner buffs — data-driven magnitudes.

Glossary 743: "Buff effect gained after Activating a Spirit Magus summoning skill." Each base magus
summon grants the SUMMONER an origin effect whose magnitude scales with the summon skill's level.
The per-level values live ONLY in the free-text ``progression[].values.Descript`` of the skill data
(40 entries), so this module parses them with one regex per magus — the numbers always come from the
season data, never from a hardcoded table (spec: .wolf/engine-spec-magus-origins.md; all magnitudes
are needs-verification — sourced from skill text, not confirmed live).

Origin of Thunder is NOT handled here: its aggregator block predates this module, is golden-locked
(test_minion_offense asserts 0.06/0.0725 @L20), and its linear formula reproduces the data exactly —
only its SCAN is shared (compute uses THUNDER_ID alongside ORIGIN_SPECS).

Magnificent supports ("Origin of Spirit Magus provided by the supported skill gains an additional
effect: ...") add a summoner-side effect parsed from the support's own per-level progression text.
Tier ranges "(a–b)" resolve at the MIDPOINT, mirroring support_resolver._range_mid_fraction's
convention. Wicked is deliberately ABSENT: its added effects are "for all Spirit Magi" (minion-scoped
conversion + per-minion ramp) and belong to the minion engine, not the summoner-origin path.
"""
from __future__ import annotations

import re

THUNDER_ID = "summon_thunder_magus"

# Base magus origins (Thunder excluded — see module docstring). ``cond`` is the synthetic condition
# flag compute sets (with ``<cond>_value`` carrying the parsed, level-resolved magnitude, PRE
# origin-effect scaling); the aggregator multiplies by the origin factor and emits.
ORIGIN_SPECS: dict[str, dict] = {
    "summon_fire_magus": {
        "cond": "origin_of_fire",
        # "Gains Origin of Fire, giving the summoner +58 Attack and Spell Critical Strike Rating"
        "regex": re.compile(r"giving the summoner\s*\+?([\d.]+)\s*Attack and Spell Critical Strike Rating", re.I),
    },
    "summon_frost_magus": {
        "cond": "origin_of_ice",
        # "Gains Origin of Ice, restoring 2.4 % of Max Life and Max Energy Shield per second to the summoner"
        "regex": re.compile(r"restoring\s*\+?([\d.]+)\s*%\s*of Max Life and Max Energy Shield per second", re.I),
    },
    "summon_rock_magus": {
        "cond": "origin_of_rock",
        # "Origin of Spirit Magus : -5.2 % additional Hit Damage taken, up to -50 % additional damage"
        "regex": re.compile(r"Origin of Spirit Magus\s*:\s*(-?[\d.]+)\s*%\s*additional Hit Damage taken", re.I),
    },
    "summon_erosion_magus": {
        "cond": "origin_of_erosion",
        # "Origin of Spirit Magus : -6.3 % additional Damage Over Time taken, up to -50 % additional damage"
        "regex": re.compile(r"Origin of Spirit Magus\s*:\s*(-?[\d.]+)\s*%\s*additional Damage Over Time taken", re.I),
    },
}

# Magnificent supports that ADD a summoner-side origin effect. Keyed by support item_id; ``cond`` is
# the synthetic flag (value key = ``<cond>_value``, the tier-midpoint % at the support's level).
MAGNIFICENT_ORIGIN_EFFECTS: dict[str, dict] = {
    "summon_fire_magus_fire_ward_magnificent": {
        "cond": "origin_ward_fire", "owner": "summon_fire_magus",
        "regex": re.compile(r"\+\(([\d.]+)[^\d.]+([\d.]+)\)\s*%\s*Max Fire Resistance", re.I),
    },
    "summon_frost_magus_cold_ward_magnificent": {
        "cond": "origin_ward_cold", "owner": "summon_frost_magus",
        "regex": re.compile(r"\+\(([\d.]+)[^\d.]+([\d.]+)\)\s*%\s*Max Cold Resistance", re.I),
    },
    "summon_thunder_magus_lightning_ward_magnificent": {
        "cond": "origin_ward_lightning", "owner": "summon_thunder_magus",
        "regex": re.compile(r"\+\(([\d.]+)[^\d.]+([\d.]+)\)\s*%\s*Max Lightning Resistance", re.I),
    },
    "summon_rock_magus_unyielding_magnificent": {
        "cond": "origin_unyielding", "owner": "summon_rock_magus",
        "regex": re.compile(r"\+\(([\d.]+)[^\d.]+([\d.]+)\)\s*%\s*Armor Effective Rate against non-Physical Damage", re.I),
    },
    "summon_erosion_magus_plague_source_magnificent": {
        "cond": "origin_plague_source", "owner": "summon_erosion_magus",
        "regex": re.compile(r"\+\(([\d.]+)[^\d.]+([\d.]+)\)\s*%\s*additional Erosion Damage", re.I),
    },
}


# Emission table shared by the aggregator (stat contributions) and compute's origin_summary (display):
# (condition flag, ((stat_key, unit_scale), ...), label, source_name, text format, clamp floor or None).
# Magnitude flow: compute parses the raw % / rating from data → `<flag>_value` condition → × origin
# factor → clamp (raw-% space) → × unit_scale per stat. Thunder is handled beside this table (formula
# block, golden-locked).
EMIT_TABLE: tuple = (
    ("origin_of_fire", (("attack_crit_rating_flat", 1.0), ("spell_crit_rating_flat", 1.0)),
     "Origin of Fire", "Fire Magus",
     "+{v:g} Attack and Spell Critical Strike Rating (Origin of Fire)", None),
    ("origin_of_ice", (("life_regen_inc", 0.01), ("energy_shield_regen_pct", 0.01)),
     "Origin of Ice", "Frost Magus",
     "Restores {v:.4g}% of Max Life and Max Energy Shield per second (Origin of Ice)", None),
    ("origin_of_rock", (("hit_dmg_taken_additional", 0.01),),
     "Origin of Spirit Magus", "Rock Magus",
     "{v:.4g}% additional Hit Damage taken (Origin of Spirit Magus, up to -50%)", -0.50),
    ("origin_of_erosion", (("dot_dmg_taken_additional", 0.01),),
     "Origin of Spirit Magus", "Erosion Magus",
     "{v:.4g}% additional Damage Over Time taken (Origin of Spirit Magus, up to -50%)", -0.50),
    ("origin_ward_fire", (("fire_resistance_max_inc", 0.01),),
     "Fire Ward (Origin effect)", "Fire Magus",
     "+{v:.3g}% Max Fire Resistance (Origin of Spirit Magus additional effect)", None),
    ("origin_ward_cold", (("cold_resistance_max_inc", 0.01),),
     "Cold Ward (Origin effect)", "Frost Magus",
     "+{v:.3g}% Max Cold Resistance (Origin of Spirit Magus additional effect)", None),
    ("origin_ward_lightning", (("lightning_resistance_max_inc", 0.01),),
     "Lightning Ward (Origin effect)", "Thunder Magus",
     "+{v:.3g}% Max Lightning Resistance (Origin of Spirit Magus additional effect)", None),
    ("origin_unyielding", (("armor_effective_rate_non_physical_inc", 0.01),),
     "Unyielding (Origin effect)", "Rock Magus",
     "+{v:.3g}% Armor Effective Rate against non-Physical Damage (Origin of Spirit Magus additional effect)", None),
    ("origin_plague_source", (("erosion_dmg_additional", 0.01),),
     "Plague Source (Origin effect)", "Erosion Magus",
     "+{v:.3g}% additional Erosion Damage (Origin of Spirit Magus additional effect)", None),
)


# Added-effect flag → the origin flag it belongs to (a magnificent effect scales with ITS magus's
# per-origin factor, including that magus's scalar-support increased share).
ORIGIN_OWNER_FLAG: dict[str, str] = {
    "origin_ward_fire": "origin_of_fire",
    "origin_ward_cold": "origin_of_ice",
    "origin_ward_lightning": "origin_of_thunder",
    "origin_unyielding": "origin_of_rock",
    "origin_plague_source": "origin_of_erosion",
}

# Origin-effect SCALAR supports ("N% Origin of Spirit Magus effect for the supported skill") — per-skill
# scoped: they raise ONLY their own magus's origin factor, via the INCREASED pool (owner-classified
# 2026-08-10, needs-verification). The Friend pair gates on the count of DISTINCT magus types slotted.
# Values are plain per-level numerics in the support progression (no ranges).
SCALAR_ORIGIN_SUPPORTS: dict[str, dict] = {
    "precise_superpower": {"min_types": 1},
    "friend_of_spirit_magi": {"min_types": 2},
    "precise_friend_of_spirit_magi": {"min_types": 3},
}

_SCALAR_VALUE_RE = re.compile(r"([\d.]+)\s*%\s*(?:Origin of Spirit Magus\s*)?[Ee]ffect")


def scalar_support_value(support_data: dict, level: int) -> float | None:
    """The origin-effect % of a scalar support at ``level`` (e.g. 48.2). The per-level progression entry
    carries template→value pairs; anchor on the origin-effect TEMPLATE first (so an unrelated second
    numeric — a duration, a radius — can never be returned by key-order accident), then fall back to
    the sole float value, then to parsing the template text itself."""
    entry = _progression_entry(support_data, level)
    if entry is None:
        return None
    values = entry.get("values") or {}
    keyed = [(str(k), v) for k, v in values.items()]
    for k, v in keyed:
        if "origin of spirit magus" in k.lower() and "effect" in k.lower():
            try:
                return float(v)
            except (TypeError, ValueError):
                m = _SCALAR_VALUE_RE.search(k)
                if m:
                    return float(m.group(1))
    floats = []
    for _k, v in keyed:
        try:
            floats.append(float(v))
        except (TypeError, ValueError):
            pass
    if len(floats) == 1:
        return floats[0]
    return None


def origin_factor(inc_total: float, add_total: float, support_inc: float = 0.0) -> float:
    """Per-origin scaling factor: (1 + Σ increased + this magus's support increased) × (1 + additional)."""
    return (1.0 + inc_total + support_inc) * (1.0 + add_total)


def scaled_magnitude(raw: float, origin_factor: float, clamp: float | None) -> float:
    """Raw data magnitude (% / rating) × origin factor, clamped in raw-% space (−50 ↔ clamp −0.50)."""
    scaled = raw * origin_factor
    if clamp is not None:
        scaled = max(scaled, clamp / 0.01)
    return scaled


def _progression_entry(skill_data: dict, level: int) -> dict | None:
    """The progression entry at ``level``, clamped to the levels actually present in the data.
    Accepts int OR float level keys (a data regen serializing 20.0 must not silently disable an origin)."""
    prog = skill_data.get("progression") or []
    by_level = {int(e["level"]): e for e in prog
                if isinstance(e, dict) and isinstance(e.get("level"), (int, float))
                and not isinstance(e.get("level"), bool)}
    if not by_level:
        return None
    lvl = max(min(int(level), max(by_level)), min(by_level))
    return by_level.get(lvl)


def origin_magnitude(skill_data: dict, level: int) -> float | None:
    """Parse a base magus's origin magnitude (the raw % / rating number, sign included) at ``level``
    from its progression Descript. None when the skill isn't a known magus or the text doesn't parse
    (never guess — an unparsed origin simply doesn't activate, surfaced by its absence)."""
    spec = ORIGIN_SPECS.get(skill_data.get("item_id", ""))
    if spec is None:
        return None
    entry = _progression_entry(skill_data, level)
    if entry is None:
        return None
    text = str((entry.get("values") or {}).get("Descript", ""))
    m = spec["regex"].search(text)
    return float(m.group(1)) if m else None


def magnificent_effect_midpoint(support_data: dict, tier) -> float | None:
    """Parse a magnificent support's added-origin-effect range at the given roll TIER and return the
    midpoint % (e.g. "(1.4–1.6)" → 1.5).

    Magnificent progression keys are roll TIERS, not levels — 2/1/0 with LOWER = better roll — and the
    app stores the tier in the attached support's ``level`` field (the 0–2 Tier control). Selection
    reuses support_resolver's convention exactly: exact tier match, fallback to tier 1 (the headline
    roll), then any entry. Falls back to the description_lines when no progression text parses."""
    spec = MAGNIFICENT_ORIGIN_EFFECTS.get(support_data.get("item_id", ""))
    if spec is None:
        return None
    from engine.support_resolver import _progression_for_tier, _tier_value
    texts: list[str] = []
    entry = _progression_for_tier(support_data.get("progression"), _tier_value(tier))
    if entry is not None:
        texts.extend(str(v) for v in (entry.get("values") or {}).values())
    for line in support_data.get("description_lines") or []:
        texts.append(str(line.get("text", "") if isinstance(line, dict) else line))
    for text in texts:
        m = spec["regex"].search(text)
        if m:
            return (float(m.group(1)) + float(m.group(2))) / 2.0
    return None
