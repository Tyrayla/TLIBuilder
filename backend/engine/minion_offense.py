"""Minion DPS engine (Phase A) — computes minion ability damage into the shared `OffenseResult` shape so the
frontend renders it through the SAME player offense panels (per-type breakdown table, crit box, hit-rate box).

Two hard rules:
  1. Minions are scaled ONLY by minion-scoped modifiers (`minion_*` pools, filtered by `"minion" in tags`) plus
     a SHARED per-level Base Damage table — never by the player's generic damage/weapon/crit pools.
  2. A minion contributes damage ONLY when its owner has a registered bespoke module (see `MINION_MODULES`).
     The generic hit pipeline here is a BUILDING BLOCK those modules call — it is never auto-applied to an
     unmodelled minion, because each minion's rotation / form combination / conversion must be specified
     explicitly (Tyra's rule). Unmodelled owners resolve to `supported=False` (NYI, zero damage) but still list
     their abilities so they're surfaced, never silently dropped.

Base Damage / Life come from data/seasons/<S>/_minion_base_stats.json (hand-entered from in-game).
"""
from __future__ import annotations
import re
from collections import defaultdict

from engine.models import BuildSource
from engine.affix_identity import affix_identity
from engine.skill_resolver import _parse_cast_time
from engine.constants import DAMAGE_TYPES as _DAMAGE_TYPES, ELEMENTAL as _ELEMENTAL
from engine.offense import (
    OffenseResult, HitFormResult, _target_mitigation, _enemy_vuln_mult, _DTYPE_TAG_SET,
)
from models.stat_meta import STAT_META

# ── Minion-scoped stat lists (built once from STAT_META) — only "minion"-tagged stats keep player pools out ──

def _minion_keyed(stage: str) -> list[tuple[str, frozenset]]:
    return [
        (stat.value, frozenset(meta.tags))
        for stat, meta in STAT_META.items()
        if meta.pipeline_stage == stage and "minion" in (meta.tags or ())
    ]

_MINION_FLAT_STATS       = _minion_keyed("flat_damage")
_MINION_INC_STATS        = _minion_keyed("increased_reduced")
_MINION_ADDITIONAL_STATS = _minion_keyed("additional")
_MINION_CRIT_RATING_STATS = _minion_keyed("crit_rating")
_MINION_CRIT_DMG_STATS   = _minion_keyed("crit_damage")
_MINION_DOUBLE_STATS     = _minion_keyed("double_damage")
_MINION_ADDITIONAL_KEYS  = frozenset(k for k, _ in _MINION_ADDITIONAL_STATS)
_MINION_ADDITIONAL_TAGS  = dict(_MINION_ADDITIONAL_STATS)

_MINION_SPEED_INC = {"attack": "minion_attack_speed_inc", "cast": "minion_cast_speed_inc"}
_MINION_SPEED_ADD = {"attack": "minion_attack_speed_additional", "cast": "minion_cast_speed_additional"}

_ELEMENTAL_SET = frozenset(_ELEMENTAL)


def _dtype_tag(dtype: str) -> frozenset:
    return frozenset({dtype}) | ({"elemental"} if dtype in _ELEMENTAL_SET else frozenset())


def _has_dtype_tags(tags: frozenset) -> bool:
    return bool(tags & _DTYPE_TAG_SET)


def _applies(tags: frozenset, dtype_tag: frozenset) -> bool:
    dmg = tags & _DTYPE_TAG_SET
    return (not dmg) or bool(dmg & dtype_tag)


# ── Interpolation / coefficient helpers ───────────────────────────────────────

def _interp_level_table(table: dict, level: int) -> float:
    if not table:
        return 0.0
    pts = sorted((int(k), float(v)) for k, v in table.items())
    if level <= pts[0][0]:
        return pts[0][1]
    if level >= pts[-1][0]:
        return pts[-1][1]
    for (l0, v0), (l1, v1) in zip(pts, pts[1:]):
        if l0 <= level <= l1:
            return v0 if l1 == l0 else v0 + (v1 - v0) * (level - l0) / (l1 - l0)
    return pts[-1][1]


