from __future__ import annotations
import math
from collections import defaultdict
from dataclasses import dataclass, field, replace
from typing import Callable, Literal

from engine import uptime
from engine.models import BuildSource
from engine.consumption import floored_consumed
from engine.affix_identity import affix_identity
from engine.modifier_lines import pool_identity
from engine.skill_resolver import ResolvedSkill
from engine.tick import TICK_RATE, cap_rate, period_ticks, rate_from_ticks
from engine.constants import DAMAGE_TYPES as _DAMAGE_TYPES, ELEMENTAL
from models.stat_meta import STAT_META

# ── Module-level stat lookups built from STAT_META ────────────────────────────

# Hit damage increased/reduced stats: (key, frozenset_of_lowercase_tags)
# Empty frozenset = universal (applies to every skill and every damage type)
_HIT_INC_STATS: list[tuple[str, frozenset]] = [
    (stat.value, frozenset(meta.tags))
    for stat, meta in STAT_META.items()
    if meta.pipeline_stage == "increased_reduced"
    and "hit" in meta.affects
]

# Critical Strike Damage is one additive pool on top of the 1.5x base crit multiplier (TLI models crit
# damage additively, not as a separate multiplicative "additional" pool). All crit-damage stats feed it,
# tag-filtered to the skill — generic crit_dmg, attack/spell crit_dmg, and element crit_dmg matching the
# skill's damage. (Previously unwired: crit_mult read an unpopulated "crit_damage" key.)
_CRIT_DMG_STATS: list[tuple[str, frozenset]] = [
    (stat.value, frozenset(meta.tags))
    for stat, meta in STAT_META.items()
    if meta.pipeline_stage == "crit_damage" and "hit" in meta.affects
]

# Critical Strike RATING pools (the chance side), tag-filtered to the skill like _CRIT_DMG_STATS.
# Split into the % pool (inc + additional, scales the whole CSR) and the flat pool (adds raw CSR).
# Excludes: weapon_crit_rating_flat (scaled by gear sub-mods, handled separately), the attack_crit_rating
# gear/mh sub-mods (decimals, not flat/inc), and minion/sentry/spirit_magi (other subsystems).
_CRIT_RATING_INC_STATS: list[tuple[str, frozenset]] = [
    (stat.value, frozenset(meta.tags))
    for stat, meta in STAT_META.items()
    if meta.pipeline_stage == "crit_rating" and "hit" in meta.affects
    and (stat.value.endswith("_inc") or stat.value.endswith("_additional"))
    and not stat.value.startswith(("minion_", "sentry_", "spirit_magi_"))
]
_CRIT_RATING_FLAT_STATS: list[tuple[str, frozenset]] = [
    (stat.value, frozenset(meta.tags))
    for stat, meta in STAT_META.items()
    if meta.pipeline_stage == "crit_rating" and "hit" in meta.affects
    and stat.value.endswith("_flat") and stat.value != "weapon_crit_rating_flat"
    and not stat.value.startswith(("minion_", "sentry_", "spirit_magi_"))
]

# Double-damage chance: probability to deal 2× on a hit → expected-value multiplier (1 + Σchance, capped).
_DOUBLE_DMG_STATS: list[tuple[str, frozenset]] = [
    (stat.value, frozenset(meta.tags))
    for stat, meta in STAT_META.items()
    if meta.pipeline_stage == "double_damage" and "hit" in meta.affects
]
# Triple / Quadruple damage chance — tag-filtered like double. Per-hit you can only get the HIGHEST tier
# that procs (check quad → triple → double); expected-value multiplier folds all three (Tyra model).
_TRIPLE_DMG_STATS: list[tuple[str, frozenset]] = [
    (stat.value, frozenset(meta.tags))
    for stat, meta in STAT_META.items()
    if meta.pipeline_stage == "triple_damage" and "hit" in meta.affects
]
_QUAD_DMG_STATS: list[tuple[str, frozenset]] = [
    (stat.value, frozenset(meta.tags))
    for stat, meta in STAT_META.items()
    if meta.pipeline_stage == "quadruple_damage" and "hit" in meta.affects
]

# Additional stats that require special handling and are excluded from the generic pool.
# Each entry notes why it can't be treated as a simple always-on multiplier.
_DEFERRED_ADDITIONAL: dict[str, str] = {
    "barrage_dmg_per_wave_inc":      "Barrage mechanic — scales per wave fired, not a flat multiplier",
    "combo_finisher_additional":     "Combo finisher only — applies to finisher hits, not all hits; combo damage model NYI",
    "multistrike_increasing_dmg_inc":"Multistrike mechanic — stacks per successive hit in a multistrike chain, not a flat multiplier",
    "post_mobility_dmg_additional":  "Requires 'mobility skill cast recently' condition boolean (not yet created)",
    "two_handed_base_dmg_additional":"May apply to base damage before inc/additional; stacking position unconfirmed — deferred",
}

# Additional-damage stats applied by a FORM-SCOPED multiplier (not the generic hit pool), so they must be
# excluded here to avoid double-counting. Steep Strike Additional Damage applies ONLY to the Steep Strike
# hit form (see calculate_offense `form_add_mult`) — it is consumed, just not a generic all-hits factor.
# Form-scoped additional-damage stats: applied ONLY to their specific hit form, never to the generic pool
# (so they don't leak onto every skill). steep_strike is wired (read when the skill has a steep-strike form);
# sweep_slash is a Berserking-Blade form mechanic whose legendary mod line isn't wired yet — kept out of the
# generic pool so it can't wrongly apply/badge until it gets its own form-scoped reader.
_FORM_SCOPED_ADDITIONAL: frozenset = frozenset({"steep_strike_additional_dmg", "sweep_slash_additional_dmg"})

# Hit damage additional multiplier stats — each is an independent multiplicative pool.
# Deferred stats (see _DEFERRED_ADDITIONAL) are excluded and listed in the NYI output.
_HIT_ADDITIONAL_STATS: list[tuple[str, frozenset]] = [
    (stat.value, frozenset(meta.tags))
    for stat, meta in STAT_META.items()
    if meta.pipeline_stage == "additional"
    and "hit" in meta.affects
    and stat.value not in _DEFERRED_ADDITIONAL
    and stat.value not in _FORM_SCOPED_ADDITIONAL
]

# Attack speed additional pools (tags read directly from stat_meta)
_APS_ADDITIONAL_STATS: list[tuple[str, frozenset]] = [
    (stat.value, frozenset(meta.tags))
    for stat, meta in STAT_META.items()
    if stat.value in ("attack_speed_additional", "combo_starter_attack_speed_additional")
]

# Cast speed additional pools — the spell hit-rate analog of _APS_ADDITIONAL_STATS.
_CAST_ADDITIONAL_STATS: list[tuple[str, frozenset]] = [
    (stat.value, frozenset(meta.tags))
    for stat, meta in STAT_META.items()
    if stat.value in ("cast_speed_additional", "combo_starter_cast_speed_additional")
]

# Skill level bonus stats — each adds integer levels to the effective skill level.
# Empty frozenset = no tag requirement (applies to all active skills).
# Non-empty = applies only when skill has ANY of the listed tags.
# main_skill_level is handled separately via is_main_skill flag in calculate_offense.
_SKILL_LEVEL_STATS: list[tuple[str, frozenset]] = [
    ("all_skill_level",        frozenset()),
    ("active_skill_level",     frozenset()),
    ("attack_skill_level",     frozenset({"attack"})),
    ("spell_skill_level",      frozenset({"spell"})),
    ("melee_skill_level",      frozenset({"melee"})),
    ("projectile_skill_level", frozenset({"projectile"})),
    ("physical_skill_level",   frozenset({"physical"})),
    ("fire_skill_level",       frozenset({"fire"})),
    ("cold_skill_level",       frozenset({"cold"})),
    ("lightning_skill_level",  frozenset({"lightning"})),
    ("erosion_skill_level",    frozenset({"erosion"})),
]


DAMAGE_TYPES = _DAMAGE_TYPES   # shared (engine.constants); re-exported for callers that import it from here
# "Elemental" = Fire/Cold/Lightning only (Erosion and Physical are NOT elemental). An "elemental"-tagged
# damage stat (e.g. elemental_dmg_inc) applies to exactly these three via the per-type tag match below.
_ELEMENTAL_DMG_TYPES = ELEMENTAL
# Tags that mark a damage stat as TYPE-SPECIFIC (excluded from the generic/"All" pool). Includes the
# pseudo-tag "elemental" so elemental_dmg_inc/additional are treated per-type, not as a uniform multiplier.
_DTYPE_TAG_SET = frozenset(DAMAGE_TYPES) | {"elemental"}


# EXCLUSIVE skill-type tags: a stat carrying one applies ONLY to skills that ALSO carry it — it can't be
# satisfied by another shared tag via the OR-match below. 'minion' is the verified case (minion_spell_dmg_
# additional must NOT leak onto a non-minion spell). MORE tags (e.g. sentry/trap/warcry subsystems) likely
# belong here too, but each needs in-game verification before adding — extend this set as that's confirmed.
_EXCLUSIVE_SKILL_TAGS: frozenset = frozenset({"minion"})


def _skill_gate(tags: frozenset, mod_tags: set) -> bool:
    """A stat's SKILL-TYPE/subsystem tags (attack/spell/minion/sentry/projectile/…) must match the skill if
    it has any. This keeps a minion-scoped stat like minion_lightning_dmg_inc OUT of a non-minion skill's
    pools even though it shares the 'lightning' damage-type tag (the bug: OR-matching applied it anyway).

    An EXCLUSIVE tag (see _EXCLUSIVE_SKILL_TAGS) is AND-required: present on the stat ⇒ it must be present on
    the skill, regardless of other shared tags. So minion_spell_dmg_additional ({minion, spell}) no longer
    leaks onto a non-minion spell via the shared 'spell' tag."""
    skill = tags - _DTYPE_TAG_SET
    if not skill:
        return True
    if (skill & _EXCLUSIVE_SKILL_TAGS) - mod_tags:
        return False
    return bool(skill & mod_tags)


def _applies_to_dtype(tags: frozenset, dtype_tag: frozenset, mod_tags: set) -> bool:
    """A damage modifier applies to a damage type iff BOTH roles hold: its damage-type tags match that type
    (or it has none → applies to all types) AND its skill-type tags match the skill (or it has none). So
    "Elemental Damage" (dmg-only) hits the elements on any skill; "Minion Lightning Damage" (dmg+skill) hits
    Lightning only on minion skills; generic/attack mods (skill-only) hit every type on a matching skill."""
    dmg = tags & _DTYPE_TAG_SET
    return ((not dmg) or bool(dmg & dtype_tag)) and _skill_gate(tags, mod_tags)

# Innate base Critical Strike Rating for spells (500 CSR = 5% base crit at 0 gear). Tyra-confirmed.
_BASE_SPELL_CRIT_RATING = 500.0

# Main-stat Damage Bonus: each point of a skill's main-stat attribute grants +0.5% damage. Multi-main-
# stat skills SUM the attribute totals before applying. Generic (all damage types), its OWN additional
# (multiplicative) pool — folded into the additional stage. Source: TLI Help DB.
_MAIN_STAT_DAMAGE_PER_POINT = 0.005

# Per-affix "additional" pooling lookups (Option A — see docs/ADDITIONAL_DAMAGE_POOLING.md).
# Scope of this pass: OUTGOING HIT damage only. FUTURE (per-affix rework), still pooled by stat-key
# elsewhere: attack-speed additional (below); damage-taken-additional family (enemy debuffs —
# defense side / engine.guards immunity tripwire). Also FUTURE: "(multiplies)" per-stack compounding
# — the keyword IS on 24+ real legendary affixes (e.g. Marksman Bracers "additional damage dealt by
# Horizontal Projectiles after each Jump (multiplies)"), but none resolve to a stat yet (all NYI), so
# the engine never reaches that path today. When such an affix is modelled, its per-stack scaling must
# compound as (1+per)^stacks-1 instead of the default per×stacks.
_HIT_ADDITIONAL_TAGS: dict[str, frozenset] = {key: tags for key, tags in _HIT_ADDITIONAL_STATS}
_HIT_ADDITIONAL_KEYS: frozenset[str] = frozenset(_HIT_ADDITIONAL_TAGS)


def _build_additional_factors(source: BuildSource) -> list[tuple[float, frozenset, str]]:
    """Per-affix additional factors as (amount, tags, stat_key).

    Each DISTINCT affix (by normalized text) becomes its own multiplicative factor; POSITIVE
    contributions sharing one identity SUM into a single factor, each NEGATIVE contribution is its
    own factor (so distinct/stacked debuffs multiply, never summing past -100% to immunity).
    Untracked contributions (added via BuildSource.add() with no source_log entry — used by tests)
    are reconciled by stat-key, preserving the old per-key pooling for that case. consumed_stats is
    NOT recorded here (it's recorded in _additional_product only for keys that actually apply).
    """
    factors: list[tuple[float, frozenset, str]] = []
    pos: dict[tuple[str, str], float] = defaultdict(float)
    neg: dict[tuple[str, str], list[float]] = defaultdict(list)
    tracked: dict[str, float] = defaultdict(float)
    _idx = getattr(source, "identity_index", None)

    for e in source.source_log:
        if e.stat not in _HIT_ADDITIONAL_KEYS:
            continue
        # "Damage Enhancement" affixes (e.g. Tangle/Combo/Focus Damage Enhancement) are ADDED TOGETHER into a
        # single additional factor (Help DB) rather than each being its own ×(1+x) factor — so pool them by
        # stat-key alone (shared identity), not by text, so two sources sum (50%+50% → +100%) instead of
        # multiplying. Regular additional mods keep their per-text identity (distinct sources multiply).
        ident = (e.stat, "" if e.stat.endswith("_enhancement_additional") else pool_identity(e, _idx))
        if e.amount < 0:
            neg[ident].append(e.amount)
        else:
            pos[ident] += e.amount
        tracked[e.stat] += e.amount

    for (stat_key, _ident), amt in pos.items():
        factors.append((amt, _HIT_ADDITIONAL_TAGS[stat_key], stat_key))
    for (stat_key, _ident), amts in neg.items():
        for a in amts:
            factors.append((a, _HIT_ADDITIONAL_TAGS[stat_key], stat_key))

    # Reconcile add()-only contributions per stat-key (raw read, no consumed_stats side effect).
    for stat_key, tags in _HIT_ADDITIONAL_STATS:
        raw = sum(v for s, v in source._entries if s == stat_key)
        remainder = raw - tracked.get(stat_key, 0.0)
        if abs(remainder) > 1e-12:
            factors.append((remainder, tags, stat_key))
    return factors


def _record_applicable_keys(source: BuildSource, keyed_tags, applies: Callable[[frozenset], bool]) -> None:
    """Mark every additional-pool key whose tags satisfy `applies` as consumed — even with no contribution —
    so its modifiers badge Consumed consistently (not Inactive→Consumed depending on whether something else
    feeds the pool). ONE shared rule for ALL additional pools (hit damage AND attack/cast speed) so they can
    never drift out of sync: any pool that wants consistent badges calls this with its (key, tags) list and
    its apply-predicate. `keyed_tags` is an iterable of (stat_key, tags)."""
    if not source._recording:
        return
    for key, tags in keyed_tags:
        if applies(tags):
            source.consumed_stats.add(key)


def _additional_product(
    source: BuildSource,
    factors: list[tuple[float, frozenset, str]],
    predicate: Callable[[frozenset], bool],
) -> float:
    """Product of (1 + amount) over factors whose tags satisfy predicate. Records consumed_stats for every
    skill-applicable additional key — INCLUDING ones with no current contribution — so an "additional damage"
    modifier badges consistently (Consumed) instead of flipping Inactive→Consumed depending on whether
    anything else currently feeds that pool. This mirrors the increased pools, which already record every
    predicate-passing key via source.total(). Type-specific keys that don't apply to the skill/damage type
    still aren't recorded (they remain correctly Inactive)."""
    p = 1.0
    for amount, tags, stat_key in factors:
        if predicate(tags):
            p *= (1.0 + amount)
    _record_applicable_keys(source, _HIT_ADDITIONAL_STATS, predicate)
    return p


def _speed_additional_product(source: BuildSource, keys, skill_tags_lower: set[str]) -> float:
    """Per-affix multiplicative product for additional attack/cast speed: each DISTINCT source (by affix
    identity) is its own ×(1+x) factor; same-identity positives sum. Verified in-game — 10% (Dual Wield)
    + 22.5% (Quick Decision) on a 1.5/s base = ×1.10×1.225 = 2.02/s, NOT ×1.325. add()-only contributions
    (no source_log text — used by tests) reconcile per key into a single factor."""
    tags_for = dict(keys)
    keyset = set(tags_for)
    pos: dict[tuple[str, str], float] = defaultdict(float)
    tracked: dict[str, float] = defaultdict(float)
    _idx = getattr(source, "identity_index", None)
    for e in source.source_log:
        if e.stat not in keyset:
            continue
        tags = tags_for[e.stat]
        if tags and not (tags & skill_tags_lower):
            continue
        pos[(e.stat, pool_identity(e, _idx))] += e.amount
        tracked[e.stat] += e.amount
    p = 1.0
    for amt in pos.values():
        p *= (1.0 + amt)
    for key, tags in keys:
        if tags and not (tags & skill_tags_lower):
            continue
        raw = sum(v for s, v in source._entries if s == key)
        remainder = raw - tracked.get(key, 0.0)
        if abs(remainder) > 1e-12:
            p *= (1.0 + remainder)
    # Record skill-applicable speed-additional keys (shared rule with the hit pool). These pools are read via
    # source_log, not source.total, so without this they'd never enter consumed_stats and would always badge
    # Inactive despite contributing (the Quick Decision report). Only the relevant pool runs per skill type
    # (cast for spells, attack for attacks), so this never cross-marks.
    _record_applicable_keys(source, keys, lambda tags: not tags or bool(tags & skill_tags_lower))
    return p


def additional_total_product(source: BuildSource, key: str) -> float:
    """Π(1 + amount) over DISTINCT affix sources of one additional-pool stat (same-identity positives sum),
    with a total() fallback for untracked contributions (tests add() with no source_log text). Used for Spell
    Burst Charge Speed additional, which combines per-source like the speed pools (Tyra: 2 / (1+inc) / Π(1+add_i))."""
    entries = [e for e in source.source_log if e.stat == key]
    if not entries:
        return 1.0 + source.total(key)
    pos: dict[str, float] = defaultdict(float)
    _idx = getattr(source, "identity_index", None)
    for e in entries:
        pos[pool_identity(e, _idx)] += e.amount
    p = 1.0
    for amt in pos.values():
        p *= (1.0 + amt)
    return p


def compute_spell_burst_rate(source: BuildSource, sps: float, M: int, auto: bool) -> float:
    """Bursts-per-second (the burst TRIGGER rate — how often a burst sequence fires, NOT the M+1 casts within one).

    Standalone mirror of the rate math inside calculate_offense's Spell Burst block — KEEP IN SYNC with it. Used by
    engine.compute to key burst-activation sustain (mana lost / life restored per trigger) and the per-recent-burst
    AS/CS feedback off the burst rate, both of which must run BEFORE offense. Returns 0.0 when the skill isn't
    bursting (M < 1)."""
    if M < 1:
        return 0.0
    charge_inc = source.total("spell_burst_charge_speed_inc")
    charge_factor = max(1e-6, (1.0 + charge_inc) * additional_total_product(source, "spell_burst_charge_speed_additional"))
    T = 2.0 / charge_factor
    surging_rate = sps * source.total("spell_burst_chance_gain_stacks_flat")
    T_eff = min(T, M / surging_rate) if (surging_rate > 0.0 and M > 0) else T
    charge_ticks = period_ticks(T_eff)
    if not auto:
        if source.total("spell_burst_auto_trigger_flag") > 0:
            auto = True
        else:
            _thr = source.total("spell_burst_auto_charge_threshold")
            if _thr > 0 and (1.0 + charge_inc) >= _thr:
                auto = True
    if auto:
        rate = rate_from_ticks(charge_ticks)
    elif sps <= 0.0:
        return 0.0
    else:
        ct = max(1, round(TICK_RATE / sps))
        rate = TICK_RATE / (math.ceil(charge_ticks / ct) * ct)
    return min(rate, float(TICK_RATE))


