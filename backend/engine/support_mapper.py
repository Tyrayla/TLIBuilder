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


# ── Damage / stat line rules ──────────────────────────────────────────────────
# (regex on number-stripped template, stat_key(s), value_kind). stat_keys may be a tuple (one line →
# several stats, e.g. attack+cast speed). value_kind "pct" = percent→fraction (÷100); flats use the raw
# count. Added-flat `{cat}` lines (spell|attack) are handled separately once we wire the skill category.
_DMG_RULES: list[tuple[str, object, str]] = [
    (r"additional\s*lightning\s*damage for the supported", "lightning_dmg_additional", "pct"),
    (r"additional\s*fire\s*damage for the supported", "fire_dmg_additional", "pct"),
    (r"additional\s*cold\s*damage for the supported", "cold_dmg_additional", "pct"),
    (r"additional\s*elemental\s*damage for the supported", "elemental_dmg_additional", "pct"),
    (r"additional\s*physical\s*damage for the supported", "physical_dmg_additional", "pct"),
    (r"additional\s*area\s*damage for the supported", "area_dmg_additional", "pct"),
    (r"additional\s*melee\s*damage for the supported", "melee_dmg_additional", "pct"),
    (r"additional\s*trauma\s*damage for the supported", "trauma_dmg_additional", "pct"),
    (r"additional attack and cast speed for the supported", ("attack_speed_additional", "cast_speed_additional"), "pct"),
    (r"attack and cast speed for the supported", ("attack_speed_inc", "cast_speed_inc"), "pct"),
    (r"attack speed for the supported", "attack_speed_inc", "pct"),
    (r"cast speed for the supported", "cast_speed_inc", "pct"),   # Psychic Burst (cast-speed only)
    (r"critical strike rating for the supported", "crit_rating_inc", "pct"),
    (r"(additional )?skill area for the supported", "skill_area_inc", "pct"),
    (r"additional projectile speed for the supported", "projectile_speed_additional", "pct"),
    (r"steep\s*strike\s*chance", "steep_strike_chance", "pct"),
    # generic additional damage (LAST — after all typed/conditional rules). The first allows a PREFIX
    # but keeps the $ anchor so a trailing condition ("...when it lands a critical strike") still falls
    # through to the conditional handler. The second is the bare line with no "for the supported" suffix
    # (e.g. Activation Medium: Motionless), anchored both ends so it can't swallow typed/conditional lines.
    (r"additional damage for the supported skill$", "dmg_additional", "pct"),
    (r"^[+\-]?#\s*% additional damage$", "dmg_additional", "pct"),
]
_DMG_COMPILED = [(re.compile(p), sk, vk) for p, sk, vk in _DMG_RULES]


def map_damage_line(line: SupportLine, level: int, cat: str | None = None) -> list[StatContribution]:
    """Emit stat contributions for a modeled damage/stat line; [] if no damage rule matches.
    `cat` is the supported skill's category ('spell'|'attack') for added-flat lines (not used yet)."""
    for rx, stat_keys, vk in _DMG_COMPILED:
        if not rx.search(line.template):
            continue
        vals = _level_value(line, level) if line.scaling else _flat_dmg_value(line.text)
        if not vals:
            return []
        amt = vals[0] / 100.0 if vk == "pct" else vals[0]
        keys = stat_keys if isinstance(stat_keys, tuple) else (stat_keys,)
        return [StatContribution(stat_key=k, amount=amt, text=line.text) for k in keys]
    return []


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


def map_line(line: SupportLine, level: int, cat: str | None = None,
             conds: dict | None = None) -> list[StatContribution]:
    """Unified stat-contribution path: damage → added-flat → conditional → capture. Returns [] for
    unmapped/skip and for auto-derive lines (those produce ConditionEffects via map_autoderive_line)."""
    return (map_damage_line(line, level, cat)
            or (map_added_flat(line, level, cat) if cat else [])
            or map_conditional_line(line, level, conds)
            or map_capture_line(line, level))