def _coefficient_at(coeff, level: int) -> float:
    if coeff is None:
        return 0.0
    if isinstance(coeff, dict):
        return _interp_level_table(coeff, level)
    return float(coeff)


def _parse_pct(val) -> float:
    if val is None:
        return 0.0
    m = re.search(r"([\d.]+)", str(val))
    return float(m.group(1)) / 100.0 if m else 0.0


_ROLE_TAGS = {"base skill": "Base", "enhanced skill": "Enhanced", "empower": "Empower", "ultimate": "Ultimate"}


def _role_of(tags_lower: set[str]) -> str:
    for tag, role in _ROLE_TAGS.items():
        if tag in tags_lower:
            return role
    return ""


def ability_label(minion_skill: dict) -> str:
    """The dropdown label for a minion ability: 'Name (Role)' — e.g. 'Blazing Dance (Base)'."""
    tags_lower = {str(t).lower() for t in (minion_skill.get("skill_tags") or [])}
    role = _role_of(tags_lower)
    return f"{minion_skill.get('name', '')}{f' ({role})' if role else ''}"


def _primary_dtype(tags_lower: set[str]) -> str:
    for t in _DAMAGE_TYPES:
        if t in tags_lower:
            return t
    return "physical"


def _minion_additional(source: BuildSource, dtype_tag: frozenset, generic_only: bool) -> float:
    """Per-affix additional product for minion damage. `generic_only`=True → only stats with NO damage-type tag
    (the 'all types' factor); False → the full product applicable to `dtype_tag` (generic + type-specific)."""
    pos: dict[tuple[str, str], float] = defaultdict(float)
    neg: dict[tuple[str, str], list[float]] = defaultdict(list)
    tracked: dict[str, float] = defaultdict(float)
    for e in source.source_log:
        if e.stat not in _MINION_ADDITIONAL_KEYS:
            continue
        tags = _MINION_ADDITIONAL_TAGS[e.stat]
        if generic_only and _has_dtype_tags(tags):
            continue
        if not generic_only and not _applies(tags, dtype_tag):
            continue
        ident = (e.stat, affix_identity(e.text or ""))
        if e.amount < 0:
            neg[ident].append(e.amount)
        else:
            pos[ident] += e.amount
        tracked[e.stat] += e.amount
    p = 1.0
    for amt in pos.values():
        p *= (1.0 + amt)
    for amts in neg.values():
        for a in amts:
            p *= (1.0 + a)
    for key, tags in _MINION_ADDITIONAL_STATS:
        if generic_only and _has_dtype_tags(tags):
            continue
        if not generic_only and not _applies(tags, dtype_tag):
            continue
        raw = sum(v for s, v in source._entries if s == key)
        remainder = raw - tracked.get(key, 0.0)
        if abs(remainder) > 1e-12:
            p *= (1.0 + remainder)
    return p


def _speed_add_product(source: BuildSource, key: str) -> float:
    entries = [e for e in source.source_log if e.stat == key]
    if not entries:
        return 1.0 + source.total(key)
    pos: dict[str, float] = defaultdict(float)
    for e in entries:
        pos[affix_identity(e.text or "")] += e.amount
    p = 1.0
    for amt in pos.values():
        p *= (1.0 + amt)
    return p


# ── Bespoke minion-module registry ────────────────────────────────────────────
# owner_id -> handler(source, owner, base_stats, level, count) -> list[OffenseResult]. EMPTY today: no minion is
# modelled, so EVERY minion resolves NYI. A module is added only when Tyra specifies that minion's mechanics.
MINION_MODULES: dict[str, object] = {}


def is_modeled(owner_id: str) -> bool:
    return owner_id in MINION_MODULES