def compute_demolisher_rate(source: BuildSource, cast_rate: float, base_restore: float,
                            mode: str = "manual", rhythm_interval: float = 0.0) -> dict:
    """Demolisher Charge charged-rate + the bidirectional restoration-vs-cadence breakpoint.

    Standalone mirror of the rate reasoning used inside calculate_offense's demolisher block — KEEP IN SYNC.
    A Demolisher skill holds at most ONE charge, regained every `restoration` seconds (the timer runs only
    while at 0). Casting while holding the charge CONSUMES it to add the secondary explosion (the primary
    fissure lands on every cast regardless).

    `cast_rate` is the skill's RESOLVED cast/trigger rate (from compute_skill_rates: manual APS, a trigger-medium
    cadence, or the Wind Rhythm rate) — Demolisher is now a generic CONSUMER of it. The cadence = 1/cast_rate.
      restoration = base_restore / (1 + Σ demolisher_charge_speed_inc)   [INCREASED pool ONLY].
    Every cast is charged iff restoration ≤ cadence; else a charge is ready only every `restoration` s →
    charged_rate = min(cast_rate, 1/restoration). Breakpoint (every-cast-charged) needs (1 + inc) ≥
    base/cadence → `restore_to_sustain` / `cdr_droppable`. `mismatch` = the secondary can't fire every cast.
    Returns 0-rates when base_restore ≤ 0 (skill isn't a Demolisher skill)."""
    inc = source.total("demolisher_charge_speed_inc")
    restoration_time = base_restore / (1.0 + inc) if base_restore > 0 else 0.0
    if base_restore <= 0:
        return {"mode": mode, "cast_rate": 0.0, "charged_rate": 0.0, "restoration_time": 0.0,
                "rhythm_interval": rhythm_interval, "charge_speed_inc": inc, "base_restore": base_restore,
                "mismatch": False, "restore_to_sustain": 0.0, "cdr_droppable": 0.0,
                "under_breakpoint": False, "over_breakpoint": False}
    cadence = (1.0 / cast_rate) if cast_rate > 0 else 0.0
    charged_rate = min(cast_rate, 1.0 / restoration_time) if restoration_time > 0 else cast_rate
    # Breakpoint in INCREASED charge-speed terms: sustain needs (1 + inc) ≥ base/cadence.
    inc_needed = (base_restore / cadence - 1.0) if cadence > 0 else 0.0
    mismatch = restoration_time > cadence + 1e-9
    return {
        "mode": mode,
        "cast_rate": cast_rate,
        "charged_rate": charged_rate,
        "restoration_time": restoration_time,
        "rhythm_interval": rhythm_interval,
        "charge_speed_inc": inc,
        "base_restore": base_restore,
        "mismatch": mismatch,
        "restore_to_sustain": max(0.0, inc_needed - inc),   # more INCREASED charge speed to reach every-cast-charged
        "cdr_droppable": max(0.0, inc - inc_needed),         # INCREASED charge speed droppable while still sustaining
        "under_breakpoint": inc < inc_needed - 1e-9,
        "over_breakpoint": inc > inc_needed + 1e-9,
    }


def compute_wind_rhythm_rate(source: BuildSource, base_cooldown: float, wind_bonus: float) -> dict:
    """Wind Rhythm trigger rate — a server-tick breakpoint mechanic (reuses tick.py, like Spell Burst / Tangle).

    The medium triggers off a per-tier base cooldown, sped by Cooldown Recovery + a share (`wind_bonus`) of the
    supported skill's Cast Speed (Tyra-confirmed via the wrc-six calculator):
      final_cast = cast_speed_inc × (1 + cast_speed_additional)     # additional cast speed MULTIPLIES the increased
      raw = base_cooldown / (1 + cdr_speed_inc + wind_bonus × final_cast) / (1 + cdr_speed_additional)
      server = ceil(raw × 30) / 30   → rate = 30 / ceil(raw × 30)
    Returns the rate + tick/cast-time detail + a breakpoint scan (CDR%, Cast-speed%, Wind-bonus% to the next
    faster tick), for the helper panel. Returns 0 rate when base_cooldown ≤ 0 (not Wind Rhythm)."""
    if base_cooldown <= 0:
        return {"rate": 0.0, "ticks": 0, "raw_cast_time": 0.0, "server_cast_time": 0.0,
                "base_cooldown": 0.0, "wind_bonus": 0.0, "cdr_to_next": 0.0, "cast_to_next": 0.0, "wind_to_next": 0.0}
    cast_inc = source.total("cast_speed_inc")
    cast_add = source.total("cast_speed_additional")
    cdr_inc = source.total("cdr_speed_inc")
    cdr_add = source.total("cdr_speed_additional")

    def _raw(ci, ca, di, da, wb):
        final_cast = ci * (1.0 + ca)
        return base_cooldown / max(1.0 + di + wb * final_cast, 1e-6) / max(1.0 + da, 1e-6)

    raw = _raw(cast_inc, cast_add, cdr_inc, cdr_add, wind_bonus)
    ticks = period_ticks(raw)
    rate = rate_from_ticks(ticks)

    # Breakpoint scan: the increment of each lever that first drops to a faster (fewer-tick) period.
    def _to_next(kind: str) -> float:
        if ticks <= 1:
            return 0.0
        d = 0.0
        while d < 5.0:
            d += 0.01
            r2 = (_raw(cast_inc + d, cast_add, cdr_inc, cdr_add, wind_bonus) if kind == "cast"
                  else _raw(cast_inc, cast_add, cdr_inc + d, cdr_add, wind_bonus) if kind == "cdr"
                  else _raw(cast_inc, cast_add, cdr_inc, cdr_add, wind_bonus + d))
            if period_ticks(r2) < ticks:
                return d
        return 0.0

    return {
        "rate": rate, "ticks": ticks, "raw_cast_time": raw, "server_cast_time": ticks / float(TICK_RATE),
        "base_cooldown": base_cooldown, "wind_bonus": wind_bonus,
        "cdr_to_next": _to_next("cdr"), "cast_to_next": _to_next("cast"), "wind_to_next": _to_next("wind"),
    }

# ── Calculation-target defense (the "dummy") ──────────────────────────────────
# Baseline mitigation the DPS-vs-target number is computed against. Named (not magic numbers) and
# centralized so they can be exposed as tweakable target settings later. Per the training dummy:
#   • Armor gives 50% damage reduction vs PHYSICAL; only 60% of armor applies to non-physical types,
#     so the same armor yields 50% × 0.60 = 30% reduction vs fire/cold/lightning/erosion.
#   • Resistance is 30% elemental (fire/cold/lightning) and 30% erosion.
# TODO(target-config): surface these per-target via the request so the user can tweak the calc target.
TARGET_ARMOR_MITIGATION = 0.50          # physical damage reduction provided by armor
TARGET_NONPHYS_ARMOR_FACTOR = 0.60      # fraction of armor that applies to non-physical damage
TARGET_ELEMENTAL_RESIST = 0.30          # fire / cold / lightning
TARGET_EROSION_RESIST = 0.30            # erosion
# Enemy-Count weight of the calc target for "for each enemy" lines (Normal/Magic 1, Rare 2, Boss 5). The
# training dummy is a Boss → 5 (e.g. Rosa Unbreakable Stand's per-enemy damage). TODO(target-config): vary by
# the selected target type.
TARGET_ENEMY_COUNT_WEIGHT = 5


def _target_effective(source: BuildSource, dtype: str) -> tuple[float, float]:
    """(effective_armor_reduction, effective_resistance) for `dtype` after the attacker's penetration.

    Penetration deducts from the target's effective armor/resistance and may drive either negative — at
    which point the reduction becomes an amplification (Help DB: both Armor DMG Mitigation Penetration and
    Resistance Penetration reduce the defender's effective value, can go negative, then add to damage
    taken). Penetration is stored positive and subtracted; `all_resistance_reduction` is a signed delta
    (negative when it lowers resistance) and applies to all elemental + erosion resists. Physical has no
    resistance term."""
    tc = getattr(source, "target_config", None) or {}     # editable dummy stats (fractions); else the constants
    armor = tc.get("armor", TARGET_ARMOR_MITIGATION)
    armor_pen = source.total("armor_pen")
    if dtype == "physical":
        return armor - armor_pen, 0.0
    eff_armor = armor * TARGET_NONPHYS_ARMOR_FACTOR - armor_pen
    all_res_red = source.total("all_resistance_reduction")          # signed (negative when reducing res)
    if dtype == "erosion":
        base_res = tc.get("erosion_res", TARGET_EROSION_RESIST)
        eff_resist = base_res - source.total("erosion_pen") + all_res_red
    else:  # fire / cold / lightning — elemental_pen stacks on top of the per-type pen
        base_res = tc.get(f"{dtype}_res", TARGET_ELEMENTAL_RESIST)
        eff_resist = (base_res - source.total(f"{dtype}_pen")
                      - source.total("elemental_pen") + all_res_red)
    return eff_armor, eff_resist


def _target_mitigation(source: BuildSource, dtype: str) -> float:
    """Per-type outgoing-damage multiplier vs the calculation target. Zero penetration reproduces the prior
    constants exactly (physical 0.50, others 0.49)."""
    eff_armor, eff_resist = _target_effective(source, dtype)
    return (1.0 - eff_armor) * (1.0 - eff_resist)


# Where the target's base mitigation/resistance comes from (so the UI shows the baseline, not magic numbers).
TARGET_SOURCE = "Lvl 85 Dummy"


def target_profile(source: BuildSource) -> dict:
    """The calculation target's defenses, with each step SEPARATED so the UI can show derivation:
      base          → the dummy baseline constant (TARGET_*),
      reduction     → enemy-resistance REDUCTION (lowers the enemy's actual resistance; a debuff),
      resist        → the enemy's effective resistance = base + reduction (what a resistance MULTIPLIER
                      would scale — penetration is NOT folded in here),
      pen           → penetration, applied SEPARATELY at hit time (the attacker ignores this much),
      effective     → resist − pen, the value actually used in the damage calc (negative = amplified).
    Keeping pen out of `resist` is deliberate: pen and resistance-reduction are different mechanics, and
    folding pen into the base would mis-scale any future enemy-resistance multiplier. All fractions."""
    tc = getattr(source, "target_config", None) or {}     # editable dummy stats (fractions); else the constants
    armor = tc.get("armor", TARGET_ARMOR_MITIGATION)
    level = tc.get("level", 85)
    armor_pen = source.total("armor_pen")
    all_red = source.total("all_resistance_reduction")   # signed; negative lowers enemy resistance

    def res_parts(t: str) -> dict:
        base = (tc.get("erosion_res", TARGET_EROSION_RESIST) if t == "erosion"
                else tc.get(f"{t}_res", TARGET_ELEMENTAL_RESIST))
        pen = (source.total("erosion_pen") if t == "erosion"
               else source.total(f"{t}_pen") + source.total("elemental_pen"))
        resist = base + all_red          # enemy's actual resistance (after reductions; multipliers go here)
        return {"base": base, "reduction": all_red, "pen": pen, "resist": resist, "effective": resist - pen}

    # Per-stat penetration SOURCES for the panel breakdown. Penetration is often skill-SCOPED (e.g. Awakening
    # Skull's attack-only Armor Pen), and scoped contributions never enter the global stat_map — so the breakdown's
    # stat_map lookup finds nothing. We read them straight off this (already skill-materialized) source's
    # source_log, which carries base PLUS the matching scoped entries, so every source that produced the displayed
    # pen shows up. Keyed by the stat the panel rows ask for via penKeys.
    _PEN_KEYS = ("armor_pen", "elemental_pen", "fire_pen", "cold_pen", "lightning_pen", "erosion_pen")
    pen_sources: dict[str, list] = {}
    for e in source.source_log:
        if e.stat in _PEN_KEYS:
            pen_sources.setdefault(e.stat, []).append({
                "source_type": e.source_type, "label": e.label, "text": e.text,
                "source_name": e.source_name, "amount": e.amount,
            })

    return {
        "source": f"Lvl {level} Dummy",
        "armor": {
            "base_phys": armor,
            "base_nonphys": armor * TARGET_NONPHYS_ARMOR_FACTOR,
            "pen": armor_pen,
            "effective_phys": armor - armor_pen,
            "effective_nonphys": armor * TARGET_NONPHYS_ARMOR_FACTOR - armor_pen,
        },
        "resists": {t: res_parts(t) for t in ("fire", "cold", "lightning", "erosion")},
        # Raw pen totals (kept for back-compat / debugging).
        "pen": {
            "armor": armor_pen,
            "all_resistance_reduction": all_red,
            "elemental": source.total("elemental_pen"),
            "fire": source.total("fire_pen"),
            "cold": source.total("cold_pen"),
            "lightning": source.total("lightning_pen"),
            "erosion": source.total("erosion_pen"),
        },
        # Per-stat source breakdown for the pen rows (incl. skill-scoped pens absent from the global stat_map).
        "pen_sources": pen_sources,
    }


def _enemy_vuln_mult(source: BuildSource, dtype: str, is_spell: bool = False) -> float:
    """Enemy-vulnerability stage: 'the enemy takes more <type> damage' effects, applied as a final
    per-type multiplier on OUTGOING damage — deliberately NOT in the attacker's additional pool, so
    distinct vulnerability sources combine on their own rule and type-scoping stays honest.

    Distinct sources combine MULTIPLICATIVELY (ship default). NOTE: the in-game wording splits these into
    an INCREASED pool (Paralysis: "Increases damage taken") and an ADDITIONAL pool (Frail / Infiltration /
    Numbed: "Additionally increases … taken"); modelling that split (increases sum, additionals multiply)
    needs direct in-game testing and is FLAGGED for later. Sources today, all baked by the aggregator from
    their enemy condition: Paralysis (global), Numbed (lightning), Frail (Spell-form), Infiltration (per
    element type). NOT the defensive dmg_taken family (incoming damage / immunity tripwire) — this is
    outgoing amplification.
    """
    mult = 1.0 + source.total("paralysis_dmg_taken")        # global
    mult *= 1.0 + source.total("no_guard_dmg_taken")        # global (Rosa Desperation — No Guard)
    mult *= 1.0 + source.total("knockback_dmg_taken")       # global (Howling Gale — Headwind; gated by hook on enemy_knocked_back)
    mult *= 1.0 + source.total("tide_dmg_taken")            # global (Selena Sing with the Tide; gated on enemy_on_tide, × Tide Effect)
    mult *= 1.0 + source.total("enemy_nearby_dmg_taken_additional")  # "additional damage taken by enemies within Nm" (Licorice Note Scattered Spore; assume in range)
    if dtype == "cold":
        mult *= 1.0 + source.total("frostbite_cold_taken")  # Frostbite (+Condensed Frost) — baked in aggregator
    if dtype == "lightning":
        mult *= 1.0 + source.total("numbed_lightning_taken")
    if dtype in ("fire", "cold", "lightning"):              # Infiltration — element-typed
        mult *= 1.0 + source.total(f"{dtype}_infiltration_taken")
    if is_spell:                                            # Frail — Spell-form (all damage of a Spell skill)
        mult *= 1.0 + source.total("frail_spell_taken")
    # Curses (applied curse skill, scaled by Curse Effect in apply_curses): the per-type pool keys off the FINAL
    # converted dtype — so an "increased Lightning Damage taken" curse does nothing once 100% of the lightning is
    # converted to cold. hit_curse_taken (Timid) is all hit damage. Distinct curse TYPES multiply (separate
    # factors); same curse is deduped to one source upstream. Pooling vs the in-game "additional" wording is
    # FLAGGED for verification (kept multiplicative, like the debuffs above).
    mult *= 1.0 + source.total(f"{dtype}_curse_taken")
    mult *= 1.0 + source.total("hit_curse_taken")
    return mult


# ── Damage-type conversion (outgoing hit damage) ──────────────────────────────
# Priority chain low→high; conversion flows UP only (Help DB). A converted/added slice carries its PATH:
# type-specific INCREASES sum over the path, type-specific ADDITIONALS multiply over the path; generic
# inc/add apply once. Tested in-game (see docs / plan): increases add, additionals multiply, lucky keys off
# the FINAL type. "convert" reduces the source's staying portion; "adds-as" is extra.
_CONV_PRIORITY = ["physical", "lightning", "cold", "fire", "erosion"]


def _conversion_fracs(source: BuildSource) -> tuple[dict, dict]:
    """Read convert + adds-as fractions per up-chain (source→dest) pair from `source`. Returns
    (convert, adds), each {src: {dst: frac}}. Convert is capped to ≤100% per source (redistributed by
    weight). physical_as_elemental adds its % as each of fire/cold/lightning."""
    convert: dict[str, dict[str, float]] = {}
    adds: dict[str, dict[str, float]] = {}
    for i, s in enumerate(_CONV_PRIORITY):
        higher = _CONV_PRIORITY[i + 1:]
        c = {d: max(0.0, source.total(f"{s}_convert_to_{d}")) for d in higher}
        tot = sum(c.values())
        if tot > 1.0:                                  # cap 100% per source, redistribute by weight
            c = {d: v / tot for d, v in c.items()}
        a = {d: max(0.0, source.total(f"{s}_as_{d}")) for d in higher}
        if s == "physical":
            pe = max(0.0, source.total("physical_as_elemental"))
            for d in ("fire", "cold", "lightning"):
                a[d] = a.get(d, 0.0) + pe
        convert[s] = {d: v for d, v in c.items() if v > 1e-12}
        adds[s] = {d: v for d, v in a.items() if v > 1e-12}
    return convert, adds


def _apply_conversion(eff_flat: dict, path_inc, path_add,
                      generic_inc: float, generic_add: float,
                      convert: dict, adds: dict) -> dict:
    """Cascade post-effectiveness flat (per type) through the conversion chain in priority order. Each
    packet records the UNION of dtype-tags of every type it has been; at finalization its type-specific
    bonuses are path_inc(path_tags) (sum) and path_add(path_tags) (product), each modifier counted ONCE.
    generic inc/add apply once. Returns {final_type: (scaled_min, scaled_max)} summed over packets landing
    there. Counting once over the path union (not per stage) is what stops "increased/additional Elemental
    Damage" from double-applying across an elemental→elemental hop (verified in-game). No conversion →
    reproduces (1 + type_inc) × type_add per native type (regression-safe)."""
    packets = {t: [] for t in _CONV_PRIORITY}          # each packet: [min, max, path_tags frozenset]
    for t in _CONV_PRIORITY:
        mn, mx = eff_flat.get(t, (0.0, 0.0))
        if mn or mx:
            packets[t].append([mn, mx, frozenset()])
    final: dict[str, tuple[float, float]] = {}
    for t in _CONV_PRIORITY:
        dt = frozenset({t}) | ({"elemental"} if t in _ELEMENTAL_DMG_TYPES else frozenset())
        for p in packets[t]:                           # this damage is now type t → record t in its path
            p[2] = p[2] | dt
        ct, at = convert.get(t, {}), adds.get(t, {})
        stay = 1.0 - sum(ct.values())
        for p in packets[t]:
            for d, frac in ct.items():                 # convert: route slice down-chain, reduce stay
                packets[d].append([p[0] * frac, p[1] * frac, p[2]])
            for d, frac in at.items():                 # adds-as: extra slice, stay unchanged
                packets[d].append([p[0] * frac, p[1] * frac, p[2]])
            if stay > 1e-12:
                f = (1.0 + generic_inc + path_inc(p[2])) * generic_add * path_add(p[2])
                cur = final.get(t, (0.0, 0.0))
                final[t] = (cur[0] + p[0] * stay * f, cur[1] + p[1] * stay * f)
    return final


