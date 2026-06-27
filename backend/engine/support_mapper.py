"""Map a parsed support line → engine contributions (P2).

Consumes `support_lines.parse_support` output and emits, for the support's chosen level:
  * stat contributions  — {stat_key, amount, text} the aggregator injects (like the existing resolver)
  * condition effects    — {condition_key, value, mode} compute applies to condition_state (auto-derive)
  * captures             — inert stats stored but not yet affecting DPS (never silently dropped)

This module holds the line→stat/condition mapping table (the modeling decisions worked out in
SUPPORT_MODELING_SPEC.md). It starts with value parsing + the ✅ damage/stat lines; conditionals,
auto-derived debuffs/buffs, and the remaining captures are layered in next.
"""
from __future__ import annotations
from dataclasses import dataclass
import re

from engine.support_lines import SupportLine


# ── Value parsing ─────────────────────────────────────────────────────────────
def _eval_token(tok: str) -> float:
    tok = tok.strip()
    if "/" in tok:                      # the data stores fractions: "37/5" = 7.4, "31/2" = 15.5
        a, b = tok.split("/", 1)
        return float(a) / float(b)
    return float(tok)


def parse_value(raw: str) -> list[float]:
    """Parse a data value into a list of numbers. Comma separates multiple ("2,3" = min,max;
    "27/10,54/5" = value,cap); each part may be a fraction. Single → one-element list."""
    return [_eval_token(t) for t in str(raw).split(",") if t.strip()]


def _level_value(line: SupportLine, level: int) -> list[float]:
    """The scaling line's value at `level` (nearest available tier ≤ level, else lowest)."""
    tv = line.tier_values
    if not tv:
        return []
    if level in tv:
        return parse_value(tv[level])
    avail = sorted(tv)
    pick = max((l for l in avail if l <= level), default=avail[0])
    return parse_value(tv[pick])


def _flat_number(text: str) -> float | None:
    """First signed number in a flat line, as a plain value (e.g. '+2' → 2, '-15 %' → -15)."""
    m = re.search(r"[+\-]?\s*\d+(?:[.,]\d+)?", text)
    return _eval_token(m.group(0).replace(" ", "")) if m else None


_RANGE_PCT = re.compile(r"\(?\s*([\d.]+)\s*[‐-―\-]\s*([\d.]+)\s*\)?\s*%")


def _flat_dmg_value(text: str) -> list[float]:
    """Value for a non-scaling damage line: the tier-MID of a '(a-b)%' range (matches the engine's
    tier-midpoint convention, e.g. activation-medium ranges), else the first signed number."""
    m = _RANGE_PCT.search(text)
    if m:
        return [(float(m.group(1)) + float(m.group(2))) / 2]
    v = _flat_number(text)
    return [v] if v is not None else []


# ── Contributions ─────────────────────────────────────────────────────────────
@dataclass
class StatContribution:
    stat_key: str
    amount: float
    text: str                 # unique pooling identity (support id + line); set by caller wrapper
    modeled: bool = True      # False = captured-but-inert (stored, no DPS effect yet)


# Damage / general stat mapping is no longer table-driven here — map_line delegates to engine.mod_parser
# (the single authority) via map_via_parser, so supports can't drift from gear/talents on pool or type.


# ── Added-flat damage (needs the supported skill's category: spell | attack) ──
_ADDED_FLAT_RE = re.compile(r"add[s]?\s*#\s*-\s*#\s*(cold|fire|lightning|erosion|physical)")


def map_added_flat(line: SupportLine, level: int, cat: str) -> list[StatContribution]:
    """'Adds #-# <Type> Damage to the supported skill' → {type}_{cat}_dmg_flat_min/max. Value is the
    [min,max] range. `cat` ('spell'|'attack') is the supported skill's category."""
    m = _ADDED_FLAT_RE.search(line.template)
    if not m or "damage" not in line.template:
        return []
    dtype = m.group(1)
    vals = _level_value(line, level) if line.scaling else parse_value(line.text)
    if len(vals) < 2 or cat not in ("spell", "attack"):
        return []
    return [StatContribution(f"{dtype}_{cat}_dmg_flat_min", vals[0], line.text),
            StatContribution(f"{dtype}_{cat}_dmg_flat_max", vals[1], line.text)]