def nyi_offense(minion_skill: dict, level: int) -> OffenseResult:
    """A minion ability with no bespoke model → surfaced but supported=False (renders the NYI card, 0 DPS)."""
    return OffenseResult(
        skill_name=ability_label(minion_skill),
        supported=False,
        effective_level=level,
        skill_tags=list(minion_skill.get("skill_tags") or []),
        nyi=["Minion not yet modelled — its skill rotation / form combination / conversion must be specified "
             "explicitly before it contributes DPS."],
    )


def calculate_minion_offense(
    source: BuildSource,
    minion_skill: dict,
    base_stats: dict | None,
    level: int,
    minion_count: int = 1,
) -> OffenseResult:
    """Compute ONE minion ability's DPS as a full `OffenseResult` (so the frontend reuses the player panels).
    A BUILDING BLOCK for bespoke minion modules — NOT called for unmodelled minions (compute stubs those NYI).
    Reads only minion-scoped pools off `source` (materialize for the owner's slot with 'minion' in scope first).
    `minion_count` is folded into the DPS totals via `cast_multiplier` (per-form figures stay per-minion)."""
    tags_list = list(minion_skill.get("skill_tags") or [])
    tags_lower = {str(t).lower() for t in tags_list}
    is_spell = "spell" in tags_lower
    dtype = _primary_dtype(tags_lower)
    name = ability_label(minion_skill)

    coeff = _coefficient_at(minion_skill.get("base_damage_coefficient"), level)
    consts = (base_stats or {}).get("constants") or {}
    shared_base = _interp_level_table((base_stats or {}).get("base_damage_by_level") or {}, level)
    if base_stats is None or shared_base <= 0:
        r = nyi_offense(minion_skill, level)
        r.nyi = ["Minion Base Damage table not filled (data/seasons/<S>/_minion_base_stats.json)"]
        return r
    if coeff <= 0:
        r = nyi_offense(minion_skill, level)
        r.nyi = [f"{name}: no '% of Base Damage' coefficient (pure buff/utility ability — no hit modelled)"]
        return r

    effectiveness = _parse_pct(minion_skill.get("effectiveness_of_added_damage"))

    # Base (single shared value on the primary type) + added flat per type.
    base_hit = shared_base * coeff / 100.0
    flat_min: dict[str, float] = defaultdict(float)
    flat_max: dict[str, float] = defaultdict(float)
    base_min: dict[str, float] = defaultdict(float)
    base_max: dict[str, float] = defaultdict(float)
    flat_min[dtype] += base_hit; flat_max[dtype] += base_hit
    base_min[dtype] += base_hit; base_max[dtype] += base_hit
    for key, tags in _MINION_FLAT_STATS:
        t = next(iter(tags & _DTYPE_TAG_SET), None)
        if t is None:
            continue
        amt = source.total(key) * (effectiveness if effectiveness > 0 else 1.0)
        if key.endswith("_min"):
            flat_min[t] += amt
        elif key.endswith("_max"):
            flat_max[t] += amt

    # Generic (all-types) increased/additional + per-type totals (generic + type-specific).
    generic_inc = sum(source.total(k) for k, tags in _MINION_INC_STATS if not _has_dtype_tags(tags))
    generic_add = _minion_additional(source, frozenset(), generic_only=True)

    hit_min: dict[str, float] = {}
    hit_max: dict[str, float] = {}
    type_inc: dict[str, float] = {}
    type_add: dict[str, float] = {}
    enemy_mult: dict[str, float] = {}
    for t in {*flat_min, *flat_max}:
        if flat_min.get(t, 0.0) == 0.0 and flat_max.get(t, 0.0) == 0.0:
            continue
        t_tag = _dtype_tag(t)
        inc = sum(source.total(k) for k, tags in _MINION_INC_STATS if _applies(tags, t_tag))
        add = _minion_additional(source, t_tag, generic_only=False)
        type_inc[t] = inc
        type_add[t] = add
        hit_min[t] = flat_min.get(t, 0.0) * (1.0 + inc) * add
        hit_max[t] = flat_max.get(t, 0.0) * (1.0 + inc) * add
        enemy_mult[t] = _target_mitigation(source, t) * _enemy_vuln_mult(source, t, is_spell)

    # Crit (fixed 500 CSR / 150% base from constants, scaled by minion crit pools).
    base_csr = float(consts.get("crit_rating_flat", 500.0))
    csr_inc = sum(source.total(k) for k, _ in _MINION_CRIT_RATING_STATS if k.endswith("_inc"))
    csr_flat = sum(source.total(k) for k, _ in _MINION_CRIT_RATING_STATS if k.endswith("_flat"))
    raw_csr = (base_csr + csr_flat) * (1.0 + csr_inc)
    crit_chance_uncapped = raw_csr / 10000.0
    crit_chance = min(crit_chance_uncapped, 1.0)
    crit_mult = float(consts.get("crit_damage", 150.0)) / 100.0 + sum(source.total(k) for k, _ in _MINION_CRIT_DMG_STATS)
    crit_factor = 1.0 + crit_chance * (crit_mult - 1.0)
    double_chance = min(sum(source.total(k) for k, _ in _MINION_DOUBLE_STATS), 1.0)
    double_factor = 1.0 + double_chance

    # Rate: cast/attack time + minion speed pools, cooldown-capped.
    base_time = _parse_cast_time(minion_skill.get("cast_speed", "")) or 0.0
    rate = 0.0
    if base_time > 0:
        which = "cast" if is_spell else "attack"
        rate = (1.0 / base_time) * (1.0 + source.total(_MINION_SPEED_INC[which])) * _speed_add_product(source, _MINION_SPEED_ADD[which])
    cooldown = _parse_cast_time(minion_skill.get("cooldown", "")) or 0.0
    if cooldown > 0:
        rate = min(rate, 1.0 / cooldown) if rate > 0 else 1.0 / cooldown

    avg_pre = sum((hit_min.get(t, 0.0) + hit_max.get(t, 0.0)) / 2.0 for t in hit_min)
    per_minion_dps = avg_pre * crit_factor * double_factor * rate
    per_minion_vs = sum(((hit_min.get(t, 0.0) + hit_max.get(t, 0.0)) / 2.0) * enemy_mult.get(t, 1.0)
                        for t in hit_min) * crit_factor * double_factor * rate
    count = max(1, minion_count)
    damage_by_type = {t: ((hit_min.get(t, 0.0) + hit_max.get(t, 0.0)) / 2.0) for t in hit_min}

    form = HitFormResult(
        name=name, effectiveness_pct=coeff, form_type="additive", proc_chance=1.0,
        damage_by_type=damage_by_type, avg_hit_pre_crit=avg_pre, avg_hit_with_crit=avg_pre * crit_factor * double_factor,
        dps_contribution=per_minion_dps, dps_vs_target=per_minion_vs,
        hit_min_by_type=dict(hit_min), hit_max_by_type=dict(hit_max), fires_per_sec=rate, hits_per_fire=1,
        base_min_by_type=dict(base_min), base_max_by_type=dict(base_max),
    )
    return OffenseResult(
        skill_name=name, supported=True, effective_level=level, hit_forms=[form],
        crit_chance=crit_chance, crit_chance_uncapped=crit_chance_uncapped, crit_multiplier=crit_mult,
        double_dmg_chance=double_chance, double_dmg_factor=double_factor,
        skills_per_second=rate, base_cast_time=base_time,
        total_dps=per_minion_dps * count, total_dps_vs_target=per_minion_vs * count,
        cast_multiplier=float(count),                       # count folds into totals like a per-cast multiplier
        flat_dmg_min=dict(flat_min), flat_dmg_max=dict(flat_max),
        base_dmg_min=dict(base_min), base_dmg_max=dict(base_max),
        type_inc=type_inc, type_add=type_add, generic_inc=generic_inc, generic_add=generic_add,
        enemy_mult_by_type=enemy_mult, base_csr=base_csr, skill_tags=tags_list,
        nyi=["Conversion (owner phys→element line), Persistent/domain per-second damage, multi-hit/shotgun forms, "
             "and ailment/DoT are NYI"],
    )
