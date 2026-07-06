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
from dataclasses import replace

from engine.models import BuildSource, SourceEntry
from engine.affix_identity import affix_identity
from engine.skill_resolver import _parse_cast_time
from engine.constants import DAMAGE_TYPES as _DAMAGE_TYPES, ELEMENTAL as _ELEMENTAL
from engine.offense import (
    OffenseResult, HitFormResult, _enemy_vuln_mult, _DTYPE_TAG_SET, _above_max_mult,
    TARGET_ARMOR_MITIGATION, TARGET_NONPHYS_ARMOR_FACTOR, TARGET_ELEMENTAL_RESIST, TARGET_EROSION_RESIST,
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


# ── Player→minion stat remap (a support/gear/effect applied TO a minion) ───────
# Built once from the Stat enum: for every `minion_<X>` stat whose bare `<X>` is also a real stat, map X → the
# minion form. So a support attached to a minion (or a gear bonus transferred to it) converts to the minion-scoped
# equivalent (damage, speed, crit, flats, CDR, duration, projectiles, ailments, …). `to_minion_stat` passes a key
# with no minion version through UNCHANGED (fine for a support — it just does nothing to the minion). For the
# weapon-bonus TRANSFER (Isomorphic Arms), use `to_minion_stat_strict`, which returns None for "no minion
# equivalent" so the caller can drop + flag it (never let a player stat leak through as if it applied).

def _all_minion_stat_values() -> frozenset:
    from models.stat import Stat
    return frozenset(s.value for s in Stat if s.value.startswith("minion_"))


_MINION_ALL_KEYS: frozenset = _all_minion_stat_values()


def _build_player_to_minion_remap() -> dict[str, str]:
    from models.stat import Stat
    all_keys = {s.value for s in Stat}
    remap: dict[str, str] = {}
    for k in all_keys:
        if k.startswith("minion_"):
            base = k[len("minion_"):]
            if base in all_keys:
                remap[base] = k
    return remap


PLAYER_TO_MINION_STAT: dict[str, str] = _build_player_to_minion_remap()
# Manual bridges where player and minion names DON'T align by a bare prefix: typed penetration (player `fire_pen`
# ↔ minion `minion_fire_pen_inc`) and the weapon's AFFIX attack-speed / crit-rating aggregates (which a minion
# consumes as its increased pools — the weapon's intrinsic BASE `weapon_attack_speed`/`weapon_crit_rating_flat`
# still have no twin and correctly don't transfer).
PLAYER_TO_MINION_STAT.update({
    "fire_pen": "minion_fire_pen_inc", "cold_pen": "minion_cold_pen_inc",
    "lightning_pen": "minion_lightning_pen_inc", "erosion_pen": "minion_erosion_pen_inc",
    "attack_speed_gear": "minion_attack_speed_inc", "attack_speed_mh": "minion_attack_speed_inc",
    "attack_crit_rating_gear": "minion_crit_rating_inc", "attack_crit_rating_mh": "minion_crit_rating_inc",
})
# Player added/scaled damage carries an infix the minion pools don't — TWO shapes: attack|spell come BEFORE
# "dmg" (a support's "lightning_attack_dmg_flat_min"), while "gear" comes AFTER (a weapon's
# "physical_dmg_gear_flat_min"). Both bridge to the minion's "minion_<type>_dmg_<suffix>".
_INFIX_DMG_RE = re.compile(r"^(physical|fire|cold|lightning|erosion)_(?:attack|spell)_dmg_(flat_min|flat_max|inc|additional)$")
_GEAR_DMG_RE = re.compile(r"^(physical|fire|cold|lightning|erosion)_dmg_gear_(flat_min|flat_max)$")


def _minion_equiv(stat_key: str) -> str | None:
    """The minion-scoped equivalent of a player stat key, or None if there is none."""
    direct = PLAYER_TO_MINION_STAT.get(stat_key)
    if direct is not None:
        return direct
    for rx in (_INFIX_DMG_RE, _GEAR_DMG_RE):
        m = rx.match(stat_key)
        if m:
            cand = f"minion_{m.group(1)}_dmg_{m.group(2)}"
            if cand in _MINION_ALL_KEYS:
                return cand
    return None


def to_minion_stat(stat_key: str) -> str:
    """Remap a player stat key to its minion equivalent; unchanged when there is no minion version."""
    return _minion_equiv(stat_key) or stat_key


def to_minion_stat_strict(stat_key: str) -> str | None:
    """Like to_minion_stat but returns None when there is NO minion equivalent — so a transfer (weapon bonuses)
    can DROP + flag the stat instead of leaking the player key through as if it applied to the minion."""
    return _minion_equiv(stat_key)


# Spirit-magus-specific damage/crit pools carry the `spirit_magi` tag (not `minion`), so `_minion_keyed` skips
# them. A magus module folds them into the generic minion pools so they're consumed — scoped to magi only.
_SPIRIT_MAGI_FOLD = {
    "spirit_magi_dmg_inc": "minion_dmg_inc",
    "spirit_magi_dmg_additional": "minion_dmg_additional",
    "spirit_magi_crit_rating_flat": "minion_crit_rating_flat",
}


def fold_spirit_magi_pools(source: BuildSource, growth: float = 0.0) -> None:
    """Fold `spirit_magi_*` damage/crit pools into the generic `minion_*` pools IN PLACE. Call on a source COPY a
    magus module owns (never the shared source), so Spirit-Magi-scoped mods (which the minion offense would
    otherwise drop on the `spirit_magi` tag) actually apply to the magus. Also folds the per-Growth pools (Talons
    of Abyss) scaled by this magus's `growth` — dmg per 20 Growth, Ultimate AS/CS per 40 Growth."""
    def _add(dst: str, amt: float, text: str) -> None:
        if amt:
            source.add_with_source(dst, amt, SourceEntry(
                stat=dst, amount=amt, source_type="minion", label="Spirit Magi", source_name="Spirit Magi", text=text))

    for src_key, dst_key in _SPIRIT_MAGI_FOLD.items():
        _add(dst_key, source.total(src_key), f"Spirit Magi {src_key.replace('spirit_magi_', '').replace('_', ' ')}")

    # Per-Growth folds (Talons of Abyss): per-unit stat × floor(growth / divisor).
    if growth > 0:
        _add("minion_dmg_additional", source.total("minion_dmg_additional_per_20_growth") * (growth // 20),
             "Talons of Abyss: additional damage per 20 Growth")
        _add("minion_ultimate_attack_speed_additional",
             source.total("minion_ultimate_attack_speed_additional_per_40_growth") * (growth // 40),
             "Talons of Abyss: Ultimate Attack Speed per 40 Growth")
        _add("minion_ultimate_cast_speed_additional",
             source.total("minion_ultimate_cast_speed_additional_per_40_growth") * (growth // 40),
             "Talons of Abyss: Ultimate Cast Speed per 40 Growth")


def _minion_target_mitigation(source: BuildSource, dtype: str) -> float:
    """Target armor/resist mitigation for a MINION hit — uses the MINION's penetration (`minion_*_pen`), NOT the
    player's (minion damage penetrates with its own pen). Enemy resistance-reduction (`all_resistance_reduction`,
    an enemy debuff) is shared. Zero minion pen reproduces the base dummy mitigation (physical 0.50, others 0.49)."""
    tc = getattr(source, "target_config", None) or {}
    armor = tc.get("armor", TARGET_ARMOR_MITIGATION)
    armor_pen = source.total("minion_armor_pen")
    if dtype == "physical":
        return 1.0 - (armor - armor_pen)
    eff_armor = armor * TARGET_NONPHYS_ARMOR_FACTOR - armor_pen
    all_res_red = source.total("all_resistance_reduction")           # enemy debuff — shared with the player
    if dtype == "erosion":
        base_res = tc.get("erosion_res", TARGET_EROSION_RESIST)
        eff_resist = base_res - source.total("minion_erosion_pen_inc") + all_res_red
    else:  # fire / cold / lightning — minion_elemental_pen stacks on the per-type minion pen
        base_res = tc.get(f"{dtype}_res", TARGET_ELEMENTAL_RESIST)
        eff_resist = (base_res - source.total(f"minion_{dtype}_pen_inc")
                      - source.total("minion_elemental_pen") + all_res_red)
    return (1.0 - eff_armor) * (1.0 - eff_resist)


def _dtype_tag(dtype: str) -> frozenset:
    return frozenset({dtype}) | ({"elemental"} if dtype in _ELEMENTAL_SET else frozenset())


def _has_dtype_tags(tags: frozenset) -> bool:
    return bool(tags & _DTYPE_TAG_SET)


def _applies(tags: frozenset, dtype_tag: frozenset) -> bool:
    dmg = tags & _DTYPE_TAG_SET
    return (not dmg) or bool(dmg & dtype_tag)


# A minion ability is an ATTACK or a SPELL — their damage pools MUST NOT mix. A stat tagged `spell`/`attack`
# applies ONLY to an ability of that category (untagged stats apply to both).
_SKILL_TYPE_TAGS = frozenset({"attack", "spell"})


def _skill_type_ok(tags: frozenset, is_spell: bool) -> bool:
    st = tags & _SKILL_TYPE_TAGS
    if not st:
        return True
    return ("spell" in st) if is_spell else ("attack" in st)


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


# ── Spirit Magus Growth (Help DB / glossary id 759) ───────────────────────────
# Magi start at Stage 1 (100 Growth) and grow a stage per +100 Growth up to Stage 5 (500). Growth itself can
# rise to 1000. Stage grants: 2 → +30% Enhanced-Skill chance, 3 → stronger Enhanced, 4 → stronger Empower,
# 5 → +50% additional damage (+area/move). Per 8 Growth → +1% Physique. Sourced from spirit_magi_initial_growth
# + talent/gear/Iris growth mods.

def spirit_magi_growth(source: BuildSource) -> float:
    """A Spirit Magus's Growth: base 100 (Stage 1) + initial-growth mods, clamped to [100, 1000]."""
    return max(100.0, min(1000.0, 100.0 + source.total("spirit_magi_initial_growth_flat")))


def growth_stage(growth: float) -> int:
    """Stage 1-5 from Growth (100/200/300/400/500 thresholds; caps at 5 even as Growth rises to 1000)."""
    return max(1, min(5, int(growth // 100)))


def spirit_magi_physique_inc(source: BuildSource, growth: float) -> float:
    """Total Spirit Magi Physique %: Growth grants +1% per 8 Growth (glossary 759), plus any gear/talent
    `minion_physique_inc` pool (e.g. Big Tough Guy's +10%). Display/attribute only — does NOT feed hit DPS."""
    return growth / 800.0 + source.total("minion_physique_inc")   # growth/8 % → growth/800 as a fraction


def spirit_magi_skill_area_inc(stage: int) -> float:
    """Total additional Skill Area from Growth: +10% additional per STAGE (in-game tooltip — the glossary's
    "per 8 Growth" is a mis-scrape; Physique is the per-8-Growth stat). Stage N → +N×10%. Display only —
    Skill Area doesn't change single-target hit DPS."""
    return stage * 0.10


def _minion_additional(source: BuildSource, dtype_tag: frozenset, generic_only: bool, is_spell: bool) -> float:
    """Per-affix additional product for minion damage. `generic_only`=True → only stats with NO damage-type tag
    (the 'all types' factor); False → the full product applicable to `dtype_tag` (generic + type-specific). A
    `spell`/`attack`-tagged stat is included only when it matches the ability's category (`is_spell`)."""
    pos: dict[tuple[str, str], float] = defaultdict(float)
    neg: dict[tuple[str, str], list[float]] = defaultdict(list)
    tracked: dict[str, float] = defaultdict(float)
    for e in source.source_log:
        if e.stat not in _MINION_ADDITIONAL_KEYS:
            continue
        tags = _MINION_ADDITIONAL_TAGS[e.stat]
        if not _skill_type_ok(tags, is_spell):
            continue
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
        if not _skill_type_ok(tags, is_spell):
            continue
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
    rate_multiplier: float = 1.0,
    *,
    shotgun_hits: int = 1,
    shotgun_falloff: float = 0.0,
    extra_additional: float = 0.0,
    extra_additional_label: str = "",
    penetrates: bool = False,
) -> OffenseResult:
    """Compute ONE minion ability's DPS as a full `OffenseResult` (so the frontend reuses the player panels).
    A BUILDING BLOCK for bespoke minion modules — NOT called for unmodelled minions (compute stubs those NYI).
    Reads only minion-scoped pools off `source` (materialize for the owner's slot with 'minion' in scope first).
    `minion_count` is folded into the DPS totals via `cast_multiplier` (per-form figures stay per-minion).
    `rate_multiplier` scales the firing rate — a bespoke module uses it to split shared attacks between a
    Base skill and its Enhanced replacement (Base at 1−chance, Enhanced at chance) so summing the two = the
    true blended DPS.

    Ability-specific (Enhanced-only) knobs, applied to THIS call only (never the shared Base):
      `shotgun_hits` / `shotgun_falloff` — same-target Shotgun: N projectiles hit one enemy, each extra hit at
        (1 − falloff) → multiplier `1 + (hits−1)×(1−falloff)`, folded into DPS + surfaced on the hit form.
      `extra_additional` (+ `_label`) — a skill-intrinsic additional-damage fraction (e.g. Thunderlight Arrow's
        +5% per Projectile Quantity), folded into the additional pool + labelled in the Total-Additional breakdown.
      `penetrates` — the projectiles always Penetrate/track (multi-target / QoL; no single-target DPS effect,
        surfaced as a note so it's never silently dropped)."""
    tags_list = list(minion_skill.get("skill_tags") or [])
    tags_lower = {str(t).lower() for t in tags_list}
    is_spell = "spell" in tags_lower
    dtype = _primary_dtype(tags_lower)
    name = ability_label(minion_skill)

    # Minion Skill Level (e.g. Isometric-Arms/Mighty-Guard "+N Minion Skill Level") raises the ability's effective
    # level. Coefficient + shared base plateau at the data max (≤ 20); above level 20 the standard compounding
    # multiplier applies (×1.10 per level 21-30, ×1.08 per level 31+). spirit_magi_skill_level stacks for magi.
    _MINION_MAX_LEVEL = 20
    skill_level_bonus = int(round(source.total("minion_skill_level") + source.total("spirit_magi_skill_level")))
    effective_level = level + max(0, skill_level_bonus)
    above_mult = _above_max_mult(effective_level, _MINION_MAX_LEVEL)
    coeff = _coefficient_at(minion_skill.get("base_damage_coefficient"), effective_level)
    consts = (base_stats or {}).get("constants") or {}
    shared_base = _interp_level_table((base_stats or {}).get("base_damage_by_level") or {}, effective_level)
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
        if t is None or not _skill_type_ok(tags, is_spell):     # attack-flat never lands on a spell (and vice versa)
            continue
        amt = source.total(key) * (effectiveness if effectiveness > 0 else 1.0)
        if key.endswith("_min"):
            flat_min[t] += amt
        elif key.endswith("_max"):
            flat_max[t] += amt

    # Generic (all-types) increased/additional + per-type totals (generic + type-specific). Skill-type-tagged pools
    # (e.g. minion_spell_dmg_additional) apply ONLY to a matching ability — a Spell pool NEVER touches an Attack.
    # An Enhanced-only skill-intrinsic additional (Thunderlight Arrow's +5%/Projectile Quantity) folds in here too.
    # Focused Strike's at-center additional applies full-uptime to AREA abilities only (mirrors the player Epicenter).
    area_center_add = source.total("minion_at_center_dmg_additional") if "area" in tags_lower else 0.0
    extra_add_factor = (1.0 + max(0.0, extra_additional)) * (1.0 + max(0.0, area_center_add))
    generic_inc = sum(source.total(k) for k, tags in _MINION_INC_STATS
                      if not _has_dtype_tags(tags) and _skill_type_ok(tags, is_spell))
    generic_add = _minion_additional(source, frozenset(), generic_only=True, is_spell=is_spell) * extra_add_factor

    hit_min: dict[str, float] = {}
    hit_max: dict[str, float] = {}
    type_inc: dict[str, float] = {}
    type_add: dict[str, float] = {}
    enemy_mult: dict[str, float] = {}
    for t in {*flat_min, *flat_max}:
        if flat_min.get(t, 0.0) == 0.0 and flat_max.get(t, 0.0) == 0.0:
            continue
        t_tag = _dtype_tag(t)
        inc = sum(source.total(k) for k, tags in _MINION_INC_STATS
                  if _applies(tags, t_tag) and _skill_type_ok(tags, is_spell))
        add = _minion_additional(source, t_tag, generic_only=False, is_spell=is_spell) * extra_add_factor
        type_inc[t] = inc
        type_add[t] = add
        hit_min[t] = flat_min.get(t, 0.0) * (1.0 + inc) * add * above_mult   # above-max skill-level multiplier
        hit_max[t] = flat_max.get(t, 0.0) * (1.0 + inc) * add * above_mult
        enemy_mult[t] = _minion_target_mitigation(source, t) * _enemy_vuln_mult(source, t, is_spell)

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
    rate *= max(0.0, rate_multiplier)   # Base/Enhanced share split (a bespoke module passes 1−chance / chance)

    # Same-target Shotgun (Enhanced-only): N projectiles converge on one enemy; each extra hit deals (1−falloff).
    # Folded into DPS (like the player's cast-level shotgun), NOT the per-hit-form damage, and surfaced on the form.
    shots = max(1, shotgun_hits)
    shotgun_mult = 1.0 + (shots - 1) * (1.0 - shotgun_falloff)

    # Lucky damage (Queer Angle): a type with minion_lucky_<type> active rolls the range twice, keeping the higher
    # → EV = min + 2/3·range instead of the midpoint (mirror the player _luck_ratio; Lucky-only, no minion Unlucky).
    def _type_avg(t: str) -> float:
        mn, mx = hit_min.get(t, 0.0), hit_max.get(t, 0.0)
        mid = (mn + mx) / 2.0
        if mx > mn and source.total(f"minion_lucky_{t}") > 0.0:
            return mn + (2.0 / 3.0) * (mx - mn)
        return mid

    # Multistrike (minion ATTACK abilities) — mirror the player: a chance to auto-repeat the attack with
    # increasing damage; the +20% multistrike Attack Speed is INCREASED, so it dilutes against the minion's own
    # increased AS. multiplier = E[chain damage] ÷ (E[chain time] × rate). Spell abilities never multistrike.
    ms_mult = 1.0
    ms_chance = ms_inc = ms_avg_count = ms_repeat_aps = 0.0
    ms_max_count = 0
    ms_chain: list = []
    _mc = source.total("minion_multistrike_chance") if not is_spell else 0.0
    if _mc > 0.0:
        _inc = source.total("minion_multistrike_increasing_dmg_inc")
        _init = source.total("minion_max_multistrike_count_flat")     # Initial Multistrike Count (pre-stacks, adds no attacks)
        _as_inc = source.total("minion_attack_speed_inc")
        _s = (1.0 + _as_inc + 0.20) / (1.0 + _as_inc)
        _G = int(_mc); _p = _mc - _G
        def _chain_dmg(L: int) -> float:
            return L + _inc * (_init * L + L * (L - 1) / 2.0)
        def _chain_time(L: int) -> float:
            return 1.0 if L <= 1 else L / _s
        _e = (1.0 - _p) * _chain_dmg(1 + _G) + _p * _chain_dmg(2 + _G)
        _den = (1.0 - _p) * _chain_time(1 + _G) + _p * _chain_time(2 + _G)
        ms_mult = _e / _den if _den > 0.0 else _e
        ms_chance, ms_inc, ms_avg_count = _mc, _inc, 1.0 + _mc
        ms_max_count = 1 + _G + (1 if _p > 1e-9 else 0)
        ms_repeat_aps = rate * _s
        ms_chain = ([{"count": 1 + _G, "prob": 1.0}] if _p <= 1e-9
                    else [{"count": 1 + _G, "prob": 1.0 - _p}, {"count": 2 + _G, "prob": _p}])

    type_avg = {t: _type_avg(t) for t in hit_min}
    avg_pre = sum(type_avg.values())
    per_minion_dps = avg_pre * crit_factor * double_factor * rate * shotgun_mult * ms_mult
    per_minion_vs = sum(type_avg[t] * enemy_mult.get(t, 1.0)
                        for t in hit_min) * crit_factor * double_factor * rate * shotgun_mult * ms_mult
    count = max(1, minion_count)
    damage_by_type = dict(type_avg)

    form = HitFormResult(
        name=name, effectiveness_pct=coeff, form_type="additive", proc_chance=1.0,
        damage_by_type=damage_by_type, avg_hit_pre_crit=avg_pre, avg_hit_with_crit=avg_pre * crit_factor * double_factor,
        dps_contribution=per_minion_dps, dps_vs_target=per_minion_vs,
        hit_min_by_type=dict(hit_min), hit_max_by_type=dict(hit_max), fires_per_sec=rate,
        hits_per_fire=shots, shotgun_falloff=shotgun_falloff, shotgun_mult=shotgun_mult,
        base_min_by_type=dict(base_min), base_max_by_type=dict(base_max),
    )
    nyi = ["Conversion (owner phys→element line), Persistent/domain per-second damage, and ailment/DoT are NYI"]
    if penetrates:
        nyi.append(f"{name}: Projectiles always Penetrate and track the enemy — multi-target / clear utility, "
                   "no single-target DPS effect (surfaced, not dropped).")
    intrinsic_sources = ([{"label": extra_additional_label or "Projectile Quantity", "amount": extra_additional}]
                         if extra_additional > 0 else [])
    return OffenseResult(
        skill_name=name, supported=True, effective_level=effective_level, hit_forms=[form],
        above_max_mult=above_mult,
        crit_chance=crit_chance, crit_chance_uncapped=crit_chance_uncapped, crit_multiplier=crit_mult,
        double_dmg_chance=double_chance, double_dmg_factor=double_factor,
        skills_per_second=rate, base_cast_time=base_time,
        total_dps=per_minion_dps * count, total_dps_vs_target=per_minion_vs * count,
        cast_multiplier=float(count),                       # count folds into totals like a per-cast multiplier
        # NOTE: the shotgun is folded into the FORM's dps + surfaced via form.hits_per_fire — NOT into the
        # result-level shotgun_hits/cast_multiplier (which would double-count against the per-minion count).
        flat_dmg_min=dict(flat_min), flat_dmg_max=dict(flat_max),
        base_dmg_min=dict(base_min), base_dmg_max=dict(base_max),
        type_inc=type_inc, type_add=type_add, generic_inc=generic_inc, generic_add=generic_add,
        intrinsic_additional_sources=intrinsic_sources,
        enemy_mult_by_type=enemy_mult, base_csr=base_csr, skill_tags=tags_list,
        multistrike_chance=ms_chance, multistrike_avg_count=ms_avg_count, multistrike_increment=ms_inc,
        multistrike_max_count=ms_max_count, multistrike_mult=ms_mult, multistrike_repeat_aps=ms_repeat_aps,
        multistrike_chain=ms_chain,
        nyi=nyi,
    )


def combine_minion_forms(name: str, results: list[OffenseResult], count: int) -> OffenseResult:
    """Merge a minion's per-ability OffenseResults into ONE result, exactly like a player multi-form skill
    (e.g. Cold Beam + Icy Blade): each DAMAGE ability becomes a hit form of the single result, so the frontend's
    Form dropdown, per-form '% of Total', and 'All forms (combined)' all work off `hit_forms`.

    Non-damage abilities (Empower buffs, locked Ultimates → supported=False) become **NYI hit forms** — they show
    up in the form dropdown / breakdown as selectable, clearly-labelled forms with 0 DPS (excluded from % of
    Total), carrying their reason. This surfaces them (never silently dropped) without polluting the DPS.

    All of a minion's damage abilities read the SAME minion pools (crit/increased/additional/enemy — only their
    base coefficient and firing-rate share differ), so the shared pipeline fields (crit, generic/type inc/add,
    enemy multiplier, cast_multiplier=count) come from the primary (first) damage ability; the per-form rows
    carry each ability's own base damage, rate, and DPS share."""
    damage = [r for r in results if r.supported and r.hit_forms]
    forms = [f for r in damage for f in r.hit_forms]
    # Non-damage abilities → NYI forms (visible + selectable, 0 DPS, carry their reason).
    for r in results:
        if r.supported and r.hit_forms:
            continue
        forms.append(HitFormResult(
            name=r.skill_name, effectiveness_pct=0.0, form_type="additive", proc_chance=0.0,
            damage_by_type={}, avg_hit_pre_crit=0.0, avg_hit_with_crit=0.0,
            dps_contribution=0.0, dps_vs_target=0.0, fires_per_sec=0.0,
            nyi=list(r.nyi or []) or ["Not yet modelled."],
        ))

    # Shared damage-ability NYI notes (conversion / persistent / ailment) — kept on the combined result too.
    nyi_notes: list[str] = []
    for r in damage:
        for n in (r.nyi or []):
            if n not in nyi_notes:
                nyi_notes.append(n)

    if not damage:
        return OffenseResult(skill_name=name, supported=False,
                             effective_level=(results[0].effective_level if results else 0),
                             hit_forms=forms, nyi=nyi_notes or ["Minion not yet modelled — no damage form."])

    prim = damage[0]                                   # shared-pipeline representative (same pools on every form)
    return replace(
        prim,
        skill_name=name,
        hit_forms=forms,
        total_dps=sum(r.total_dps for r in damage),
        total_dps_vs_target=sum(r.total_dps_vs_target for r in damage),
        skills_per_second=sum(f.fires_per_sec for f in forms),   # NYI forms are 0/s → = the shared attack rate
        nyi=nyi_notes,
    )


def nyi_owner(name: str, abilities: list[dict], level: int) -> OffenseResult:
    """A single NYI card for an unmodelled minion OWNER — lists its abilities so nothing is silently dropped."""
    labels = ", ".join(ability_label(a) for a in abilities) or "(no abilities)"
    return OffenseResult(
        skill_name=name, supported=False, effective_level=level,
        nyi=["Minion not yet modelled — its skill rotation / form combination / conversion must be specified "
             f"explicitly before it contributes DPS. Abilities: {labels}"],
    )