# ── Capture rules: flat lines stored as inert stats (never dropped) ───────────
# (regex on template, stat_key, value_kind). flag → amount 1.0; pct → ÷100; flat → raw count.
_CAPTURE_RULES: list[tuple[str, str, str]] = [
    # "+N Jumps for the supported skill" → extra_jumps_flat (consumed by jump-using skills' offense, e.g.
    # Chain Lightning's Merge shotgun / Augmentation). NOT inert — it feeds DPS for those skills.
    (r"jumps for the supported",                       "extra_jumps_flat", "flat"),
    (r"projectile quantity",                          "projectile_quantity_flat", "flat"),
    (r"shadow quantity",                              "max_shadow_quantity_flat", "flat"),
    (r"additional refractions|additional beams|beams for the supported", "extra_beams_flat", "flat"),
    (r"beam length for the supported",                "beam_length_additional", "pct"),
    (r"additional stack\(s\) of ignite|stack of ignite",  "ignite_stacks_inflicted_flat", "flat"),
    (r"ignite chance for the supported",              "ignite_chance", "pct"),
    (r"additional stacks of wilt|stack\(s\) of wilt", "wilt_stacks_inflicted_flat", "flat"),
    (r"chance .*to .*wilt|to inflict.*wilt",          "wilt_chance", "pct"),
    (r"chance to inflict.*trauma|inflict a? ?trauma", "trauma_chance", "pct"),
    (r"min channeled stacks",                         "min_channeled_stacks_flat", "flat"),
    (r"horizontal projectile penetration",            "horizontal_projectile_penetration_flat", "flat"),
    (r"demolisher charge restoration speed",          "demolisher_charge_speed_inc", "pct"),
    (r"aura effect for the supported",                "aura_effect_inc", "pct"),
    # Sealed-mana reservation supports (slot-local; consumed by engine.utility.apply_reservation). The
    # "additional" rule MUST precede the generic one (first match wins). Values may be negative (Seal
    # Conversion's "-70% additional Sealed Mana Compensation"). seal_to_life = a flag toggling the host
    # skill to seal Life instead of Mana ("Replaces Sealed Mana … with Sealed Life").
    # \s* between words: the scraper glues word pairs inconsistently ("mana compensation" vs "manacompensation").
    (r"additional\s*sealed\s*mana\s*compensation\s*for\s*the\s*supported", "sealed_mana_compensation_additional", "pct"),
    (r"sealed\s*mana\s*compensation\s*for\s*the\s*supported", "sealed_mana_compensation_inc", "pct"),
    (r"replaces\s*sealed\s*mana.*sealed\s*life",      "seal_to_life", "flag"),
    # Lunar Eclipse: a support that IMPARTS a seal onto its host (even an active skill) + removes mana cost.
    (r"seal\s*#\s*%\s*max\s*mana",                    "imparted_seal_mana_pct", "pct"),
    (r"no\s*longer\s*costs\s*mana",                   "skill_no_mana_cost", "flag"),
    (r"wave interval",                                "wave_interval_inc", "pct"),
    (r"summonable minions|max .*minions for the supported", "extra_max_minions_flat", "flat"),
    (r"can(no|')t be interrupted",                    "es_uninterruptible", "flag"),
]
_CAPTURE_COMPILED = [(re.compile(p), sk, vk) for p, sk, vk in _CAPTURE_RULES]
_CANNOT_AILMENTS = ("ignite", "frostbite", "numbed", "wilt")


def map_capture_line(line: SupportLine, level: int) -> list[StatContribution]:
    """Emit INERT capture contributions (stored, no DPS effect yet) for a flat utility/quantity line."""
    t = line.template
    # 'cannot inflict X (, Y, Z)' → one flag per named ailment
    if "cannot inflict" in t:
        return [StatContribution(f"cannot_inflict_{a}", 1.0, line.text, modeled=False)
                for a in _CANNOT_AILMENTS if a in t]
    for rx, stat_key, vk in _CAPTURE_COMPILED:
        if not rx.search(t):
            continue
        if vk == "flag":
            return [StatContribution(stat_key, 1.0, line.text, modeled=False)]
        v = (_level_value(line, level)[:1] or [None])[0] if line.scaling else _flat_number(line.text)
        if v is None:
            return []
        return [StatContribution(stat_key, v / 100.0 if vk == "pct" else v, line.text, modeled=False)]
    return []