@dataclass
class HitFormResult:
    name: str
    effectiveness_pct: float
    form_type: Literal["additive", "exclusive"]
    proc_chance: float
    damage_by_type: dict[str, float]
    avg_hit_pre_crit: float
    avg_hit_with_crit: float
    dps_contribution: float
    dps_vs_target: float = 0.0   # dps_contribution after target dummy mitigation
    hit_min_by_type: dict[str, float] = field(default_factory=dict)
    hit_max_by_type: dict[str, float] = field(default_factory=dict)
    fires_per_sec: float = 0.0   # this form's effective occurrences/sec (rate × proc); channeled forms differ
    hits_per_fire: int = 1       # projectiles/blades per occurrence (shotgun on one target)
    shotgun_falloff: float = 0.0 # same-target Shotgun Effect falloff coefficient (each subsequent hit −this)
    shotgun_mult: float = 1.0    # total per-occurrence shotgun multiplier (1 + (hits−1)×(1−falloff))
    base_min_by_type: dict[str, float] = field(default_factory=dict)  # this form's intrinsic base (spells)
    base_max_by_type: dict[str, float] = field(default_factory=dict)
    # Non-empty → this form is NOT-YET-IMPLEMENTED (0 DPS, excluded from % of Total); the strings are the reasons.
    # Used to surface a minion's non-damage abilities (Empower buffs, locked Ultimates) as visible, selectable
    # forms in the form dropdown rather than hiding them (never-silently-drop).
    nyi: list[str] = field(default_factory=list)


@dataclass
class DamageRow:
    """One row of the engine-owned breakdown table (`OffenseResult.damage_rows`) — the reconciliation
    contract that lets the frontend stop hand-reconstructing `_delivery` (cast/tangle/spell-burst/multistrike
    multiplier) and stop back-solving per-type mitigation. Every row here is ALREADY fully delivered and
    ALREADY split per damage type post-mitigation: nothing is left for the UI to multiply or re-derive.
    `pct_of_total` is of `OffenseResult.total_dps_vs_target`; summed across every row (all kinds) it equals
    100.0 (within float tolerance) — see `_finalize_damage_row_pcts`.

    kind:
      "hit"  — mirrors one `hit_forms[i]` entry, 1:1, same order. dps_final/dps_vs_target_final are that
               form's dps_contribution/dps_vs_target × the caller's delivery multiplier (1.0 for minions,
               which fold delivery — `count` — in earlier; see minion_offense.calculate_minion_offense).
      "true" — an unmitigated true-damage add-on with NO HitFormResult of its own (Mercury Baptism, Spell
               Ripple). dps_by_type_vs_target / hit_min_by_type / hit_max_by_type are empty — these are a
               single already-final number, not a per-type hit roll.
      "dot"  — FORWARD SLOT for the upcoming DoT damage stage; no "dot" row is emitted today. No DoT ever
               crits (ailment or otherwise — confirmed by the Help DB's "will not affect" list, and in-game:
               the control_spell support carries −100% Critical Strike Rating and RAISED Mind Control's DPS),
               so skip crit_factor/double_dmg_factor entirely. A DoT is a per-second standing effect, not
               delivered per-cast (tick granularity is deliberately not modelled here), so it must NOT be
               multiplied by `_delivery` either — cast_multiplier/tangle_mult/spell_burst_mult/multistrike_mult
               all describe how often a HIT is DELIVERED, which doesn't apply to a standing effect.
               (Design inference, not a Help DB statement: the Help DB never says a standing effect isn't
               "delivered" per cast — this is a sound engineering read of "DoT effects deal damage
               continuously for a period of time", not a cited mechanic. Revisit if a DoT is ever observed
               scaling with multistrike/tangle/spell-burst count in-game.)
               dps_final/dps_vs_target_final DO still have the usual pre-target/post-target split (a DoT is
               mitigated by the target's RESISTANCE — Help DB-confirmed in-game via Mind Control 222/sec base
               → ~155/sec vs the 30%-erosion-resist dummy, 222×0.70=155.4 — the ×0.49 an armor term would add
               is absent from the measurement) — they are NOT the same number:
                 dps_final          = base_per_second × (1 + Σ increased) × Π(1 + additional)
                 dps_vs_target_final = dps_final × (a RESISTANCE-ONLY multiplier — NO armor term, so no
                                       armor_pen either). Do not reuse `_target_mitigation` (it multiplies in
                                       `(1 − eff_armor)`); a sibling `_target_mitigation_dot` will be added
                                       that applies only `(1 − effective_resistance)`, with erosion_pen /
                                       <type>_pen / elemental_pen / all_resistance_reduction still feeding
                                       effective_resistance exactly as they do for a hit. BINDING CONSTRAINT:
                                       `_target_mitigation_dot` MUST reuse `_target_effective`'s existing
                                       per-type dispatch (the fire/cold/lightning branch vs the erosion branch)
                                       rather than reimplementing it — that dispatch is what keeps
                                       `elemental_pen` off Erosion (TLI "Elemental" excludes Erosion; see
                                       `_target_effective`'s branch at the top of this file). A fresh
                                       implementation is exactly where that bug would be reintroduced, silently
                                       overstating every Erosion DoT.
               dps_by_type_vs_target IS populated (a DoT has a damage type, unlike a "true" row);
               hit_min_by_type/hit_max_by_type stay `{}` (a DoT has no hit min/max — it isn't rolled per-hit).
               To add one: append the row to the SAME `damage_rows` list, fold its dps_final into total_dps
               AND its dps_vs_target_final into total_dps_vs_target, THEN call `_finalize_damage_row_pcts`.
               Zero frontend change required — the table already renders whatever rows are in the list.
    """
    kind: Literal["hit", "true", "dot"]
    name: str
    dps_final: float
    dps_vs_target_final: float
    pct_of_total: float
    dps_by_type_vs_target: dict[str, float] = field(default_factory=dict)
    hit_min_by_type: dict[str, float] = field(default_factory=dict)
    hit_max_by_type: dict[str, float] = field(default_factory=dict)


@dataclass
class OffenseResult:
    skill_name: str
    supported: bool             # False = NYI; when False no numeric fields are meaningful
    effective_level: int = 0
    hit_forms: list[HitFormResult] = field(default_factory=list)
    crit_chance: float = 0.0            # EFFECTIVE crit chance (capped at 1.0, post Lucky/Unlucky crit) — drives DPS
    crit_chance_uncapped: float = 0.0   # TRUE chance from rating (may exceed 1.0) — display-only, surfaces over-cap
    crit_luck_effect: str = ""          # "", "lucky", or "unlucky" — Critical Strikes have the Lucky/Unlucky effect
    crit_multiplier: float = 1.5
    # Double / Triple / Quadruple damage CHANCE (tag-filtered, summed pool, capped 100%) + the expected-value
    # multiplier folded into the average DPS (highest tier per hit). double_dmg_factor=1.0 → no double damage.
    double_dmg_chance: float = 0.0
    triple_dmg_chance: float = 0.0
    quad_dmg_chance: float = 0.0
    double_dmg_factor: float = 1.0
    steep_strike_chance: float = 0.0
    skills_per_second: float = 0.0
    base_cast_time: float = 0.0        # spell base cast time (seconds); 0 for attacks (weapon-APS driven)
    total_dps: float = 0.0
    total_dps_vs_target: float = 0.0   # total DPS after target dummy mitigation
    nyi: list[str] = field(default_factory=list)
    # Weapon component breakdown (for CalcsScreen display).
    # For single-weapon these reflect the actual weapon values.
    # For dual-wield, weapon_attack_speed / weapon_crit_rating_flat are the pre-averaged
    # effective values (gear multipliers already baked in by buildGearPayload); the
    # _gear and _mh fields will be 0 in that case.
    weapon_attack_speed: float = 0.0
    weapon_aps_gear: float = 0.0       # attack_speed_gear (decimal, e.g. 0.27)
    weapon_aps_mh: float = 0.0         # attack_speed_mh (decimal, mainhand-only)
    weapon_crit_rating_flat: float = 0.0
    weapon_csr_gear: float = 0.0       # attack_crit_rating_gear (decimal)
    weapon_csr_mh: float = 0.0         # attack_crit_rating_mh (decimal, mainhand-only)
    base_csr: float = 0.0              # intrinsic base crit rating (spells get _BASE_SPELL_CRIT_RATING; attacks 0 — weapon provides it)
    # Per-type damage breakdown for the stats screen breakdown table
    flat_dmg_min: dict[str, float] = field(default_factory=dict)  # flat before inc/add (skill base + added)
    flat_dmg_max: dict[str, float] = field(default_factory=dict)
    # The skill's INTRINSIC per-level base damage per type (spells only; attacks derive base from the
    # weapon, which is already a keyed gear source). Surfaced so the breakdown can show it as a baseline.
    base_dmg_min: dict[str, float] = field(default_factory=dict)
    base_dmg_max: dict[str, float] = field(default_factory=dict)
    type_inc: dict[str, float] = field(default_factory=dict)      # total increased decimal (e.g. 2.77 = 277% increased)
    type_add: dict[str, float] = field(default_factory=dict)      # total more product (e.g. 1.65 = x1.65)
    above_max_mult: float = 1.0  # additional multiplier from being above max skill level (1.0 = at or below max)
    generic_inc: float = 0.0    # total increased from non-dtype-specific sources (applies uniformly to all types)
    generic_add: float = 1.0    # total more product from non-dtype-specific sources (INCLUDES main-stat Damage Bonus)
    # Main-stat Damage Bonus — the portion of generic_add from the skill's main-stat attributes.
    # main_stat_damage_bonus is the fraction (0.255 = +25.5%); main_stats lists the attributes summed.
    main_stat_damage_bonus: float = 0.0
    main_stats: list[str] = field(default_factory=list)
    # Skill-intrinsic 'additional damage' pool entries ([{label, amount}]) — the extra_additional folded into
    # intrinsic_add (e.g. Rapid Advance's per-Max-Channeled-Stack bonus, Focused Slash's Fervor). Populated by
    # compute (which has the source + condition state); surfaced in the "Total Additional" breakdown panel.
    intrinsic_additional_sources: list = field(default_factory=list)
    # Skill tags and tag-specific mechanics
    skill_tags: list[str] = field(default_factory=list)
    skill_area_inc: float = 0.0  # total increased area of effect (only when "area" in skill_tags)
    # Per-cast hit multiplier from same-target shotgun (Merge + Web). 1.0 = no shotgun. Applied to the
    # DPS totals (NOT the per-hit-form damage — mirrors the in-game tooltip vs Recount split).
    cast_multiplier: float = 1.0
    shotgun_hits: int = 1        # same-target hits per cast (1 = no shotgun)
    # Jumps / Chains (Chain Lightning etc.): total = skill base jumps + Σ extra_jumps_flat (support-granted).
    # jumps_base is the skill's intrinsic count (0 for non-jump skills, so the Skill Effects row stays hidden).
    jumps: int = 0
    jumps_base: int = 0
    # Base per-cast Mana Cost (display only — cost reductions/conversions / "Skills no longer cost Mana" NYI).
    mana_cost: float = 0.0
    # Tangle mode (the skill is cast by N tangles, not the player). tangle_count = attached tangles on the target
    # (each a full caster), tangle_enhancement = the ×(1 + Σ Tangle Damage Enhancement) multiplier. Both fold into
    # the DPS totals like cast_multiplier (NOT the per-hit-form damage). 0 / 1.0 when the skill is not tangled.
    tangle_count: int = 0
    tangle_enhancement: float = 1.0
    tangle_mult: float = 1.0           # total Tangle delivery multiplier folded into total_dps (= count; 1.0 if untangled)
    tangle_placeable: int = 0          # Max Tangle Quantity (base 2 + mods)
    tangle_inactivated: int = 0        # placeable − active (feeds Dormant Entanglement)
    tangle_duration: float = 0.0       # seconds (base 8 × duration mods) — display only
    tangle_attach_range: float = 0.0   # metres (base 8 × attach-range mods) — display only
    tangle_cast_ticks: int = 0         # whole server ticks per tangle cast (cast-speed breakpoint); 0 if untangled
    tangle_cast_to_next_increased: float = 0.0  # +Increased Cast Speed needed for the next faster tick breakpoint
    tangle_cast_to_next_additional: float = 0.0  # +Additional Cast Speed needed for the next faster tick breakpoint
    # Channeled-attack rate breakpoints (Split Shot: Rapid Advance) — the channel fires on whole 30 Hz ticks
    # (rate = 30 ÷ ticks). 0 when not a channeled attack. Surfaced in the Channeled box.
    channel_attack_ticks: int = 0
    channel_attack_smooth_sps: float = 0.0  # the smooth attack rate BEFORE the 30 Hz breakpoint (the true attack speed)
    channel_attack_to_next_increased: float = 0.0  # +Increased Attack Speed needed for the next faster breakpoint
    channel_attack_to_next_additional: float = 0.0  # +Additional Attack Speed needed for the next faster breakpoint
    # Spell Burst mode (an eligible Spell cast at full charge consumes all M stacks and auto-recasts the spell
    # M times — the triggering cast also counts, so casts_per_burst = M + 1). The charge is a server-timed,
    # whole-tick countdown (hard-rounded breakpoints — see engine/tick.py), so charge speed only helps at
    # integer-tick crossings. spell_burst_mult is the TOTAL delivery multiplier folded into total_dps
    # ( = casts_per_burst × bursts/sec ÷ sps); the per-hit-form damage already carries the spell_burst pools.
    spell_burst_count: int = 0             # Max Spell Burst (M); 0 = not bursting
    spell_burst_casts_per_burst: int = 0   # M + 1 (the M recasts + the triggering cast)
    spell_burst_charge_ticks: int = 0      # whole-tick charge period (ceil(30 × T_eff))
    spell_burst_charge_time: float = 0.0   # seconds to full charge (T_eff, after Surging) — display
    spell_burst_charge_factor: float = 1.0 # total Spell Burst Charge Speed multiplier ((1+Σinc)×Π(1+add)) — display
    spell_burst_charge_inc: float = 0.0    # Σ Spell Burst Charge Speed INCREASED only (matches in-game; Solid River's gate)
    spell_burst_charge_to_next_inc: float = 0.0   # +Increased Charge Speed for the next DPS-relevant breakpoint
    spell_burst_charge_to_next_add: float = 0.0   # +Additional Charge Speed for the same breakpoint
    spell_burst_cast_to_next_inc: float = 0.0     # +Increased Cast Speed to the next breakpoint (manual / Play Safe)
    spell_burst_cast_to_next_add: float = 0.0     # +Additional Cast Speed to the same breakpoint (manual / Play Safe)
    spell_burst_play_safe: bool = False           # Play Safe in build → cast speed couples into charge (a second lever)
    spell_burst_next_breakpoint_ticks: int = 0    # charge-tick count of the next breakpoint that raises bursts/sec (0 = none)
    spell_burst_rate: float = 0.0          # bursts per second (≤ 30)
    spell_burst_mult: float = 1.0          # total damage multiplier from bursting (folded into total_dps)
    spell_burst_auto: bool = False         # auto-trigger (instant at full charge) vs manual (cast-gated)
    spell_burst_auto_source: str = ""      # what drives auto-trigger (e.g. Burst Activation); "" = manual
    # Burst / non-burst DPS split (combined manual model — auto has no non-burst part). Sum to total_dps(_vs_target).
    spell_burst_dps: float = 0.0
    spell_burst_dps_vs_target: float = 0.0
    non_spell_burst_dps: float = 0.0           # casts made BETWEEN bursts (manual only; 0 for auto-trigger)
    non_spell_burst_dps_vs_target: float = 0.0
    # Channeled mode (a held skill gaining 1 stack/use; RESET dumps at max + fires a burst form). All 0 / ""
    # when not channeled. The continuous form fires every use; the burst form at channeled_burst_rate. Stacks
    # are display-only (steady state = the cap). See engine/uptime.channeled_rounds_per_cycle.
    channeled_max_stacks: int = 0          # cap after +Max Channeled Stacks (0 = not channeled)
    channeled_min_stacks: int = 0          # Min Channeled Stacks (first round from 0 gains 1 + this)
    channeled_stacks: float = 0.0          # display steady-state stacks (= cap for a sustained channel)
    channeled_rounds_per_cycle: float = 0.0  # uses per RESET cycle = max(1, max − min)
    channeled_burst_rate: float = 0.0      # reset-burst occurrences/sec (= sps / rounds_per_cycle)
    channeled_behavior: str = ""           # "reset" | "refresh" | "" (not channeled)
    channeled_attack_frequency: float = 0.0  # persistent-entity strike rate (Howling Gale's Gale); 0 = N/A
    projectile_count: int = -1             # projectiles of the projectile-scaling form (Icy Blade); -1 = N/A (no such form)
    projectile_base_count: int = 0         # the skill's OWN projectiles before +Quantity mods (for the count breakdown)
    # Compulsory-conversion per-element detail (Chromatic Shot). {element: {hit_min, hit_max, avg_pre_crit,
    # avg_with_crit, mitigation}}. The headline total_dps is the EXPECTED average; this is the C+D per-element box.
    compulsory_breakdown: dict = field(default_factory=dict)
    # Combined per-type ENEMY damage multiplier on OUTGOING damage = target armor/resist mitigation
    # (1−armor)(1−resist) × enemy vulnerability (Paralysis / Numbed / Frostbite / Infiltration / curses / …).
    # 1.0 = neutral; <1 = net-mitigated, >1 = net-amplified. Surfaced so the damage area can show one
    # "Enemy Multiplier" line per type. Depends on is_spell (Frail is Spell-form).
    enemy_mult_by_type: dict[str, float] = field(default_factory=dict)
    # Multistrike (attack skills): per-cast delivery multiplier from auto-repeats — each repeat pays its own
    # attack time (+20% increased AS) and deals increasing damage. 1.0 = no multistrike. The rest drive the box.
    multistrike_chance: float = 0.0           # total chance (fraction, e.g. 1.16 = 116%)
    multistrike_avg_count: float = 0.0        # expected attacks per chain = 1 + chance
    multistrike_increment: float = 0.0        # effective per-stack increment = base × (1 + additional)
    multistrike_max_count: int = 0            # K = longest possible chain (Max Multistrike Count)
    multistrike_mult: float = 1.0             # delivery multiplier folded into total_dps
    multistrike_repeat_aps: float = 0.0       # attack rate during repeats = sps × (1 + as_inc + 0.20)/(1 + as_inc)
    multistrike_chain: list = field(default_factory=list)  # [{count, prob}] chain-length distribution
    # Mercury Baptism (Rosa Unsullied Blade): recorded fraction of elemental hit damage re-dealt as TRUE damage,
    # and the resulting unmitigated DPS (vs target), folded into total_dps_vs_target.
    mercury_baptism_fraction: float = 0.0
    mercury_baptism_dps: float = 0.0
    # Spell Ripple (Ethereal Prism): spell hits proc a Pulse dealing TRUE damage = fraction × hit damage
    # (fraction = 0.5 chance × 1.5 = 0.75), folded in unmitigated.
    spell_ripple_fraction: float = 0.0
    spell_ripple_dps: float = 0.0
    # Demolisher Charge mode (Groundshaker etc.). The skill is cast at a cadence (Rhythm interval / APS); the
    # primary fissure lands every cast, the secondary explosion only on a CHARGED cast (a held charge, regained
    # every restoration_time s). The breakpoint fields drive the bidirectional restoration-vs-cadence helper.
    # All 0 / "" when the skill is not a Demolisher skill.
    demolisher_mode: str = ""                    # "rhythm" | "manual" | "" (not a demolisher skill)
    demolisher_restoration_time: float = 0.0     # seconds to regain 1 charge = base / (1 + Σ charge-speed increased)
    demolisher_base_restore: float = 0.0         # skill's base restoration (Groundshaker 3s)
    demolisher_charge_speed_inc: float = 0.0     # Σ Demolisher Charge Speed INCREASED (the only pool that applies)
    demolisher_cast_rate: float = 0.0            # casts/sec (primary fissure rate)
    demolisher_charged_rate: float = 0.0         # charged casts/sec (secondary explosion rate) ≤ cast_rate
    demolisher_rhythm_interval: float = 0.0      # Rhythm cast interval R (0 = manual/APS)
    demolisher_mismatch: bool = False            # restoration slower than the cadence → not every cast is charged
    demolisher_restore_to_sustain: float = 0.0   # +Increased Charge Speed needed for every-cast-charged
    demolisher_cdr_droppable: float = 0.0        # Increased Charge Speed droppable while still sustaining
    demolisher_under_breakpoint: bool = False    # below the every-cast-charged breakpoint
    demolisher_over_breakpoint: bool = False     # above it (has headroom to drop charge speed)
    demolisher_collapse_pct: float = 0.0         # Collapse tick amplification (fraction) folded into the fissure ticks
    demolisher_frequent_quake: bool = False      # explosion replaced by 5 primary-fissure hits
    demolisher_area_mode: str = "both"           # "both" | "primary" | "secondary" (the fissure ENUM)
    demolisher_primary_dps: float = 0.0          # primary-fissure DPS vs target (after delivery)
    demolisher_secondary_dps: float = 0.0        # secondary-explosion / FQ-tick DPS vs target (after delivery)
    # Activation-medium trigger cadence driving the cast rate (Rhythm/Track/Instruction/Wind Rhythm). 0 = the
    # skill fires at its own cast/attack rate (no triggering medium). Surfaced so the Hit Rate row reads correctly.
    trigger_interval: float = 0.0
    # Wind Rhythm trigger (server-tick breakpoint mechanic). All 0 / False when Wind Rhythm isn't the trigger.
    wind_rhythm_active: bool = False
    wind_rhythm_rate: float = 0.0                 # triggers/sec (= cast rate) after tick rounding
    wind_rhythm_ticks: int = 0                    # whole-tick cadence period (ceil(raw × 30))
    wind_rhythm_cast_time: float = 0.0            # server cast time (ticks / 30)
    wind_rhythm_base_cooldown: float = 0.0        # per-tier base cooldown (seconds)
    wind_rhythm_bonus: float = 0.0               # roll: share of Cast Speed applied to CDR
    wind_rhythm_cdr_to_next: float = 0.0          # +Increased CDR % to the next faster tick
    wind_rhythm_cast_to_next: float = 0.0         # +Increased Cast Speed % to the next faster tick
    wind_rhythm_wind_to_next: float = 0.0         # +Wind-bonus % to the next faster tick
    # Spirit Magus (minion) display info — the Growth subsystem's per-minion state, surfaced for the minion panel.
    # All 0 for non-Spirit-Magus results. Growth/Stage/Physique/Skill Area/Enhanced-chance don't (except via the
    # stage bonuses already folded into the damage forms) feed hit DPS — Physique & Skill Area are display-only.
    spirit_magi_growth: float = 0.0               # current Growth (100–1000)
    spirit_magi_stage: int = 0                    # Stage 1–5 (0 = not a Spirit Magus)
    spirit_magi_physique_inc: float = 0.0         # total Physique % (Growth +1%/8 + gear) — display only
    spirit_magi_enhanced_chance: float = 0.0      # Enhanced-Skill chance (pool + Stage-2 +30%), capped ≤ 1
    spirit_magi_max: int = 0                       # Max Spirit Magi in Map (the count that fights)
    # A minion's Empower buff (e.g. Thundercloud Surge) surfaced like a player empower: base/effective cooldown +
    # duration, uptime, Empower Effect, and the per-buff magnitudes (base → effective). None for non-empower.
    minion_empower: dict | None = None
    # ── Purpose-built breakdown-row contract (engine-owned; see DamageRow) ────────────────────────────────
    # Replaces the frontend's hand-reconstruction of _delivery and its back-solved per-type mitigation.
    # kind="hit" rows mirror hit_forms 1:1; kind="true" covers Mercury Baptism / Spell Ripple; kind="dot" is
    # the forward slot for the upcoming DoT stage (see DamageRow's docstring for the exact slot-in contract).
    damage_rows: list[DamageRow] = field(default_factory=list)
    # The two halves of enemy_mult_by_type, split out so the frontend can show/verify them separately instead
    # of back-solving mitigation as enemy_mult_by_type ÷ its own copy of the vuln stat-key list.
    # target_mitigation_by_type[d] × enemy_vuln_by_type[d] == enemy_mult_by_type[d] for every d.
    target_mitigation_by_type: dict[str, float] = field(default_factory=dict)  # armour/resist half only
    enemy_vuln_by_type: dict[str, float] = field(default_factory=dict)         # vulnerability-product half only