# ── Conditional damage lines (gated / scaled by a condition value) ────────────
def _cnum(conds: dict, key: str) -> float:
    v = (conds or {}).get(key, 0.0)
    return float(v) if not isinstance(v, bool) else (1.0 if v else 0.0)


def _cbool(conds: dict, key: str) -> bool:
    return bool((conds or {}).get(key))


def _last_number(text: str) -> float:
    nums = re.findall(r"[+\-]?\s*\d+(?:[.,]\d+)?", text)
    return _eval_token(nums[-1].replace(" ", "")) if nums else 0.0


def _per_n(text: str) -> float:
    m = re.search(r"(?:every|per)\s+(\d+(?:\.\d+)?)", text, re.I)
    return float(m.group(1)) if m else 1.0


def _cap_frac(text: str) -> float | None:
    m = re.search(r"up to\s*[+\-]?\s*(\d+(?:[.,]\d+)?)\s*%", text, re.I)
    return float(m.group(1).replace(",", ".")) / 100.0 if m else None


def map_conditional_line(line: SupportLine, level: int, conds: dict | None) -> list[StatContribution]:
    """Damage lines whose magnitude depends on a condition value; [] if not conditional or gated off.
    `conds` is the build's condition_state ({key: value|bool})."""
    t = line.template
    has = lambda pat: re.search(pat, t) is not None       # glue-tolerant membership
    base = (_level_value(line, level)[:1] or [_last_number(line.text)])[0] / 100.0

    if has(r"cursed\s*enem"):                                # Grudge — gated on enemy_cursed
        return [StatContribution("dmg_additional", base, line.text)] if _cbool(conds, "enemy_cursed") else []

    if has(r"numbed\s*enem"):                                # Electric Punishment — flat + per numbed stack
        stacks = _cnum(conds, "numbed_stacks")
        if stacks <= 0 and not _cbool(conds, "enemy_numbed"):
            return []
        per_stack = _last_number(line.text) / 100.0          # the "+1%" per-stack literal
        return [StatContribution("dmg_additional", base + per_stack * stacks, line.text)]

    if has(r"fervor\s*rating"):                              # Attack Focus — per-fervor (dmg or crit rating)
        is_crit = has(r"critical\s*strike\s*rating")
        # A fervor line with no damage/crit payload (e.g. the "Gains N Fervor Rating on hit" generation
        # clause) is NOT a contribution — guard so it can't default to a bogus dmg_additional.
        if not is_crit and not has(r"additional\s*damage"):
            return []
        amt = base * (_cnum(conds, "fervor_rating") / _per_n(line.text))
        if amt == 0:
            return []
        return [StatContribution("crit_rating_inc" if is_crit else "dmg_additional", amt, line.text)]

    if has(r"stack\s*of\s*focus\s*blessing"):                # Overload — one additive bucket, capped
        amt = base * _cnum(conds, "focus_blessings")
        cap = _cap_frac(line.text)
        return [StatContribution("dmg_additional", min(amt, cap) if cap else amt, line.text)]

    if has(r"stack\s*of\s*ignite") and has(r"additional\s*ignite\s*damage"):  # Additional Ignite — per ignite stack, capped
        vals = _level_value(line, level)
        per_stack = (vals[0] if vals else 0) / 100.0
        cap = (vals[1] / 100.0) if len(vals) > 1 else _cap_frac(line.text)
        amt = per_stack * _cnum(conds, "ignite_stacks")
        return [StatContribution("ignite_dmg_additional", min(amt, cap) if cap else amt, line.text)]

    if has(r"every type of\s*ailment"):                      # Ailment Termination — (1+x)^count (multiplies)
        amt = (1.0 + base) ** _cnum(conds, "ailment_type_count") - 1.0
        return [StatContribution("dmg_additional", amt, line.text)]

    return []


# ── Auto-derived debuffs / buffs (set a condition; effect applied by the existing machinery) ──
@dataclass
class ConditionEffect:
    condition_key: str
    value: float                       # 1.0 = boolean true; >1 = stack count
    mode: str                          # "set_true" | "max"
    requires_dtype: str | None = None  # only when the supported skill deals this damage type
    requires_cond: str | None = None   # precondition that must already hold (e.g. enemy_cursed)
    source: str | None = None          # human label of what inflicts this (for the Config "auto" badge)


def map_autoderive_line(line: SupportLine) -> list[ConditionEffect]:
    """Lines that INFLICT a debuff / GRANT a buff → set the relevant condition (effect applied by the
    existing condition→effect machinery; soft proc-chance ignored, 100% assumed). [] otherwise."""
    t = line.template
    has = lambda pat: re.search(pat, t) is not None

    if has(r"inflicts?\s*numbed"):                           # High Voltage
        return [ConditionEffect("enemy_numbed", 1.0, "set_true", requires_dtype="lightning"),
                ConditionEffect("numbed_stacks", 1.0, "max", requires_dtype="lightning")]
    if has(r"inflicts?\s*frostbite"):                        # Glacial Freeze
        return [ConditionEffect("enemy_frostbitten", 1.0, "set_true", requires_dtype="cold")]
    if has(r"chance\s*to\s*paralyze"):                       # Grudge — needs enemy already Cursed
        return [ConditionEffect("enemy_paralyzed", 1.0, "set_true", requires_cond="enemy_cursed")]
    if has(r"buff\s*on\s*critical\s*strike"):               # Electric Overload (soft trigger → assume active)
        return [ConditionEffect("electric_overload", 1.0, "set_true")]
    if has(r"stack\s*of\s*buff") and has(r"standing\s*still"):                     # Willpower
        return [ConditionEffect("willpower_stacks", 6.0, "max", requires_cond="standing_still")]
    return []


# ── Authoritative stat mapping (delegates to engine.mod_parser — the SINGLE source of truth) ─────────
_STAT_PCT_UNIT: dict[str, bool] = {}


def _stat_is_pct(stat_key: str) -> bool:
    """Whether a stat's value is a percentage (unit '%') — so a level-scaled raw number is divided by 100."""
    if not _STAT_PCT_UNIT:
        from models.stat_meta import STAT_META
        for s, m in STAT_META.items():
            _STAT_PCT_UNIT[s.value] = (m.unit == "%")
    return _STAT_PCT_UNIT.get(stat_key, False)


_SUPPORT_TARGET_RE = re.compile(r'\s+(?:for|of)\s+(?:the supported|this) skill\b.*$', re.I)
_SUPPORT_TARGET_LEAD_RE = re.compile(r'^\s*the supported skill\s+', re.I)


def _strip_support_target(text: str) -> str:
    """Drop the 'for/of the (supported/this) skill' target phrase so the general parser sees the bare stat."""
    return _SUPPORT_TARGET_RE.sub('', _SUPPORT_TARGET_LEAD_RE.sub('', text or '')).strip()


def map_via_parser(line: SupportLine, level: int) -> list[StatContribution]:
    """AUTHORITATIVE flat-stat mapping: resolve the phrase → (stat_key, pool, type) via engine.mod_parser (one
    source of truth, so supports can't drift from gear/talents on the increased-vs-additional pool or the damage
    type), then apply the support's LEVEL-scaled value (a scaling line's text only carries an anchor value).
    Added-flat and conditional lines are handled by their bespoke passes BEFORE this is reached."""
    from engine.mod_parser import _parse_custom_mod_text
    parsed = _parse_custom_mod_text(_strip_support_target(line.text))
    if not parsed:
        return []
    if line.scaling:
        vals = _level_value(line, level)
        if not vals:
            return []
        v = vals[0]
        return [StatContribution(d["stat_key"], v / 100.0 if _stat_is_pct(d["stat_key"]) else v, line.text)
                for d in parsed]
    # Non-scaling line: the text carries the literal value, already pool/type-correct from the parser.
    return [StatContribution(d["stat_key"], d["amount"], line.text) for d in parsed]


def map_line(line: SupportLine, level: int, cat: str | None = None,
             conds: dict | None = None) -> list[StatContribution]:
    """Unified stat-contribution path. Bespoke passes first — category-routed added-flat, then conditional/
    scaled lines — then the AUTHORITATIVE general parser (engine.mod_parser), then the inert capture fallback
    for flags/utility the parser doesn't model yet. Returns [] for auto-derive lines (those produce
    ConditionEffects via map_autoderive_line). The general parser is the single mapping authority: support_mapper
    no longer keeps its own damage/stat table, so a support can't drift from gear/talents on pool or type."""
    return ((map_added_flat(line, level, cat) if cat else [])
            or map_conditional_line(line, level, conds)
            or map_via_parser(line, level)
            or map_capture_line(line, level))