def _build_hit_damage_rows(hit_forms: list[HitFormResult], *, delivery: float,
                           mitigation_fn: Callable[[str], float],
                           crit_factor: float, double_dmg_factor: float) -> list[DamageRow]:
    """Build one kind="hit" DamageRow per HitFormResult (same order), fully delivered (× `delivery` — the
    cast/tangle/spell-burst/multistrike multiplier the caller already computed) and split per damage type
    using `mitigation_fn(dtype)` — the remaining post-hit multiplier NOT already folded into `damage_by_type`.
    Player caller: pass target-mitigation ALONE (enemy-vulnerability is already folded into damage_by_type at
    hit time — see the per-type loop in calculate_offense). Minion caller: pass mitigation × vulnerability
    combined (neither is pre-folded into the minion's damage_by_type — see calculate_minion_offense).

    Pure read of hit_forms — never mutates it (hit_forms is consumed elsewhere, and displayOffense relies on
    a pre-delivery RATIO where _delivery cancels; that must keep working byte-identical).

    Share math: damage_by_type[t] already reflects every per-hit factor EXCEPT crit/double-damage (both
    single skill-level scalars applied uniformly to every type) and this remaining mitigation factor — so
    `damage_by_type[t] * mitigation_fn(t) * crit_factor * double_dmg_factor` is exactly the per-type slice of
    the form's own `avg_hit_with_crit` vs-target average; summed over t it reproduces that scalar exactly.
    Multiplying the form's ALREADY-FINAL dps_vs_target by each type's SHARE of that slice (rather than
    recomputing a rate from scratch) makes this exact for every form, including ones a caller rewrites after
    the fact with a different rate (Demolisher's cast/charged-rate rebuild, Chilling Spike's split-off form)
    — those rewrites only ever rescale a form's total DPS by a scalar uniform across damage types.
    """
    rows: list[DamageRow] = []
    for form in hit_forms:
        per_type_vs_target = {
            t: v * mitigation_fn(t) * crit_factor * double_dmg_factor
            for t, v in form.damage_by_type.items()
        }
        share_total = sum(per_type_vs_target.values())
        dps_vs_target_final = form.dps_vs_target * delivery
        dps_by_type_vs_target = (
            {t: dps_vs_target_final * (v / share_total) for t, v in per_type_vs_target.items()}
            if share_total > 0.0 else {}
        )
        rows.append(DamageRow(
            kind="hit",
            name=form.name,
            dps_final=form.dps_contribution * delivery,
            dps_vs_target_final=dps_vs_target_final,
            pct_of_total=0.0,   # filled by _finalize_damage_row_pcts once the FINAL total is known
            dps_by_type_vs_target=dps_by_type_vs_target,
            hit_min_by_type=dict(form.hit_min_by_type),
            hit_max_by_type=dict(form.hit_max_by_type),
        ))
    return rows


def _finalize_damage_row_pcts(rows: list[DamageRow], total_dps_vs_target: float) -> None:
    """Fill pct_of_total on every row (hit + true + any dot rows already appended) so they sum to 100.0 of
    the FINAL total_dps_vs_target (after true-damage add-ons like Mercury Baptism / Spell Ripple have been
    folded in by the caller). No-op (rows stay at their DamageRow-construction default 0.0) when the total
    is zero — an unsupported/zero-damage skill has nothing to reconcile."""
    if total_dps_vs_target <= 0.0:
        return
    for row in rows:
        row.pct_of_total = row.dps_vs_target_final / total_dps_vs_target * 100.0


def _above_max_mult(effective_level: int, max_level: int) -> float:
    """Return the additional damage multiplier for levels above max level.

    Damage effectiveness % from the skill description does NOT change above max level.
    Instead, a compounding additional multiplier is applied to the final hit damage:
      Levels max+1 to max+10: ×1.10 per level.
      Levels max+11+:         ×1.08 per level (compound on top of tier1).
    Returns 1.0 at or below max level.
    """
    extra = effective_level - max_level
    if extra <= 0:
        return 1.0
    tier1 = min(extra, 10)
    result = 1.10 ** tier1
    tier2 = max(0, extra - 10)
    if tier2 > 0:
        result *= 1.08 ** tier2
    return result


def skill_effective_level(
    source: BuildSource,
    skill_tags: list[str],
    base_level: int,
    is_main_skill: bool = False,
) -> int:
    """Compute effective skill level from base_level + all applicable +Skill Level bonuses."""
    tags_lower = {t.lower() for t in skill_tags}
    bonus = sum(
        int(source.total(key))
        for key, tags in _SKILL_LEVEL_STATS
        if not tags or tags & tags_lower
    )
    if is_main_skill:
        bonus += int(source.total("main_skill_level"))
    return max(1, base_level + bonus)


def compute_skill_rates(source: BuildSource, skill: ResolvedSkill, *, skill_tags_lower=None) -> dict:
    """The cheap "rates" stage of offense — a skill's rate primitives, independent of the heavy damage
    calc. Currently attacks/cast per second (crit chance, hit rate can join this dict later). Extracted
    so it can run INSIDE the aggregation loop for uptime models (which need APS during convergence) while
    the damage calc stays one-shot post-loop; calculate_offense calls this too, so the APS math has one
    source of truth. Slot-agnostic: computes rates for whatever skill it is given (no main-slot assumption).

    Returns {"sps": float, "base_cast_time": float}.
    """
    if skill_tags_lower is None:
        skill_tags_lower = {t.lower() for t in skill.tags}
    base_cast_time = 0.0
    if skill.is_spell:
        # Spell: casts/sec = (1 / cast time) × (1 + cast speed inc) × Π(1 + cast speed additional).
        cast_time = skill.base_cast_time or 1.0
        base_cast_time = cast_time
        sps = (1.0 / cast_time) * (1.0 + source.total("cast_speed_inc"))
        sps *= _speed_additional_product(source, _CAST_ADDITIONAL_STATS, skill_tags_lower)
    else:
        # APS: base × (1 + per-weapon gear multipliers) × (1 + inc) × additional pools. A channeled ATTACK
        # (Split Shot: Rapid Advance) uses this SAME weapon-APS path — it keys off weapon attack speed like any
        # attack (the standard 1.5 base weapon APS × +100% additional = 3/s); calculate_offense then hard-rounds
        # the rate to 30 Hz tick breakpoints (opt-in regime, engine/tick.py).
        weapon_aps_mult = 1.0 + source.total("attack_speed_gear") + source.total("attack_speed_mh")
        sps = source.total("weapon_attack_speed") * weapon_aps_mult * (1.0 + source.total("attack_speed_inc"))
        sps *= _speed_additional_product(source, _APS_ADDITIONAL_STATS, skill_tags_lower)
        # Movement Speed → additional Attack Speed (Wrathful Vault: "75% of the bonuses for Movement Speed is
        # also applied to the additional Attack Speed, up to +60%"). movement_bonus_to_attack_speed is the share
        # (0.75); the optional _cap stat bounds the converted bonus. Presence-gated (non-consuming all_stats check)
        # so non-source builds don't read/consume it → golden-identical.
        mbtas = source.total("movement_bonus_to_attack_speed") if "movement_bonus_to_attack_speed" in source.all_stats() else 0.0
        if mbtas > 0.0:
            conv = mbtas * max(0.0, source.total("movement_speed_inc"))
            cap = source.total("movement_bonus_to_attack_speed_cap")
            if cap > 0.0:
                conv = min(conv, cap)
            sps *= (1.0 + conv)
    # Activation-medium trigger cadence OVERRIDE (Rhythm/Track/Instruction/Preparation/Wind Rhythm): a triggered
    # skill fires at the medium's cadence, not the player's cast/attack rate. Presence-gated (non-consuming) so
    # non-triggered skills stay identical. Wind Rhythm is tick-quantized; the "every X s" mediums are exact 1/interval.
    _present_rate = source.all_stats()
    if "wind_rhythm_base_cooldown" in _present_rate and source.total("wind_rhythm_base_cooldown") > 0.0:
        sps = compute_wind_rhythm_rate(source, source.total("wind_rhythm_base_cooldown"),
                                       source.total("wind_rhythm_share"))["rate"]
    elif "trigger_interval" in _present_rate and source.total("trigger_interval") > 0.0:
        sps = 1.0 / source.total("trigger_interval")
    # Global 30 Hz cap: a single caster acts at most once per server tick.
    return {"sps": cap_rate(sps), "base_cast_time": base_cast_time}


def channeled_attack_fire_rate(smooth_sps: float, skill: ResolvedSkill, is_attack: bool) -> float:
    """The actual fire cadence of a channeled ATTACK. It fires at the SMOOTH attack rate — channeled attacks do
    NOT snap to 30 Hz breakpoints. (Split Shot: Rapid Advance snapped ~3 seasons ago, but that quirk was removed
    in-game; breakpoints are unrelated to channeling — verified: the flat-damage-per-consume ramps CONTINUOUSLY
    with attack speed, which a breakpoint would freeze flat across a whole tick band.) Kept as the single shared
    entry point (offense DPS path + consumption use-rate) so "how often it fires" stays defined in one place."""
    return smooth_sps


def _spell_flat(source: BuildSource, base_map: dict, eff_mult: float):
    """Spell flat pool for one (per-level base, added-damage effectiveness): the intrinsic base (UNSCALED
    by effectiveness) + spell-tagged added flat (gear/supports) scaled by eff_mult. Weapon base does NOT
    apply to spells. Returns (flat_dmg, skill_base_dmg). Shared by the single-form spell path and each
    multi-form spell form (e.g. Icebound Beam's Cold Beam / Icy Blade, which carry per-form base+eff)."""
    flat: dict[str, tuple[float, float]] = {}
    base_only: dict[str, tuple[float, float]] = {}
    for dtype in DAMAGE_TYPES:
        b_min, b_max = base_map.get(dtype, (0.0, 0.0))
        add_min = source.total(f"{dtype}_spell_dmg_flat_min")
        add_max = source.total(f"{dtype}_spell_dmg_flat_max")
        total_min = b_min + add_min * eff_mult
        total_max = b_max + add_max * eff_mult
        if b_min > 0 or b_max > 0:
            base_only[dtype] = (b_min, b_max)
        if total_min > 0 or total_max > 0:
            flat[dtype] = (total_min, total_max)
    return flat, base_only


def calculate_offense(
    source: BuildSource,
    skill: ResolvedSkill,
    base_level: int,
    is_main_skill: bool = True,
    extra_additional: float = 0.0,
    support_behavior: dict | None = None,
    remove_mod_tags: set[str] | None = None,
    tangle: dict | None = None,
    spell_burst: dict | None = None,
    demolisher: dict | None = None,
    add_mod_tags: set[str] | None = None,
) -> OffenseResult:
    # tangle: when set (the skill has a Tangle activator support), the skill is cast by N tangles instead of the
    # player. `tangle["count"]` = attached tangles on the target (each a full caster). Adds the "tangle" mod tag
    # (so Tangle Damage / additional / crit pools apply via existing tag filtering) and folds two final
    # multipliers into the DPS totals: the count, and ×(1 + Σ Tangle Damage Enhancement).
    # extra_additional: a skill-intrinsic generic "additional damage" pool (fraction), evaluated
    # by the caller from the skill's intrinsic_additional + condition state (e.g. Focused Slash's
    # Fervor bonus). Applied as one extra multiplicative pool on every hit.
    if not skill.supported:
        return OffenseResult(skill_name=skill.name, supported=False)

    # Tags used for damage increased/additional + crit filtering — the skill's own tags plus any it
    # borrows (e.g. Moon Strike borrows 'spell' so Spell Damage mods apply to its Attack Damage).
    # NOT used for flat adds / is_spell, so a borrowing skill doesn't pull in off-type flat damage.
    skill_tags_lower = {t.lower() for t in skill.tags}
    # A support can strip a tag from the supported skill (e.g. Focused Slash: Behead removes 'area', so
    # Area-scoped damage mods + the skill_area display no longer apply). Affects mod-gating + skill_area.
    if remove_mod_tags:
        skill_tags_lower = skill_tags_lower - {t.lower() for t in remove_mod_tags}
    mod_tags = skill_tags_lower | {t.lower() for t in skill.extra_damage_mod_tags}
    if remove_mod_tags:
        mod_tags = mod_tags - {t.lower() for t in remove_mod_tags}
    # Tangle mode: tag the skill "tangle" so Tangle Damage (inc), additional Tangle Damage, and Tangle Crit
    # Rating apply through the existing tag-filtered pools. The count + enhancement multipliers are folded into
    # the DPS totals at the end (like cast_multiplier).
    if tangle:
        mod_tags = mod_tags | {"tangle"}
    # Spell Burst mode: tag the skill "spell_burst" so "+X% additional Hit Damage for skills cast by Spell
    # Burst" (spell_burst_hit_dmg_additional) applies only to burst casts. The charge/recast multiplier folds
    # into the DPS totals at the end (like cast_multiplier / tangle_mult).
    if spell_burst:
        mod_tags = mod_tags | {"spell_burst"}
    # Skill-effect-granted tags (e.g. Wrathful Vault makes Groundshaker a Mobility skill) — so Mobility-scoped
    # damage/crit mods apply. Added to both the damage-mod set and the reported skill_tags.
    if add_mod_tags:
        _extra_tags = {t.lower() for t in add_mod_tags}
        skill_tags_lower = skill_tags_lower | _extra_tags
        mod_tags = mod_tags | _extra_tags

    # 0. Crit — computed here in the offense layer, NOT in the fixed-point loop
    # Weapon CSR (from weapon gear piece) scaled by gear-specific and MH-specific % mods only — ATTACKS ONLY.
    # Spells derive crit from their innate base 500 CSR, NOT the weapon (which is still worn for its other stats),
    # so weapon Critical Strike Rating must not leak into a spell's crit. Tag-borrowing attacks (Moon Strike,
    # is_spell=False) keep weapon CSR correctly.
    weapon_csr = 0.0 if skill.is_spell else source.total("weapon_crit_rating_flat") * (
        1.0 + source.total("attack_crit_rating_gear") + source.total("attack_crit_rating_mh")
    )
    # Non-weapon flat CSR — attack_crit_rating_flat + spell_crit_rating_flat, tag-filtered to the skill.
    other_csr = sum(source.total(k) for k, tags in _CRIT_RATING_FLAT_STATS if not tags or tags & mod_tags)
    # Innate base Critical Strike Rating for spells: every spell starts at 500 CSR (= 5% base crit)
    # with no weapon to provide it. Attacks derive their crit from weapon CSR and are left unchanged.
    base_csr = _BASE_SPELL_CRIT_RATING if skill.is_spell else 0.0
    # Increased Critical Strike Rating scales the whole CSR pool. The % pool sums the generic
    # crit_rating_inc/additional plus the tag-specific increases (attack/spell/projectile) that match this
    # skill — so e.g. "Spell Critical Strike Rating" applies only to spell skills, "Projectile…" only to
    # projectile skills, exactly like the type/skill crit-damage pool above.
    crit_rating_inc = sum(source.total(k) for k, tags in _CRIT_RATING_INC_STATS if not tags or tags & mod_tags)
    # Crit Rating per Mana consumed recently (Tyrant's Iron Fist) — increased Crit Rating scaled by the rolling
    # consumed_recently_mana (set on source post-loop). One-directional, so folded here, not in the loop.
    _crr_per = source.total("crit_rating_inc_per_mana_consumed")
    if _crr_per:
        crit_rating_inc += floored_consumed(source.total("consumed_recently_mana"),
                                            source.total("crit_rating_inc_per_mana_consumed_unit")) * _crr_per
    raw_csr = (base_csr + weapon_csr + other_csr) * (1.0 + crit_rating_inc)
    # 100 CSR = 1% crit chance; divide by 10000 to convert to 0–1 float
    # crit_chance_uncapped is the TRUE chance from rating (can exceed 1.0) — surfaced so the user sees over-cap;
    # the EFFECTIVE crit_chance that drives crit_factor is capped at 1.0 (crit is ineffective above 100%).
    crit_chance_uncapped = raw_csr / 10000.0
    crit_chance = min(crit_chance_uncapped, 1.0)
    # "Critical Strikes have the Lucky / Unlucky effect" (Perched River kismet): the crit-CHANCE roll is made twice —
    # Lucky keeps the better outcome (crit if EITHER roll succeeds → 1−(1−p)²), Unlucky the worse (crit only if BOTH →
    # p²). This EFFECTIVE chance drives crit_factor AND the displayed Crit Chance. Lucky+Unlucky cancel (→ unchanged).
    _lucky_crit = source.total("lucky_crit") > 0.0
    _unlucky_crit = source.total("unlucky_crit") > 0.0
    crit_luck_effect = ""   # "", "lucky", or "unlucky" — surfaced so the UI can show the effective-chance source
    if _lucky_crit and not _unlucky_crit:
        crit_chance = 1.0 - (1.0 - crit_chance) ** 2
        crit_luck_effect = "lucky"
    elif _unlucky_crit and not _lucky_crit:
        crit_chance = crit_chance * crit_chance
        crit_luck_effect = "unlucky"

    # 1. Effective level — sum all applicable skill level bonuses from gear/talents/memories

    # Crit multiplier = 1.5 base + the additive Critical Strike Damage pool (tag-filtered to the skill).
    crit_damage = sum(source.total(key) for key, tags in _CRIT_DMG_STATS if not tags or tags & mod_tags)
    # Crit Damage per Mana consumed recently (Tyrant's Iron Fist) — additive Crit Damage scaled by consumed_recently.
    _crd_per = source.total("crit_dmg_inc_per_mana_consumed")
    if _crd_per:
        crit_damage += floored_consumed(source.total("consumed_recently_mana"),
                                        source.total("crit_dmg_inc_per_mana_consumed_unit")) * _crd_per
    crit_mult = 1.5 + crit_damage
    crit_factor = 1.0 + crit_chance * (crit_mult - 1.0)

    def _luck_ratio(mn: float, mx: float, level: int) -> float:
        """EV-of-the-damage-roll ÷ the midpoint EV, for a given luck level: +1 Lucky (roll twice, keep HIGHER →
        min + 2/3·range), −1 Unlucky (keep LOWER → min + 1/3·range), 0 normal (midpoint → 1.0). Lucky and Unlucky
        on the same type cancel to 0. Returns exactly 1.0 at level 0 / zero spread → Lucky-only & no-luck builds
        stay byte-identical."""
        if level == 0 or mx <= mn:
            return 1.0
        frac = (2.0 / 3.0) if level > 0 else (1.0 / 3.0)
        R = mx - mn
        return (mn + frac * R) / (mn + 0.5 * R)

    # Double-damage chance — each hit has Σchance probability to deal 2×. Expected-value multiplier on the
    # average (lifts DPS, not the displayed per-hit), tag-filtered like crit. Chance capped at 100% (→ ≤2×).
    # Double/Triple/Quadruple damage — highest-tier-procs expected value. Each tier's chance is the summed,
    # tag-filtered pool, capped at 100%. EV multiplier = Σ tier_value × P(that tier is the highest to proc):
    #   4q₄ + 3(1−q₄)q₃ + 2(1−q₄)(1−q₃)q₂ + (1−q₄)(1−q₃)(1−q₂).  With only double (q₃=q₄=0) this reduces to
    #   1 + q₂ — IDENTICAL to the prior double-only behavior (snapshot-safe). Applied to the average like crit.
    q2 = min(sum(source.total(k) for k, tags in _DOUBLE_DMG_STATS if not tags or tags & mod_tags), 1.0)
    q3 = min(sum(source.total(k) for k, tags in _TRIPLE_DMG_STATS if not tags or tags & mod_tags), 1.0)
    q4 = min(sum(source.total(k) for k, tags in _QUAD_DMG_STATS if not tags or tags & mod_tags), 1.0)
    double_dmg_factor = (4 * q4 + 3 * (1 - q4) * q3 + 2 * (1 - q4) * (1 - q3) * q2
                         + (1 - q4) * (1 - q3) * (1 - q2))

    effective_level = skill_effective_level(source, skill.tags, base_level, is_main_skill)
    lookup_level = min(effective_level, skill.max_level)

    # 2. Flat damage pool per type: weapon base (× gear inc) + ring/gear/talent flat adds
    #    All sources pool here before any inc or additional multiplier is applied.
    is_attack = "attack" in skill_tags_lower
    is_spell = "spell" in skill_tags_lower

    flat_dmg: dict[str, tuple[float, float]] = {}
    skill_base_dmg: dict[str, tuple[float, float]] = {}  # intrinsic per-level base (spells); shown as baseline
    if skill.is_spell:
        # Spell flat pool — see _spell_flat. Verified in-game (docs/CHAIN_LIGHTNING_IMPLEMENTATION_PLAN.md §1).
        # For multi-form spells (Icebound Beam) this is the HEADLINE (continuous) form's flat; each form
        # recomputes its own flat from form.base_dmg + form.added_eff inside the hit-form loop below.
        # DEFERRED: min/max-damage reshaping (Phase 3, with Lucky); elemental-gear-flat→spell (flagged).
        flat_dmg, skill_base_dmg = _spell_flat(
            source, skill.base_dmg_by_level.get(lookup_level, {}), skill.added_dmg_effectiveness)
    else:
        # Main-hand-only additional damage (Rosa Born to Cleanse): a standard additional multiplier scoped to the
        # weapon1 base share. Injected into the flat (conversion-safe; linear pipeline ⇒ ≡ multiplying the main-hand
        # weapon's final damage by (1+mh_add)). Presence-gated via all_stats so non-Rosa consumed_stats is unchanged.
        mh_add = source.total("main_hand_dmg_additional") if "main_hand_dmg_additional" in source.all_stats() else 0.0
        for dtype in DAMAGE_TYPES:
            # Weapon implicit base, scaled by the weapon's own gear inc
            dmg_min = source.total(f"{dtype}_dmg_gear_flat_min")
            dmg_max = source.total(f"{dtype}_dmg_gear_flat_max")
            gear_inc = source.total(f"{dtype}_dmg_gear_inc")
            total_min = dmg_min * (1.0 + gear_inc)
            total_max = dmg_max * (1.0 + gear_inc)
            # Ring/gear/talent flat adds — no damage-type tag filtering; attack/spell split only
            if is_attack:
                total_min += source.total(f"{dtype}_attack_dmg_flat_min")
                total_max += source.total(f"{dtype}_attack_dmg_flat_max")
            if is_spell:
                total_min += source.total(f"{dtype}_spell_dmg_flat_min")
                total_max += source.total(f"{dtype}_spell_dmg_flat_max")
            if is_attack and mh_add:
                total_min += source.main_hand_flat(dtype, "min") * (1.0 + gear_inc) * mh_add
                total_max += source.main_hand_flat(dtype, "max") * (1.0 + gear_inc) * mh_add
            if total_min > 0 or total_max > 0:
                flat_dmg[dtype] = (total_min, total_max)

        # Elemental flat damage from weapons distributes the full amount to fire, cold, and lightning independently
        elem_min = source.total("elemental_dmg_gear_flat_min")
        elem_max = source.total("elemental_dmg_gear_flat_max")
        elem_gear_inc = source.total("elemental_dmg_gear_inc")
        scaled_elem_min = elem_min * (1.0 + elem_gear_inc)
        scaled_elem_max = elem_max * (1.0 + elem_gear_inc)
        if scaled_elem_min > 0 or scaled_elem_max > 0:
            for dtype in ("fire", "cold", "lightning"):
                existing = flat_dmg.get(dtype, (0.0, 0.0))
                flat_dmg[dtype] = (existing[0] + scaled_elem_min, existing[1] + scaled_elem_max)

    # (Flat PHYSICAL damage per N consumed — Blade-dancer/Glacier — is folded into the REAL physical_{attack,spell}_
    # dmg_flat source stats IN the compute loop, so it flows through the full flat→inc→additional pipeline incl.
    # multi-form spells and shows a source in the breakdown. See engine/compute.py consume block.)

    # 3. Per-type inc and additional — precomputed outside the hit form loop.
    #    Inc: skill-tag-filtered incs PLUS the type-specific inc for that dtype.
    #    Additional: each applicable stat is an independent multiplicative pool.
    #    A dtype-specific stat (e.g. fire_dmg_inc) applies to that dtype even if the
    #    skill is not fire-tagged (e.g. a fire ring add on a physical skill still scales).
    # Additional pools are per-AFFIX (Option A): build the factor list once, then apply the same
    # tag-scope predicates the increased pools use. Each distinct affix multiplies; same-affix
    # positives sum; each negative is its own factor. See docs/ADDITIONAL_DAMAGE_POOLING.md.
    add_factors = _build_additional_factors(source)

    # "+X% additional damage when you land a Critical Strike" (Critical Strike Damage Increase support, Razor Leaf
    # ingredient): an additional-damage factor WEIGHTED by the build's finalized crit chance — effective = X ×
    # crit_chance — folded in as a generic (all-type) additional factor. Read unconditionally so the synthetic
    # consumable-universe run consumes it; contributes nothing when absent.
    _on_crit_add = source.total("dmg_additional_on_crit")
    if _on_crit_add:
        add_factors = add_factors + [(_on_crit_add * crit_chance, frozenset(), "dmg_additional_on_crit")]

    # "For every 400 Max Energy Shield, +X% additional damage, up to +Y%" (Licorice Note's Pixie Tear ingredient):
    # min(max_es/400 × per_unit, cap), folded as a generic additional factor. Not scaled by Elixir Effect (handled
    # at emit). Read unconditionally for the consumable-universe run; nothing when absent.
    _per_400_es = source.total("dmg_additional_per_400_es")
    if _per_400_es:
        _es_amt = source.total("max_energy_shield") / 400.0 * _per_400_es
        _es_cap = source.total("dmg_additional_per_400_es_cap")
        if _es_cap:
            _es_amt = min(_es_amt, _es_cap)
        if _es_amt:
            add_factors = add_factors + [(_es_amt, frozenset(), "dmg_additional_per_400_es")]

    # "+X% ADDITIONAL damage per N Life consumed recently, up to Y%". per-unit normalized to per-1-life at parse;
    # consumed-recently is floored to whole N-chunks (discrete "for every N" procs) then × per-unit, capped. (Plain
    # "damage per N consumed" is INCREASED — folded into generic_inc below, not here.)
    _per_life_cons = source.total("dmg_additional_per_life_consumed")
    if _per_life_cons:
        _lc_amt = floored_consumed(source.total("consumed_recently_life"),
                                   source.total("dmg_additional_per_life_consumed_unit")) * _per_life_cons
        _lc_cap = source.total("dmg_additional_per_life_consumed_cap")
        if _lc_cap:
            _lc_amt = min(_lc_amt, _lc_cap)
        if _lc_amt:
            add_factors = add_factors + [(_lc_amt, frozenset(), "dmg_additional_per_life_consumed")]

    # Generic intrinsic additional multiplier — applies uniformly to EVERY damage type (not per-affix):
    #   • extra_additional: skill-intrinsic pool (e.g. Fervor / Moon Strike's mana bonus), evaluated by caller.
    #   • main_stat_factor: 1 + (Σ the skill's main-stat attribute totals) × 0.5% — the "Damage Bonus" the
    #     attribute panel shows, driven by the skill's main_stat field (NOT tags). Source: TLI Help DB.
    # Folded into BOTH type_add and generic_add below so the per-type breakdown ratio cancels it cleanly
    # (it's a uniform multiplier, not a type-specific one) and "Total Additional" still reflects it.
    main_stat_bonus = sum(source.total(a) for a in skill.main_stat) * _MAIN_STAT_DAMAGE_PER_POINT
    # Lightchaser (Chromatic Shot) raises the main-attribute damage ratio by a % (0.5%/pt → 0.625%/pt). Presence-
    # gated so builds without it consume nothing and stay golden-identical.
    _ms_inc = source.total("main_stat_dmg_bonus_inc") if "main_stat_dmg_bonus_inc" in source.all_stats() else 0.0
    main_stat_bonus *= (1.0 + _ms_inc)   # Lightchaser etc. — report + apply the BOOSTED ratio (×1 when absent)
    main_stat_factor = 1.0 + main_stat_bonus
    intrinsic_add = (1.0 + extra_additional) * main_stat_factor

    # Damage-type conversion: read fractions once. When any conversion is present, compute the per-type
    # inc/add for ALL types (a converted slice can land in a type that had no native flat); otherwise only
    # the flat types (regression-identical to the pre-conversion engine).
    convert_fracs, adds_fracs = _conversion_fracs(source)
    has_conversion = any(convert_fracs.values()) or any(adds_fracs.values())
    calc_types = list(DAMAGE_TYPES) if has_conversion else list(flat_dmg.keys())
    # Compulsory conversion (Chromatic Shot): the skill deals each of these elements, so compute their per-type
    # increased/additional too — surfaced in the Skill Hit Damage breakdown so the per-element columns match the
    # actual per-element damage (e.g. +Fire Damage shows in the Fire column).
    if skill.compulsory_elements:
        calc_types = list(dict.fromkeys(calc_types + list(skill.compulsory_elements)))
    # "You can only deal <Type> Damage" (Extreme Coldness): any FINAL (post-conversion) damage that isn't an
    # allowed type deals zero. Read only when the flag is present (all_stats avoids consuming it on every build,
    # keeping consumed_stats/goldens stable). Empty = no restriction.
    _present = source.all_stats()
    only_deal_types = {t for t in DAMAGE_TYPES
                       if f"can_only_deal_{t}" in _present and source.total(f"can_only_deal_{t}") > 0.0}

    # Rosa Unsullied Blade: "Spell Damage bonus + additional also apply to Attack Damage". Augment the DAMAGE-pool
    # tag set with "spell" for attack skills when the flag is present, so spell_dmg_inc/additional (+ per-element
    # spell damage) bridge to the attack's damage pools ONLY — crit/area/cast-speed keep plain mod_tags below.
    # Presence-gated → non-Rosa builds byte-identical.
    pool_tags = mod_tags
    if is_attack and "spell_dmg_to_attack" in _present and source.total("spell_dmg_to_attack") > 0.0:
        pool_tags = mod_tags | {"spell"}

    type_inc: dict[str, float] = {}
    type_add: dict[str, float] = {}
    for dtype in calc_types:
        # Elemental types also carry the "elemental" pseudo-tag so "increased/additional Elemental Damage"
        # (tagged 'elemental') applies to Fire/Cold/Lightning but not Erosion/Physical.
        dtype_tag = frozenset({dtype}) | ({"elemental"} if dtype in _ELEMENTAL_DMG_TYPES else frozenset())
        type_inc[dtype] = sum(
            source.total(key)
            for key, tags in _HIT_INC_STATS
            if _applies_to_dtype(tags, dtype_tag, pool_tags)
        )
        type_add[dtype] = _additional_product(
            source, add_factors,
            lambda tags, dt=dtype_tag: _applies_to_dtype(tags, dt, pool_tags),
        ) * intrinsic_add

    # Generic (non-dtype-specific) multipliers — applies uniformly to every damage type.
    # These are the "All" column values in the stats screen breakdown table.
    generic_inc = sum(
        source.total(key)
        for key, tags in _HIT_INC_STATS
        if not (tags & _DTYPE_TAG_SET) and _skill_gate(tags, pool_tags)
    )
    generic_add = _additional_product(
        source, add_factors,
        lambda tags: not (tags & _DTYPE_TAG_SET) and _skill_gate(tags, pool_tags),
    ) * intrinsic_add

    # Type-specific bonuses for the conversion cascade, computed over the UNION of a packet's path types
    # (the set of dtype-tags of every type it has been). Each type-specific modifier is counted ONCE: an
    # "increased Elemental Damage" mod applies once across an elemental→elemental hop (Lightning→Cold), not
    # once per element — verified in-game. Single-type mods (e.g. "increased Cold Damage") apply only when
    # Cold is in the path. generic_inc/add are applied once separately inside _apply_conversion.
    def _path_spec_inc(path_tags):
        return sum(source.total(k) for k, tags in _HIT_INC_STATS
                   if (tags & _DTYPE_TAG_SET & path_tags) and _skill_gate(tags, mod_tags))

    def _path_spec_add(path_tags):
        return _additional_product(
            source, add_factors,
            lambda tags: bool(tags & _DTYPE_TAG_SET & path_tags) and _skill_gate(tags, mod_tags))

    # 4. Steep strike chance: skill's intrinsic passive + stat sources, capped at 1.0
    steep_chance = min(skill.base_steep_strike_chance + source.total("steep_strike_chance"), 1.0)
    # Additional Steep Strike Damage applies ONLY to the steep-strike hit form (the high-damage proc). It's
    # a form-scoped additional multiplier on top of the generic additional pool (e.g. node sources, and
    # Berserking Blade Rampage's skill-area→steep-strike share). Only READ the stat when the skill actually
    # has a steep-strike form, so it isn't false-flagged "Consumed" for skills that can't steep strike.
    _has_steep_form = any(f.proc_stat_key == "steep_strike_chance"
                          for f in skill.hit_forms_by_level.get(lookup_level, []))
    steep_add_mult = (1.0 + source.total("steep_strike_additional_dmg")) if _has_steep_form else 1.0

    # 5. Hit rate (casts/attacks per second) — the shared "rates" stage (compute_skill_rates), which
    # uptime models also call in-loop so the APS math has one source of truth. The 30 Hz per-caster cap
    # (engine/tick.py) is applied inside it; Tangle's N casters / Spell Burst recasts multiply it later.
    _rates = compute_skill_rates(source, skill, skill_tags_lower=skill_tags_lower)
    sps = _rates["sps"]
    base_cast_time = _rates["base_cast_time"]

    # Wind Rhythm trigger panel (server-tick breakpoints) — populated when the skill is triggered by Wind Rhythm.
    _wind = None
    if "wind_rhythm_base_cooldown" in _present and source.total("wind_rhythm_base_cooldown") > 0.0:
        _wind = compute_wind_rhythm_rate(source, source.total("wind_rhythm_base_cooldown"),
                                         source.total("wind_rhythm_share"))

    # ── Tangle cast-speed breakpoints ── A Tangle is a server-scheduled proxy-player, so its per-tangle cast rate
    # hard-rounds to whole server ticks (cast-speed BREAKPOINTS) instead of the player's smooth, continuously-
    # scaling rate: ticks = ceil(cast_time × TICK_RATE), effective casts/sec = TICK_RATE / ticks. So extra cast
    # speed only helps when it crosses an integer-tick boundary (flat dead zones between breakpoints — e.g. 6.04
    # and 7.44 casts/s both land on 5 ticks → 6.0/s, Tyra-verified). Quantizing sps here flows the breakpoint
    # rate into every hit form's DPS and the displayed casts/sec; the attached-tangle count multiplies it after.
    # The 30 Hz per-caster cap still holds via period_ticks' 1-tick floor. See engine/tick.py (opt-in regime).
    tangle_cast_ticks = 0
    # MORE cast speed needed to reach the next (faster) tick breakpoint, in BOTH forms (each independently gets
    # you there). Additional = a new ×(1+x) factor → x = target/current − 1. Increased adds into the shared
    # increased pool, so it dilutes against the existing total → ΔI = (1 + current increased) × x.
    tangle_cast_to_next_increased = 0.0
    tangle_cast_to_next_additional = 0.0
    if tangle and sps > 0.0:
        _sps_raw = sps                                   # smooth cast speed before tick-rounding
        tangle_cast_ticks = period_ticks(1.0 / _sps_raw)
        sps = rate_from_ticks(tangle_cast_ticks)
        if tangle_cast_ticks > 1:
            _next_cs = rate_from_ticks(tangle_cast_ticks - 1)   # cast speed needed for (ticks − 1)
            _x = max(0.0, _next_cs / _sps_raw - 1.0)
            tangle_cast_to_next_additional = _x
            tangle_cast_to_next_increased = (1.0 + source.total("cast_speed_inc")) * _x

    # ── Channeled attacks fire at the SMOOTH attack rate (no 30 Hz breakpoint) ── Split Shot: Rapid Advance
    # snapped to whole 30 Hz ticks ~3 seasons ago, but that quirk was removed in-game; channeled attacks (likely
    # all of them) now fire smoothly, and the breakpoint regime is unrelated to channeling. Verified in-game: the
    # flat-damage-per-consume ramps CONTINUOUSLY with attack speed, which a breakpoint would freeze flat across a
    # tick band. So `sps` is left as the smooth rate (channeled_attack_fire_rate is a no-op) and the channel-
    # breakpoint fields stay 0 → the "Attack Ticks / next breakpoint" rows don't render; the normal Attacks-per-
    # Second row shows the true rate. Fields kept for schema stability / any future skill that genuinely snaps.
    channel_attack_ticks = 0
    channel_attack_smooth_sps = 0.0
    channel_attack_to_next_increased = 0.0
    channel_attack_to_next_additional = 0.0

    # ── Channeled cadence ── 1 stack per use; a RESET skill ramps 0→max over `rounds_per_cycle` uses then
    # dumps + fires its burst form once per cycle. Min Channeled Stacks shortens the ramp (first round gains
    # 1+Min). The continuous form fires every use (sps); the burst form fires at sps / rounds_per_cycle.
    # cycle_time is constant here (Icebound never sits AT max → any not-at-max cast speed applies every round),
    # so both forms anchor to the same sps — see the channeled framework plan. 0 / 1.0 when not channeled.
    ch_max_stacks = 0
    ch_min_stacks = 0
    ch_rounds_per_cycle = 0.0
    ch_burst_rate = 0.0
    ch_behavior = ""
    ch_attack_frequency = 0.0   # persistent-entity strike rate (Howling Gale's Gale); 0 = not used
    if skill.channeled:
        ch_max_stacks = int(skill.channeled.max_stacks) + int(source.total("max_channeled_stacks_flat"))
        ch_min_stacks = int(skill.channeled.min_stacks) + int(source.total("min_channeled_stacks_flat"))
        ch_max_stacks = max(1, ch_max_stacks)
        ch_min_stacks = max(0, min(ch_min_stacks, ch_max_stacks))
        ch_rounds_per_cycle = uptime.channeled_rounds_per_cycle(ch_max_stacks, ch_min_stacks)
        ch_burst_rate = sps / ch_rounds_per_cycle if ch_rounds_per_cycle else sps
        ch_behavior = skill.channeled.behavior
        # Persistent entity (Gale): its strike rate = attack_frequency × the cast-speed multiplier. sps already =
        # (1/base_cast_time) × cast-speed product, so cast_speed_mult = sps × base_cast_time and the Gale rate =
        # attack_frequency × cast_speed_mult. sps stays the channel build rate (shown separately).
        if skill.channeled.attack_frequency:
            cs_mult = sps * base_cast_time if base_cast_time else 1.0
            ch_attack_frequency = skill.channeled.attack_frequency * cs_mult
            # Furious Sweep: +X% additional Gale Attack Frequency per channeled stack. The hook bakes the total
            # (per-stack × current stacks) into channeled_attack_frequency_additional; we apply it as an additional
            # multiplier on the Gale rate (does NOT touch the channel build rate / sps).
            freq_add = source.total("channeled_attack_frequency_additional")
            if freq_add:
                ch_attack_frequency *= 1.0 + freq_add

    # Augmentation: per-Jump (multiplies) compounding factor on hit damage. Scales with jumps REMAINING;
    # on a lone dummy the single hit is the first hit (full jumps remaining = total jumps), and
    # Augmentation excludes Web so there is no multi-hit chain here. Shows in per-hit damage.
    aug_factor = 1.0
    if support_behavior and support_behavior.get("augmentation_per_jump"):
        total_jumps = max(0, skill.jumps_base + int(source.total("extra_jumps_flat")))
        aug_factor = (1.0 + float(support_behavior["augmentation_per_jump"])) ** total_jumps
    # Lucky: the skill rolls damage twice and keeps the higher. Modelled as a per-type expected-value
    # scalar computed from the flat [min,max] spread (scale-invariant), applied to the average only —
    # it lifts DPS but not the displayed min/max range, and is distinct from crit.
    lucky_damage = bool(support_behavior and support_behavior.get("lucky_damage"))

    # 6. Per hit form
    # Effectiveness % stays at the max-level value when above max level.
    # Instead, a compounding additional multiplier is applied to all hit damage.
    above_mult = _above_max_mult(effective_level, skill.max_level)
    hit_forms: list[HitFormResult] = []
    # Pre-scan the projectile-scaling (reset burst) form's count, BEFORE the loop, so the continuous form
    # (processed first) knows whether the burst fires — and thus whether it's suppressed. -1 = no such form.
    compulsory_breakdown: dict[str, dict] = {}   # Chromatic Shot: per-element {hit_min,hit_max,avg_pre_crit,avg_with_crit,mitigation}
    projectile_count = -1
    projectile_base_count = 0   # the skill's OWN projectiles (before +Projectile Quantity mods) — for the breakdown
    for _f in skill.hit_forms_by_level.get(lookup_level, []):
        if _f.scales_with_projectiles:
            _n = max(0, _f.hit_count + int(source.total("projectile_quantity_flat")))
            projectile_count = _n if projectile_count < 0 else max(projectile_count, _n)
            projectile_base_count = max(projectile_base_count, _f.hit_count)
    # The reset burst fires when its projectile count ≥ 1 → the continuous form is then suppressed.
    burst_active = projectile_count >= 1
    for form in skill.hit_forms_by_level.get(lookup_level, []):
        eff = form.effectiveness_pct

        if form.proc_stat_key == "steep_strike_chance":
            proc = steep_chance
            form_add_mult = steep_add_mult   # additional Steep Strike Damage hits only this form
        elif form.proc_stat_key == "_complement_steep_strike_chance":
            proc = 1.0 - steep_chance
            form_add_mult = 1.0
        else:
            proc = 1.0
            form_add_mult = 1.0

        # Channeled RESET redistribution: while the burst form fires, the CONTINUOUS form's damage is
        # suppressed (Icebound Beam's Cold Beam drops to 1/3 once Icy Blades fire). Folded into form_add_mult
        # so it scales the per-hit damage too (Hit Range shows the suppressed value). No effect at 0 projectiles.
        if (skill.channeled and skill.channeled.behavior == "reset"
                and form.channel_role == "continuous" and burst_active
                and not source.total("continuous_suppression_disable")):
            # Chilling Spike (Icebound) sets continuous_suppression_disable → the Cold Beam runs at FULL
            # damage even while the Icy Blades fire (Tyra-validated: beam 30-40 vs the normal 9-12).
            form_add_mult *= skill.channeled.continuous_suppression_when_bursting

        damage_by_type: dict[str, float] = {}
        hit_min_by_type: dict[str, float] = {}
        hit_max_by_type: dict[str, float] = {}
        avg_pre = 0.0
        avg_pre_vs_target = 0.0
        # Multi-form SPELL base: a form with its own base_dmg (e.g. Icebound Beam's Cold Beam / Icy Blade)
        # recomputes its flat from THAT base + the shared added flat scaled by THIS form's effectiveness
        # (added_eff). Other forms use the skill-wide flat_dmg built above. base stays unscaled either way.
        form_flat = flat_dmg
        form_base = skill_base_dmg
        if form.base_dmg is not None:
            form_eff = form.added_eff if form.added_eff is not None else skill.added_dmg_effectiveness
            form_flat, form_base = _spell_flat(source, form.base_dmg, form_eff)
        if skill.compulsory_elements and form.base_dmg is None:
            # COMPULSORY conversion (Chromatic Shot): fold the type-agnostic base + ALL added spell flat (every
            # type, ×eff) into one pool, then deal it as EACH element FULLY (only that element's increased/additional
            # — _apply_conversion with no conversion fracs reproduces the native (1+type_inc)×type_add for one type).
            # The headline is the EXPECTED average across the elements (random/rotated 1/3 each); per-element detail
            # is stashed in compulsory_breakdown for the C+D display.
            b_min, b_max = skill.base_flat_by_level.get(lookup_level, (0.0, 0.0))
            em = skill.added_dmg_effectiveness
            add_min = sum(source.total(f"{t}_spell_dmg_flat_min") for t in DAMAGE_TYPES)
            add_max = sum(source.total(f"{t}_spell_dmg_flat_max") for t in DAMAGE_TYPES)
            tot = (b_min + add_min * em, b_max + add_max * em)
            elems = skill.compulsory_elements
            for e in elems:
                conv_e = _apply_conversion({e: tot}, _path_spec_inc, _path_spec_add, generic_inc, generic_add, {}, {})
                smin, smax = conv_e.get(e, (0.0, 0.0))
                vuln = _enemy_vuln_mult(source, e, is_spell)
                e_min = smin * above_mult * vuln * aug_factor * form_add_mult
                e_max = smax * above_mult * vuln * aug_factor * form_add_mult
                # Lucky (+1) / Unlucky (−1) DAMAGE roll for this type — roll twice keep higher/lower; they cancel.
                _lvl_e = (1 if (lucky_damage or source.total(f"lucky_{e}") > 0.0) else 0) \
                    - (1 if source.total(f"unlucky_{e}") > 0.0 else 0)
                e_avg = ((e_min + e_max) / 2.0) * _luck_ratio(e_min, e_max, _lvl_e)
                e_mit = _target_mitigation(source, e)
                compulsory_breakdown[e] = {
                    "hit_min": e_min, "hit_max": e_max, "avg_pre_crit": e_avg,
                    "avg_with_crit": e_avg * crit_factor * double_dmg_factor, "mitigation": e_mit,
                }
                avg_pre += e_avg
                avg_pre_vs_target += e_avg * e_mit
            n = float(len(elems) or 1)
            avg_pre /= n
            avg_pre_vs_target /= n
            # Headline form damage_by_type = each element's 1/n share (so it sums to the expected average).
            damage_by_type = {e: compulsory_breakdown[e]["avg_pre_crit"] / n for e in elems}
            hit_min_by_type = {e: compulsory_breakdown[e]["hit_min"] for e in elems}
            hit_max_by_type = {e: compulsory_breakdown[e]["hit_max"] for e in elems}
        else:
            # Conversion stage: apply this form's effectiveness to the flat, then cascade through the
            # conversion chain. _apply_conversion returns each FINAL type's (min,max) already scaled by
            # (1 + path increases) × (path additionals) × generic; per-final-type factors (enemy vuln,
            # above-max, augmentation) and Lucky apply below. No conversion → final == native per-type result.
            eff_flat = {t: (mn * (eff / 100.0), mx * (eff / 100.0)) for t, (mn, mx) in form_flat.items()}
            converted = _apply_conversion(eff_flat, _path_spec_inc, _path_spec_add, generic_inc, generic_add,
                                          convert_fracs, adds_fracs)
            for dtype, (smin, smax) in converted.items():
                # "You can only deal <Type>" — a FINAL packet left as a non-allowed type deals zero (applied AFTER
                # conversion, so damage that converted INTO an allowed type still counts).
                if only_deal_types and dtype not in only_deal_types:
                    continue
                # Enemy-vulnerability (Numbed etc.) and Augmentation are per-FINAL-type / global multipliers.
                vuln = _enemy_vuln_mult(source, dtype, is_spell)
                type_min = smin * above_mult * vuln * aug_factor * form_add_mult
                type_max = smax * above_mult * vuln * aug_factor * form_add_mult
                # Lucky (+1) / Unlucky (−1) DAMAGE roll, keyed off the FINAL type (Lucky tested in-game): EV uplift/
                # downlift from the spread, applied to the average. Lucky + Unlucky on the same type cancel.
                _lvl_t = (1 if (lucky_damage or source.total(f"lucky_{dtype}") > 0.0) else 0) \
                    - (1 if source.total(f"unlucky_{dtype}") > 0.0 else 0)
                avg = ((type_min + type_max) / 2.0) * _luck_ratio(type_min, type_max, _lvl_t)
                damage_by_type[dtype] = avg
                hit_min_by_type[dtype] = type_min
                hit_max_by_type[dtype] = type_max
                avg_pre += avg
                avg_pre_vs_target += avg * _target_mitigation(source, dtype)

        # Crit (expected-value) and double-damage (expected-value) both uplift the average, not per-hit. crit_factor
        # already reflects the effective crit chance (post Lucky/Unlucky crit).
        avg_post = avg_pre * crit_factor * double_dmg_factor
        avg_post_vs_target = avg_pre_vs_target * crit_factor * double_dmg_factor

        # Per-form firing rate. Default = sps (every use). Channeled: a "burst" form fires once per RESET
        # cycle (sps / rounds_per_cycle); a "continuous" form fires every use, except when the dump use
        # REPLACES the continuous hit (burst_replaces_continuous) → it fires (rounds−1)/rounds of the time.
        # Icebound Beam is additive (beam fires every round, Tyra-confirmed) so the beam stays at sps.
        form_rate = sps
        if skill.channeled and form.channel_role == "burst":
            form_rate = ch_burst_rate
        elif skill.channeled and form.channel_role == "continuous" and ch_attack_frequency:
            # Persistent entity (Howling Gale's Gale): the continuous damage fires at the Gale's strike rate,
            # not the channel build rate.
            form_rate = ch_attack_frequency
        elif (skill.channeled and form.channel_role == "continuous"
              and skill.channeled.burst_replaces_continuous and ch_rounds_per_cycle > 1):
            form_rate = sps * (ch_rounds_per_cycle - 1.0) / ch_rounds_per_cycle
        # Projectile count for this form. Projectile-scaling forms (Icy Blade) add +Projectile Quantity to
        # the base count; all projectiles home onto one target and shotgun (1st full + each subsequent
        # ×(1−falloff), linear — every subsequent deals (1−falloff) of the first). Such a form can drop to
        # 0 projectiles (reduced Projectile Quantity) → it does NOT fire, isolating the continuous form.
        # Non-scaling forms always fire (≥1 hit).
        if form.scales_with_projectiles:
            n_proj = max(0, form.hit_count + int(source.total("projectile_quantity_flat")))
        else:
            n_proj = max(1, form.hit_count)
        # Compulsory skills (Chromatic Shot): only the projectiles that LAND on the target shotgun. Cap the hit
        # count at "shots on target" (a user input the chromatic_shot module emits — full count under Lightchaser/
        # tangle; default 7 otherwise). Presence-gated so non-chromatic skills are unaffected.
        if skill.compulsory_elements:
            shots = (int(source.total("chromatic_shots_on_target_flat"))
                     if "chromatic_shots_on_target_flat" in source.all_stats() else 7)
            if shots >= 1:
                n_proj = min(n_proj, shots)
        # Shotgun-Effect gating (Split Shot): a projectile-scaling form on a skill with NO innate Shotgun Effect
        # ("the Projectiles shot by this skill cannot hit the same enemy") lands only 1 projectile on a single
        # target UNTIL a support grants Shotgun Effect (Volley → same_target_shotgun_grant). Distinct from
        # spread/trajectory. Presence-gated so other skills stay byte-identical.
        if skill.shotgun_requires_grant and form.scales_with_projectiles:
            granted = ("same_target_shotgun_grant" in source.all_stats()
                       and source.total("same_target_shotgun_grant") > 0.0)
            if not granted:
                n_proj = 1
        form_shotgun = (1.0 + (n_proj - 1) * (1.0 - form.shotgun_falloff)) if n_proj >= 1 else 0.0

        # Icebound Beam canvas supports add extra Icy Blade damage onto the projectile-scaling (burst) form:
        #   - Chilling Spike: extra penetrating blades, NO shotgun falloff — a net single-target
        #     blade-equivalent count (icy_blade_extra_blade_equiv) fired at the burst rate.
        #   - Ring Blade (Frozen proc): a full extra Icy Blade burst per its cooldown (icy_blade_frozen_burst_rate
        #     = 1/cooldown), gated on enemy_frozen by the support. The proc fires on the FIRST beam hit AFTER each
        #     cooldown, and the beam hits at the channel rate (sps) — so the EFFECTIVE rate is sps/ceil(sps×cooldown),
        #     capped at the 1/cooldown ceiling. Higher cast speed pushes it toward the ceiling (Tyra-validated;
        #     the small ε absorbs the 0.333s parse so a clean 3/s lands exactly 1 proc/s, not the 4th hit).
        # Ring Blade's Frozen burst stays on Icy Blade (it IS an extra Icy Blade burst); Chilling Spike's extra
        # penetrating blades are split into their OWN form below (chilling_extra), so the total is unchanged but
        # the breakdown shows Chilling Spike separately and the form selector can isolate it.
        chilling_equiv = 0.0
        chilling_extra = 0.0
        form_extra_mult = 0.0
        if form.scales_with_projectiles:
            frozen_rate = source.total("icy_blade_frozen_burst_rate")
            eff_frozen = 0.0
            if frozen_rate > 0.0 and sps > 0.0:
                cooldown = 1.0 / frozen_rate
                hits_per_cd = max(1, math.ceil(sps * cooldown - 0.05))
                eff_frozen = min(frozen_rate, sps / hits_per_cd)
            chilling_equiv = source.total("icy_blade_extra_blade_equiv")
            chilling_extra = chilling_equiv * form_rate
            form_extra_mult = eff_frozen * form_shotgun   # Frozen burst only — Chilling Spike is its own form

        hit_forms.append(HitFormResult(
            name=form.name,
            effectiveness_pct=eff,
            form_type=form.form_type,
            proc_chance=proc,
            damage_by_type=damage_by_type,
            avg_hit_pre_crit=avg_pre,
            avg_hit_with_crit=avg_post,
            # Original term kept verbatim (+ extra term, which is 0.0 for non-Icy-Blade forms → no ULP drift).
            dps_contribution=avg_post * form_rate * proc * form_shotgun + avg_post * proc * form_extra_mult,
            dps_vs_target=avg_post_vs_target * form_rate * proc * form_shotgun + avg_post_vs_target * proc * form_extra_mult,
            hit_min_by_type=hit_min_by_type,
            hit_max_by_type=hit_max_by_type,
            fires_per_sec=form_rate * proc,
            hits_per_fire=n_proj,
            shotgun_falloff=form.shotgun_falloff,
            shotgun_mult=form_shotgun,
            base_min_by_type={t: mn for t, (mn, _) in form_base.items()},
            base_max_by_type={t: mx for t, (_, mx) in form_base.items()},
        ))

        # Chilling Spike (Icebound canvas support): its extra penetrating blades — split off Icy Blade into their
        # own additive form so the breakdown/selector treats them distinctly. Same per-hit damage as Icy Blade;
        # the net single-target blade-equivalent (chilling_equiv, no shotgun) rides the burst rate. Total DPS is
        # unchanged (this slice was previously folded into Icy Blade's form_extra_mult).
        if form.scales_with_projectiles and chilling_extra > 0.0:
            hit_forms.append(HitFormResult(
                name="Chilling Spike",
                effectiveness_pct=eff,
                form_type="additive",
                proc_chance=proc,
                damage_by_type=damage_by_type,
                avg_hit_pre_crit=avg_pre,
                avg_hit_with_crit=avg_post,
                dps_contribution=avg_post * proc * chilling_extra,
                dps_vs_target=avg_post_vs_target * proc * chilling_extra,
                hit_min_by_type=hit_min_by_type,
                hit_max_by_type=hit_max_by_type,
                # Fires WITH Icy Blade (same burst rate at max channeled stacks). The 0.69 net single-target
                # blade-equivalent is a per-occurrence damage factor (stored in shotgun_mult, not the rate),
                # so dps = avg × rate × equiv reconciles without faking a slower cadence.
                fires_per_sec=form_rate * proc,
                hits_per_fire=1,
                shotgun_falloff=0.0,
                shotgun_mult=chilling_equiv,
                base_min_by_type={t: mn for t, (mn, _) in form_base.items()},
                base_max_by_type={t: mx for t, (_, mx) in form_base.items()},
            ))

    # Same-target shotgun (Merge lands Web's per-Jump chains on the same target). First hit 100%, each
    # subsequent (one per Jump) deals (1 − falloff). Scales total DPS only; per-hit damage unchanged.
    cast_multiplier = 1.0
    shotgun_hits = 1
    if support_behavior and support_behavior.get("same_target_shotgun") and support_behavior.get("chains_per_jump"):
        total_jumps = skill.jumps_base + int(source.total("extra_jumps_flat"))
        subsequent = max(0, total_jumps) * int(support_behavior["chains_per_jump"])
        cast_multiplier = 1.0 + subsequent * (1.0 - float(support_behavior["falloff_coefficient"]))
        shotgun_hits = 1 + subsequent

    # Tangle mode: N attached tangles each cast the skill (full caster), so the DPS scales by the count; Tangle
    # Damage Enhancement is its own ×(1 + Σ) multiplier (additive within itself), separate from the inc/additional
    # pools. Both fold into the DPS totals (the per-hit-form damage is unchanged), like the shotgun multiplier.
    tangle_count = int(tangle["count"]) if tangle else 0
    # Tangle Damage Enhancement now rides the ADDITIONAL pool (summed into one factor — see
    # _build_additional_factors), so it's ALREADY in each hit's damage. tangle_enhancement is kept only for the
    # Tangle panel display (the ×factor); the DPS total multiplier is the attached count alone.
    tangle_enhancement = (1.0 + source.total("tangle_dmg_enhancement_additional")) if tangle else 1.0
    tangle_mult = float(tangle_count) if tangle else 1.0
    tangle_placeable = int(tangle["placeable"]) if tangle else 0
    tangle_inactivated = int(tangle["inactivated"]) if tangle else 0
    tangle_duration = (8.0 * (1.0 + source.total("tangle_duration_inc"))
                       * (1.0 + source.total("tangle_duration_additional"))) if tangle else 0.0
    tangle_attach_range = (8.0 * (1.0 + source.total("tangle_attach_range_inc"))) if tangle else 0.0

    # Spell Burst mode: an eligible Spell cast at full charge consumes all M stacks and auto-recasts the spell
    # M times (the triggering cast also counts → casts_per_burst = M + 1, no damage cap — every stack is a full
    # cast). The charge is a server-timed whole-tick countdown, so it hard-rounds (engine/tick.py); the player's
    # cast rate stays smooth (already 30-capped above). Final delivery multiplier folds into total_dps.
    # Manual triggering = COMBINED model: the player keeps casting between bursts, so total DPS = burst casts
    # (the M+1-per-proc, boosted by the spell_burst pool) PLUS the normal casts in between (no spell_burst pool).
    # Auto-trigger (Solid River / Burst Activation) = burst-only: you almost never cast manually with those, so
    # the between-burst casts are excluded. The two parts are surfaced distinctly (spell_burst_dps / non_..._dps).
    spell_burst_count = 0
    spell_burst_casts_per_burst = 0
    spell_burst_charge_ticks = 0
    spell_burst_charge_time = 0.0
    spell_burst_charge_factor = 1.0
    spell_burst_charge_inc = 0.0
    spell_burst_charge_to_next_inc = 0.0
    spell_burst_charge_to_next_add = 0.0
    spell_burst_cast_to_next_inc = 0.0
    spell_burst_cast_to_next_add = 0.0
    spell_burst_play_safe = False   # Play Safe couples cast speed → charge speed (so cast speed is also a lever)
    spell_burst_next_breakpoint_ticks = 0
    spell_burst_rate = 0.0
    spell_burst_mult = 1.0
    spell_burst_dps = 0.0
    spell_burst_dps_vs_target = 0.0
    non_spell_burst_dps = 0.0
    non_spell_burst_dps_vs_target = 0.0
    spell_burst_area_display = 0.0   # DISPLAY-only: Skill Area for skills cast by Spell Burst (Prairie Fire / Ripple)
    spell_burst_auto = bool(spell_burst.get("auto")) if spell_burst else False
    spell_burst_auto_source = spell_burst.get("auto_source", "") if spell_burst else ""
    if spell_burst:
        M = max(0, int(spell_burst["count"]))
        spell_burst_count = M
        spell_burst_casts_per_burst = M + 1
        # Skill-Area-per-Burst (DISPLAY only): support pool is pre-scaled ×min(M,cap) in compute; the _per pool is
        # per-burst-stack (×M, Kismet Ripple). Added to the shown skill_area_inc below — never touches DPS.
        spell_burst_area_display = (source.total("spell_burst_area_additional")
                                    + M * source.total("spell_burst_area_additional_per"))
        # Base charge time 2s, sped by Spell Burst Charge Speed: (1 + Σ inc) additive × Π(1 + add_i) per-source.
        # Play Safe feeds cast-speed bonuses into these pools (aggregator). Higher chargeFactor → shorter charge.
        charge_inc = source.total("spell_burst_charge_speed_inc")
        charge_add_product = additional_total_product(source, "spell_burst_charge_speed_additional")
        charge_factor = max(1e-6, (1.0 + charge_inc) * charge_add_product)
        spell_burst_charge_factor = charge_factor
        spell_burst_charge_inc = charge_inc
        spell_burst_play_safe = source.total("cast_speed_to_spell_burst_charge") > 0.0
        T = 2.0 / charge_factor
        # Surging Inspiration: each cast has a chance to immediately gain Spell Burst Charge stacks; the
        # expected stacks/cast (spell_burst_chance_gain_stacks_flat) over the (capped) cast rate is an
        # alternative fill that can reach max faster than the base charge. T_eff = min(T, M / surging_rate).
        # Shape flagged for in-game verification (SPELLBURST-01).
        surging_rate = sps * source.total("spell_burst_chance_gain_stacks_flat")  # stacks/sec (sps already 30-capped)
        T_eff = T
        if surging_rate > 0.0 and M > 0:
            T_eff = min(T, M / surging_rate)
        spell_burst_charge_time = T_eff
        # Whole-tick charge period (server-timed → ceil). Auto-trigger fires the instant it completes.
        charge_ticks = period_ticks(T_eff)
        spell_burst_charge_ticks = charge_ticks
        # Finalize auto-trigger from the stat-driven sources (needs charge_factor): an unconditional flag (Burst
        # Activation), or Solid River's CONDITIONAL threshold (auto only when charge_factor ≥ N×base). The toggle
        # passed from compute already set spell_burst_auto. Done BEFORE bursts so the combined/burst-only split is right.
        if not spell_burst_auto:
            if source.total("spell_burst_auto_trigger_flag") > 0:
                spell_burst_auto = True
                spell_burst_auto_source = spell_burst_auto_source or "Burst Activation"
            else:
                # Solid River checks "Burst Charge Recovery Speed ≥ N% of base" against the INCREASED total only,
                # BEFORE additional bonuses (verified in-game) — so compare (1 + Σ increased), not charge_factor.
                _auto_thr = source.total("spell_burst_auto_charge_threshold")
                if _auto_thr > 0 and (1.0 + charge_inc) >= _auto_thr:
                    spell_burst_auto = True
                    spell_burst_auto_source = spell_burst_auto_source or "Solid River / Vorax"
        # Bursts/sec. AUTO: fires the tick the charge completes → 30 / charge_ticks. MANUAL: the player must cast
        # at/after the charge completes; both the cast cadence and the charge are whole-tick server quantities, so
        # the proc period rounds up to the next whole cast after the charge → proc_ticks = ceil(charge/cast)·cast,
        # bursts = 30 / proc_ticks (verified in-game at the 43- and 45-tick breakpoints). This is intentionally
        # non-monotonic at the tick level — the same server-timing quirk as Split Shot's 15→29→30 — so the
        # breakpoint helper below SCANS rather than assumes monotonicity.
        def _bursts(aps_v: float, ticks_v: int) -> float:
            if spell_burst_auto:
                return rate_from_ticks(ticks_v)
            if aps_v <= 0.0:
                return 0.0
            ct = max(1, round(TICK_RATE / aps_v))
            return TICK_RATE / (math.ceil(ticks_v / ct) * ct)
        bursts_per_sec = min(_bursts(sps, charge_ticks), float(TICK_RATE))
        spell_burst_rate = bursts_per_sec
        # Breakpoint helper — the next investment that ACTUALLY raises bursts/sec (and thus DPS); steps that change
        # nothing are skipped. Two levers, scanned so the Play Safe cast→charge coupling is handled exactly:
        #   • Charge Speed — shortens the charge, dropping ceil(sps·T) at integer crossings → stepped gains.
        #   • Cast Speed (MANUAL only) — raises sps (the bursts numerator) and, with Play Safe, also feeds charge.
        # Auto ignores cast speed (no manual casting); for auto every whole charge tick is a real gain.
        if charge_add_product > 0 and sps > 0.0:
            if spell_burst_auto:
                if charge_ticks > 1:
                    spell_burst_next_breakpoint_ticks = charge_ticks - 1
                    # Increased dilutes against the existing increased pool; Additional is a fresh ×(1+x) factor.
                    spell_burst_charge_to_next_inc = max(
                        0.0, (60.0 / ((charge_ticks - 1) * charge_add_product) - 1.0) - charge_inc)
                    spell_burst_charge_to_next_add = max(
                        0.0, 60.0 / ((charge_ticks - 1) * charge_factor) - 1.0)
            else:
                # Charge speed — Increased (adds into pool) then Additional (new ×factor); each scanned to the
                # first step that actually raises bursts/sec (the tick math is non-monotonic, so we scan).
                dc = 0.0
                while dc < 5.0:
                    dc += 0.01
                    ct2 = period_ticks(2.0 / max((1.0 + charge_inc + dc) * charge_add_product, 1e-6))
                    if _bursts(sps, ct2) > bursts_per_sec + 1e-9:
                        spell_burst_charge_to_next_inc = dc
                        spell_burst_next_breakpoint_ticks = ct2
                        break
                dca = 0.0
                while dca < 5.0:
                    dca += 0.01
                    ct2 = period_ticks(2.0 / max((1.0 + charge_inc) * charge_add_product * (1.0 + dca), 1e-6))
                    if _bursts(sps, ct2) > bursts_per_sec + 1e-9:
                        spell_burst_charge_to_next_add = dca
                        break
                # Cast speed (manual) — raises the bursts numerator; with Play Safe (ps_coeff>0) the coupled share
                # also shortens the charge. Modeled for both Increased and Additional cast speed.
                cast_inc = source.total("cast_speed_inc")
                ps_coeff = source.total("cast_speed_to_spell_burst_charge")  # Play Safe: cast→charge share (0 if none)
                base_k = sps / (1.0 + cast_inc) if (1.0 + cast_inc) > 0 else sps   # sps = base_k × (1+cast_inc)
                d = 0.0
                while d < 5.0:
                    d += 0.01
                    sps2 = min(base_k * (1.0 + cast_inc + d), float(TICK_RATE))
                    ct2 = period_ticks(2.0 / max((1.0 + charge_inc + ps_coeff * d) * charge_add_product, 1e-6))
                    if _bursts(sps2, ct2) > bursts_per_sec + 1e-9:
                        spell_burst_cast_to_next_inc = d
                        break
                da = 0.0
                while da < 5.0:
                    da += 0.01
                    sps2 = min(sps * (1.0 + da), float(TICK_RATE))
                    ct2 = period_ticks(2.0 / max((1.0 + charge_inc + ps_coeff * da) * charge_add_product, 1e-6))
                    if _bursts(sps2, ct2) > bursts_per_sec + 1e-9:
                        spell_burst_cast_to_next_add = da
                        break
        # Cast accounting (per second). Each burst's triggering cast IS one of the player's casts and is counted
        # as a burst cast (M+1 total per proc, all boosted by the spell_burst pool). The remaining player casts
        # are normal (no pool). Auto-trigger → the player isn't casting manually, so no normal casts.
        burst_casts_per_sec = spell_burst_casts_per_burst * bursts_per_sec
        if spell_burst_auto:
            normal_casts_per_sec = 0.0
        else:
            normal_casts_per_sec = max(0.0, sps - bursts_per_sec)   # subtract the triggering casts (now burst casts)
        # Normal casts deal LESS than burst casts by exactly the spell_burst additional pool (the only per-cast
        # difference between a burst and a normal cast). sb_pool_factor = per_cast_burst / per_cast_normal.
        sb_pool_factor = 1.0
        for amt, ftags, _sk in add_factors:
            if "spell_burst" in ftags:
                sb_pool_factor *= (1.0 + amt)
        sb_pool_factor = max(sb_pool_factor, 1e-9)
        # Fold everything into ONE multiplier on the (burst-damage) per-cast totals so the breakdown table still
        # reconciles with a single scalar: spell_burst_mult = (burst casts + normal casts ÷ pool) ÷ sps. Auto →
        # normal term is 0 → mult = (M+1)·bursts/sec ÷ sps (pure burst). The burst/normal split is reported too.
        if sps > 0.0:
            burst_share = burst_casts_per_sec / sps
            normal_share = (normal_casts_per_sec / sb_pool_factor) / sps
            spell_burst_mult = burst_share + normal_share
            base_dps = sum(f.dps_contribution for f in hit_forms)
            base_dps_vt = sum(f.dps_vs_target for f in hit_forms)
            delivery = cast_multiplier * tangle_mult
            spell_burst_dps = base_dps * delivery * burst_share
            spell_burst_dps_vs_target = base_dps_vt * delivery * burst_share
            non_spell_burst_dps = base_dps * delivery * normal_share
            non_spell_burst_dps_vs_target = base_dps_vt * delivery * normal_share
        else:
            spell_burst_mult = 0.0

    # ── Multistrike (attack skills) ──────────────────────────────────────────────────────────────────────
    # Using an attack skill has a chance to auto-repeat it; the +20% INCREASED attack speed during multistrike applies
    # to the WHOLE chain (first hit included — it is "during multistrike" for attack speed) the moment a swing becomes
    # a chain (Tyra-verified by throughput: 116% chance / 1.5 base → measured ~1.92 attacks/sec = the multistrike rate
    # 1.935, not the 1.78 a "first hit slow, repeats fast" model predicts). When chance ≥ 100% every swing is a chain,
    # so every attack runs at sps×s. When chance < 100% (rare) the swings that DON'T multistrike are lone base-speed
    # attacks and get NO +20% — handled per-outcome below. Damage is time-weighted with increasing damage (the n-th
    # attack of a chain gets (n−1) increment stacks; Initial Multistrike Count pre-stacks the count without adding
    # attacks). multiplier = E[chain damage] ÷ (E[chain time] × sps); for chance ≥ 100% this is s × E[f(L)] ÷ (1 + c).
    # Gated to attack skills (not spell/channeled/mobility/sentry) with chance > 0; reads are presence-gated
    # (mirror enemy_mult / only_deal_cold) so non-multistrike builds stay golden-identical. Plan: docs.
    multistrike_mult = 1.0
    multistrike_chance = 0.0
    multistrike_avg_count = 0.0
    multistrike_increment = 0.0
    multistrike_max_count = 0
    multistrike_repeat_aps = 0.0
    multistrike_chain: list = []
    if (is_attack and not skill.channeled and not demolisher
            and "mobility" not in skill_tags_lower and "sentry" not in skill_tags_lower
            and "multistrike_chance" in _present and source.total("multistrike_chance") > 0.0):
        c = source.total("multistrike_chance")
        inc = source.total("multistrike_increasing_dmg_inc") * (1.0 + source.total("multistrike_increasing_dmg_additional"))
        init = source.total("initial_multistrike_count_flat")   # pre-stacks the count (adds NO attacks)
        q = source.total("multistrike_max_count_proc_chance")    # Cat Dive: chance to count an attack at Max Count
        # +20% Attack Speed during multistrike is INCREASED — it adds into the increased AS pool for the REPEAT
        # attacks (Tyra-verified: at +9% increased AS, 1.5 → 1.935 = 1.5×(1+0.09+0.20), NOT 1.635×1.20). So the
        # repeat AS factor dilutes against existing increased AS, like every increased source.
        as_inc = source.total("attack_speed_inc")
        s = (1.0 + as_inc + 0.20) / (1.0 + as_inc)
        G = int(math.floor(c))
        p = c - G
        K = 1 + G + (1 if p > 1e-9 else 0)                       # longest possible chain = Max Multistrike Count

        def _chain_dmg(L: int) -> float:
            # Σ n=1..L of (1 + inc·(init + n − 1)) = L + inc·(init·L + L(L−1)/2)
            base = L + inc * (init * L + L * (L - 1) / 2.0)
            if q > 0.0:
                # Cat Dive (Tyra): with prob q, an attack deals damage as the FINAL attack of THIS chain (realized
                # length L), gaining inc·(L−n) stacks. Σ n=1..L of (L−n) = L(L−1)/2 (final attack & a lone length-1
                # swing add 0). Independent of init (it cancels). NOT the theoretical max K.
                base += q * inc * (L * (L - 1) / 2.0)
            return base

        e_chain = (1.0 - p) * _chain_dmg(1 + G) + p * _chain_dmg(2 + G)
        # Attack-speed application: the roll happens up front. A swing that becomes a multistrike chain (length ≥ 2)
        # runs the WHOLE chain at the multistrike rate sps×s — the first hit included (it is "during multistrike" for
        # attack speed, though it still gets 0 increment stacks). A swing that does NOT multistrike — only possible
        # when chance < 100% (G == 0 and the leftover roll fails → a lone length-1 attack) — runs at BASE speed with
        # NO +20%. For chance ≥ 100% every swing is a chain, so this reduces to s × E[f] / (1 + chance).
        def _chain_time(L: int) -> float:                        # chain duration × sps (normalized)
            return 1.0 if L <= 1 else L / s
        denom = (1.0 - p) * _chain_time(1 + G) + p * _chain_time(2 + G)
        multistrike_mult = e_chain / denom if denom > 0.0 else e_chain
        multistrike_chance = c
        multistrike_avg_count = 1.0 + c
        multistrike_increment = inc
        multistrike_max_count = K
        multistrike_repeat_aps = sps * s
        multistrike_chain = ([{"count": 1 + G, "prob": 1.0}] if p <= 1e-9
                             else [{"count": 1 + G, "prob": 1.0 - p}, {"count": 2 + G, "prob": p}])

    # ── Demolisher Charge (Groundshaker etc.) ────────────────────────────────────────────────────────────
    # The skill is driven by a cast cadence (Rhythm interval, or APS when manual), NOT by attack-speed repeats.
    # The PRIMARY fissure lands on every cast (cast_rate); the SECONDARY explosion only on a CHARGED cast
    # (charged_rate — a charge must be held, regained every `restoration` s). We rebuild the two forms' DPS from
    # those rates (replacing the per-form sps default) and layer the demolisher damage modifiers:
    #   • demolisher_consume_dmg_additional (Cripple +44-46%) — the consuming cast only → charged-cast SHARE.
    #   • Cripple −90% "while the fissure spreads" — a separate multiplicative additional factor on the PRIMARY
    #     (and, with Frequent Quake, the fissure ticks). The secondary EXPLOSION is EXEMPT (fires at max spread).
    #   • Frequent Quake — the explosion is replaced by fq_ticks primary-fissure hits (1 + 4×0.4s).
    #   • Collapse — amps the fissure ticks by floor(1.6/R)·0.5·roll (Frequent-Quake persistence + rhythm only).
    #   • at_center_dmg_additional (Epicenter) is UNTAGGED → already folded into every hit's avg (full uptime).
    # The fissure ENUM zeroes the non-selected form (kept listed). Non-demolisher path is untouched.
    demolisher_mode = ""
    demolisher_restoration_time = 0.0
    demolisher_cast_rate = 0.0
    demolisher_charged_rate = 0.0
    demolisher_rhythm_interval = 0.0
    demolisher_charge_speed_inc = 0.0
    demolisher_base_restore = 0.0
    demolisher_mismatch = False
    demolisher_restore_to_sustain = 0.0
    demolisher_cdr_droppable = 0.0
    demolisher_under_breakpoint = False
    demolisher_over_breakpoint = False
    demolisher_collapse_pct = 0.0
    demolisher_frequent_quake = False
    demolisher_consume_add = 0.0
    demolisher_cripple = False
    demolisher_area_mode = "both"
    _demo_prim_vt = 0.0
    _demo_sec_vt = 0.0
    if demolisher:
        demolisher_mode = demolisher.get("mode", "manual")
        demolisher_restoration_time = demolisher.get("restoration_time", 0.0)
        demolisher_cast_rate = demolisher.get("cast_rate", 0.0)
        demolisher_charged_rate = demolisher.get("charged_rate", 0.0)
        demolisher_rhythm_interval = demolisher.get("rhythm_interval", 0.0)
        demolisher_charge_speed_inc = demolisher.get("charge_speed_inc", 0.0)
        demolisher_base_restore = demolisher.get("base_restore", 0.0)
        demolisher_mismatch = bool(demolisher.get("mismatch", False))
        demolisher_restore_to_sustain = demolisher.get("restore_to_sustain", 0.0)
        demolisher_cdr_droppable = demolisher.get("cdr_droppable", 0.0)
        demolisher_under_breakpoint = bool(demolisher.get("under_breakpoint", False))
        demolisher_over_breakpoint = bool(demolisher.get("over_breakpoint", False))
        demolisher_frequent_quake = bool(demolisher.get("frequent_quake", False))
        demolisher_area_mode = demolisher.get("area_mode", "both")
        demolisher_cripple = bool(demolisher.get("cripple_spread_penalty", False))
        fq_ticks = int(demolisher.get("fq_ticks", 5))
        cripple_factor = 0.10 if demolisher_cripple else 1.0
        demolisher_consume_add = source.total("demolisher_consume_dmg_additional")

        # Collapse: a step function of overlapping still-alive fissures. Needs Frequent-Quake persistence
        # (fissure lifetime ~1.6s) AND auto/rhythm casting (manual/spaced = no overlap). Amps individual
        # fissure ticks by floor(1.6/R)·0.5·roll (Tyra-verified across the rhythm table). At the exact floor
        # boundaries R=0.8 (=1.6/2) and R=0.4 (=1.6/4) the game time-averages between the two floors, so we use
        # the midpoint there (approximate — flagged). collapse_roll is a fraction (e.g. 0.62 for a +62% roll).
        collapse_roll = demolisher.get("collapse_roll", 0.0)
        R = demolisher_rhythm_interval
        if collapse_roll > 0 and demolisher_frequent_quake and demolisher_mode == "rhythm" and R > 0:
            n = 1.6 / R
            nearest = round(n)
            if nearest >= 1 and abs(n - nearest) < 1e-6:
                eff_floor = nearest - 0.5            # on a floor boundary → time-averaged midpoint
            else:
                eff_floor = math.floor(n)
            demolisher_collapse_pct = eff_floor * 0.5 * collapse_roll

        cast_rate = demolisher_cast_rate
        charged_rate = demolisher_charged_rate
        charged_frac = (charged_rate / cast_rate) if cast_rate > 0 else 0.0
        allow_primary = demolisher_area_mode != "secondary"
        allow_secondary = demolisher_area_mode != "primary"

        primary = next((f for f in hit_forms if f.name == "Primary Fissure"), None)
        secondary = next((f for f in hit_forms if f.name == "Secondary Explosion"), None)

        def _per_fire(form: HitFormResult) -> tuple[float, float]:
            # Per-cast damage of one form (pre-mit, vs-target), stripped of its sps-based rate.
            if form is None or form.fires_per_sec <= 0:
                return 0.0, 0.0
            return (form.dps_contribution / form.fires_per_sec,
                    form.dps_vs_target / form.fires_per_sec)

        prim_pm, prim_vt = _per_fire(primary)
        sec_pm, sec_vt = _per_fire(secondary)

        # Primary fissure — every cast. Cripple −90% on the whole term; consume on the charged share only.
        prim_consume = 1.0 + charged_frac * demolisher_consume_add
        p_pm = cast_rate * prim_pm * cripple_factor * prim_consume if allow_primary else 0.0
        p_vt = cast_rate * prim_vt * cripple_factor * prim_consume if allow_primary else 0.0

        # Secondary — charged casts only. Frequent Quake turns the single explosion into fq_ticks primary-fissure
        # hits that DO eat Cripple −90% + Collapse; the plain explosion is EXEMPT from Cripple and gets no Collapse.
        if demolisher_frequent_quake:
            s_pm = (charged_rate * fq_ticks * prim_pm * cripple_factor
                    * (1.0 + demolisher_consume_add) * (1.0 + demolisher_collapse_pct)) if allow_secondary else 0.0
            s_vt = (charged_rate * fq_ticks * prim_vt * cripple_factor
                    * (1.0 + demolisher_consume_add) * (1.0 + demolisher_collapse_pct)) if allow_secondary else 0.0
            sec_fires = charged_rate * fq_ticks
        else:
            s_pm = charged_rate * sec_pm * (1.0 + demolisher_consume_add) if allow_secondary else 0.0
            s_vt = charged_rate * sec_vt * (1.0 + demolisher_consume_add) if allow_secondary else 0.0
            sec_fires = charged_rate

        if primary is not None:
            primary.dps_contribution = p_pm
            primary.dps_vs_target = p_vt
            primary.fires_per_sec = cast_rate if allow_primary else 0.0
        if secondary is not None:
            if demolisher_frequent_quake and primary is not None:
                # Frequent Quake REPLACES the secondary explosion with fissure ticks (each = a primary-fissure
                # hit). Rebuild the form from the primary's per-hit values so the Skill Hit Damage table shows a
                # single fissure tick (not the stale 1135% explosion), relabeled, with the FQ tick DPS + rate.
                idx = hit_forms.index(secondary)
                hit_forms[idx] = replace(
                    primary,
                    name="Fissure Ticks (Frequent Quake)",
                    dps_contribution=s_pm,
                    dps_vs_target=s_vt,
                    fires_per_sec=sec_fires if allow_secondary else 0.0,
                )
            else:
                secondary.dps_contribution = s_pm
                secondary.dps_vs_target = s_vt
                secondary.fires_per_sec = sec_fires if allow_secondary else 0.0
        _demo_prim_vt = p_vt
        _demo_sec_vt = s_vt

    _delivery = cast_multiplier * tangle_mult * spell_burst_mult * multistrike_mult
    total_dps = sum(f.dps_contribution for f in hit_forms) * _delivery
    total_dps_vs_target = sum(f.dps_vs_target for f in hit_forms) * _delivery
    _base_dps_pre_true, _base_vt_pre_true = total_dps, total_dps_vs_target   # hit DPS before true-damage stages

    # ── Purpose-built breakdown rows (engine-owned reconciliation; see DamageRow) ─────────────────────────
    # Vuln (Numbed/Frostbite/Infiltration/curses/Paralysis) is already folded into damage_by_type at hit time
    # (the per-type loop above applies `vuln` before storing it) — mitigation_fn supplies only the REMAINING
    # target armour/resist factor, so the two never double-apply.
    damage_rows: list[DamageRow] = _build_hit_damage_rows(
        hit_forms, delivery=_delivery,
        mitigation_fn=lambda dt: _target_mitigation(source, dt),
        crit_factor=crit_factor, double_dmg_factor=double_dmg_factor,
    )

    # ── Mercury Baptism (Rosa Unsullied Blade) ────────────────────────────────────────────────────────────
    # Records a fraction (0.12-0.44) of non-channeled attack ELEMENTAL hit damage DEALT and re-deals it as TRUE
    # damage every 0.5s; in sustained DPS the record/dump window cancels, so it's `fraction × (elemental DPS dealt)`
    # added unmitigated on top (no _target_mitigation / enemy_vuln). Presence-gated → non-Rosa builds unchanged.
    mercury_baptism_fraction = 0.0
    mercury_baptism_dps = 0.0
    if (is_attack and not skill.channeled
            and "mercury_baptism_fraction" in _present and source.total("mercury_baptism_fraction") > 0.0):
        mbf = source.total("mercury_baptism_fraction")

        def _elem_share(form: HitFormResult) -> float:
            tot = sum(form.damage_by_type.values())
            return (sum(form.damage_by_type.get(t, 0.0) for t in _ELEMENTAL_DMG_TYPES) / tot) if tot > 0.0 else 0.0

        elem_premit = sum(f.dps_contribution * _elem_share(f) for f in hit_forms) * _delivery
        elem_vt = sum(f.dps_vs_target * _elem_share(f) for f in hit_forms) * _delivery
        mercury_baptism_fraction = mbf
        mercury_baptism_dps = mbf * elem_vt                  # true damage (unmitigated), vs-target
        total_dps += mbf * elem_premit
        total_dps_vs_target += mbf * elem_vt
        # kind="true": already-final true damage, no HitFormResult / per-type split of its own (sourced from
        # the existing, already-correct mercury_baptism_dps — not recomputed here).
        damage_rows.append(DamageRow(
            kind="true", name="Mercury Baptism (True Damage)",
            dps_final=mercury_baptism_dps, dps_vs_target_final=mercury_baptism_dps, pct_of_total=0.0,
        ))

    # ── Spell Ripple (Ethereal Prism) ───────────────────────────────────────────────────────────────────────
    # Spell hits proc a Pulse dealing TRUE damage = 150% of Hit Damage at 50% chance → fraction 0.75 of the spell's
    # hit DPS, added unmitigated (no mitigation/enemy-vuln). Computed from the pre-true-damage hit DPS. Presence-
    # gated → non-Spell-Ripple builds unchanged.
    spell_ripple_fraction = 0.0
    spell_ripple_dps = 0.0
    if (is_spell and "spell_ripple_fraction" in _present and source.total("spell_ripple_fraction") > 0.0):
        srf = source.total("spell_ripple_fraction")
        spell_ripple_fraction = srf
        spell_ripple_dps = srf * _base_vt_pre_true            # true damage (unmitigated), vs-target
        total_dps += srf * _base_dps_pre_true
        total_dps_vs_target += srf * _base_vt_pre_true
        # kind="true": sourced from the existing, already-correct spell_ripple_dps — not recomputed here.
        damage_rows.append(DamageRow(
            kind="true", name="Spell Ripple (True Damage)",
            dps_final=spell_ripple_dps, dps_vs_target_final=spell_ripple_dps, pct_of_total=0.0,
        ))

    # target_mitigation_by_type × enemy_vuln_by_type == enemy_mult_by_type — derived from the SAME two calls
    # enemy_mult_by_type is built from below, so the identity is exact (not just float-close).
    target_mitigation_by_type = {
        dt: _target_mitigation(source, dt)
        for dt in DAMAGE_TYPES
        if any(f.hit_max_by_type.get(dt, 0.0) > 0.0 for f in hit_forms)
    }
    enemy_vuln_by_type = {
        dt: _enemy_vuln_mult(source, dt, is_spell)
        for dt in target_mitigation_by_type
    }
    _finalize_damage_row_pcts(damage_rows, total_dps_vs_target)

    return OffenseResult(
        skill_name=skill.name,
        supported=True,
        effective_level=effective_level,
        hit_forms=hit_forms,
        crit_chance=crit_chance,
        crit_chance_uncapped=crit_chance_uncapped,
        crit_luck_effect=crit_luck_effect,
        crit_multiplier=crit_mult,
        double_dmg_chance=q2, triple_dmg_chance=q3, quad_dmg_chance=q4, double_dmg_factor=double_dmg_factor,
        steep_strike_chance=steep_chance,
        skills_per_second=sps,
        base_cast_time=base_cast_time,
        total_dps=total_dps,
        total_dps_vs_target=total_dps_vs_target,
        weapon_attack_speed=source.total("weapon_attack_speed"),
        weapon_aps_gear=source.total("attack_speed_gear"),
        weapon_aps_mh=source.total("attack_speed_mh"),
        weapon_crit_rating_flat=source.total("weapon_crit_rating_flat"),
        weapon_csr_gear=source.total("attack_crit_rating_gear"),
        weapon_csr_mh=source.total("attack_crit_rating_mh"),
        base_csr=base_csr,
        flat_dmg_min={dtype: mn for dtype, (mn, _) in flat_dmg.items()},
        flat_dmg_max={dtype: mx for dtype, (_, mx) in flat_dmg.items()},
        base_dmg_min={dtype: mn for dtype, (mn, _) in skill_base_dmg.items()},
        base_dmg_max={dtype: mx for dtype, (_, mx) in skill_base_dmg.items()},
        type_inc=type_inc,
        type_add=type_add,
        above_max_mult=above_mult,
        generic_inc=generic_inc,
        generic_add=generic_add,
        main_stat_damage_bonus=main_stat_bonus,
        main_stats=list(skill.main_stat),
        skill_tags=(skill.tags + [t for t in (add_mod_tags or set())
                                  if t.lower() not in {x.lower() for x in skill.tags}]),
        skill_area_inc=(source.total("skill_area_inc") + spell_burst_area_display) if "area" in skill_tags_lower else 0.0,
        cast_multiplier=cast_multiplier,
        shotgun_hits=shotgun_hits,
        # Only jump skills consume extra_jumps_flat (reading source.total marks it consumed) — guard on jumps_base
        # so a non-jump skill doesn't falsely consume a build's +Jumps source.
        jumps=skill.jumps_base + (int(source.total("extra_jumps_flat")) if skill.jumps_base else 0),
        jumps_base=skill.jumps_base,
        mana_cost=skill.mana_cost,
        tangle_count=tangle_count,
        tangle_enhancement=tangle_enhancement,
        tangle_mult=tangle_mult,
        tangle_placeable=tangle_placeable,
        tangle_inactivated=tangle_inactivated,
        tangle_duration=tangle_duration,
        tangle_attach_range=tangle_attach_range,
        tangle_cast_ticks=tangle_cast_ticks,
        tangle_cast_to_next_increased=tangle_cast_to_next_increased,
        tangle_cast_to_next_additional=tangle_cast_to_next_additional,
        channel_attack_ticks=channel_attack_ticks,
        channel_attack_smooth_sps=channel_attack_smooth_sps,
        channel_attack_to_next_increased=channel_attack_to_next_increased,
        channel_attack_to_next_additional=channel_attack_to_next_additional,
        spell_burst_count=spell_burst_count,
        spell_burst_casts_per_burst=spell_burst_casts_per_burst,
        spell_burst_charge_ticks=spell_burst_charge_ticks,
        spell_burst_charge_time=spell_burst_charge_time,
        spell_burst_charge_factor=spell_burst_charge_factor,
        spell_burst_charge_inc=spell_burst_charge_inc,
        spell_burst_charge_to_next_inc=spell_burst_charge_to_next_inc,
        spell_burst_charge_to_next_add=spell_burst_charge_to_next_add,
        spell_burst_cast_to_next_inc=spell_burst_cast_to_next_inc,
        spell_burst_cast_to_next_add=spell_burst_cast_to_next_add,
        spell_burst_play_safe=spell_burst_play_safe,
        spell_burst_next_breakpoint_ticks=spell_burst_next_breakpoint_ticks,
        spell_burst_rate=spell_burst_rate,
        spell_burst_mult=spell_burst_mult,
        spell_burst_auto=spell_burst_auto,
        spell_burst_auto_source=spell_burst_auto_source,
        spell_burst_dps=spell_burst_dps,
        spell_burst_dps_vs_target=spell_burst_dps_vs_target,
        non_spell_burst_dps=non_spell_burst_dps,
        non_spell_burst_dps_vs_target=non_spell_burst_dps_vs_target,
        channeled_max_stacks=ch_max_stacks,
        channeled_min_stacks=ch_min_stacks,
        channeled_stacks=float(ch_max_stacks),
        channeled_rounds_per_cycle=ch_rounds_per_cycle,
        channeled_burst_rate=ch_burst_rate,
        channeled_behavior=ch_behavior,
        channeled_attack_frequency=ch_attack_frequency,
        projectile_count=projectile_count,
        projectile_base_count=projectile_base_count,
        compulsory_breakdown=compulsory_breakdown,
        # Only for types this skill actually deals — those stats were already read (consumed) in the per-type
        # loop above, so re-reading is golden-neutral; reading types the skill doesn't deal would wrongly mark
        # their enemy-vuln stats "Consumed".
        enemy_mult_by_type={
            dt: target_mitigation_by_type[dt] * enemy_vuln_by_type[dt]
            for dt in target_mitigation_by_type
        },
        damage_rows=damage_rows,
        target_mitigation_by_type=target_mitigation_by_type,
        enemy_vuln_by_type=enemy_vuln_by_type,
        multistrike_chance=multistrike_chance,
        multistrike_avg_count=multistrike_avg_count,
        multistrike_increment=multistrike_increment,
        multistrike_max_count=multistrike_max_count,
        multistrike_mult=multistrike_mult,
        multistrike_repeat_aps=multistrike_repeat_aps,
        multistrike_chain=multistrike_chain,
        mercury_baptism_fraction=mercury_baptism_fraction,
        mercury_baptism_dps=mercury_baptism_dps,
        spell_ripple_fraction=spell_ripple_fraction,
        spell_ripple_dps=spell_ripple_dps,
        demolisher_mode=demolisher_mode,
        demolisher_restoration_time=demolisher_restoration_time,
        demolisher_base_restore=demolisher_base_restore,
        demolisher_charge_speed_inc=demolisher_charge_speed_inc,
        demolisher_cast_rate=demolisher_cast_rate,
        demolisher_charged_rate=demolisher_charged_rate,
        demolisher_rhythm_interval=demolisher_rhythm_interval,
        demolisher_mismatch=demolisher_mismatch,
        demolisher_restore_to_sustain=demolisher_restore_to_sustain,
        demolisher_cdr_droppable=demolisher_cdr_droppable,
        demolisher_under_breakpoint=demolisher_under_breakpoint,
        demolisher_over_breakpoint=demolisher_over_breakpoint,
        demolisher_collapse_pct=demolisher_collapse_pct,
        demolisher_frequent_quake=demolisher_frequent_quake,
        demolisher_area_mode=demolisher_area_mode,
        demolisher_primary_dps=_demo_prim_vt * _delivery,
        demolisher_secondary_dps=_demo_sec_vt * _delivery,
        trigger_interval=(1.0 / sps if (_wind is not None and sps > 0)
                          else (source.total("trigger_interval") if "trigger_interval" in _present else 0.0)),
        wind_rhythm_active=_wind is not None,
        wind_rhythm_rate=(_wind or {}).get("rate", 0.0),
        wind_rhythm_ticks=(_wind or {}).get("ticks", 0),
        wind_rhythm_cast_time=(_wind or {}).get("server_cast_time", 0.0),
        wind_rhythm_base_cooldown=(_wind or {}).get("base_cooldown", 0.0),
        wind_rhythm_bonus=(_wind or {}).get("wind_bonus", 0.0),
        wind_rhythm_cdr_to_next=(_wind or {}).get("cdr_to_next", 0.0),
        wind_rhythm_cast_to_next=(_wind or {}).get("cast_to_next", 0.0),
        wind_rhythm_wind_to_next=(_wind or {}).get("wind_to_next", 0.0),
        nyi=[
            "Support skill flat damage adds",
            "Elemental conversion",
            "Lucky crit",
            "Ailment DPS",
            *[f"{k} — {reason}" for k, reason in _DEFERRED_ADDITIONAL.items()],
        ],
    )
