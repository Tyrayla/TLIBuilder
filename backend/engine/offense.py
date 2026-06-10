from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Literal

from engine.models import BuildSource
from engine.affix_identity import affix_identity
from engine.skill_resolver import ResolvedSkill
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

# Additional stats that require special handling and are excluded from the generic pool.
# Each entry notes why it can't be treated as a simple always-on multiplier.
_DEFERRED_ADDITIONAL: dict[str, str] = {
    "barrage_dmg_per_wave_inc":      "Barrage mechanic — scales per wave fired, not a flat multiplier",
    "combo_finisher_additional":     "Combo finisher only — applies to finisher hits, not all hits; combo damage model NYI",
    "enemy_nearby_dmg_taken_additional": "Requires 'nearby enemy' condition boolean (not yet wired)",
    "multistrike_increasing_dmg_inc":"Multistrike mechanic — stacks per successive hit in a multistrike chain, not a flat multiplier",
    "post_mobility_dmg_additional":  "Requires 'mobility skill cast recently' condition boolean (not yet created)",
    "spell_burst_hit_dmg_additional":"Spell burst mechanic — unique per-burst hit scaling, deferred",
    "two_handed_base_dmg_additional":"May apply to base damage before inc/additional; stacking position unconfirmed — deferred",
}

# Hit damage additional multiplier stats — each is an independent multiplicative pool.
# Deferred stats (see _DEFERRED_ADDITIONAL) are excluded and listed in the NYI output.
_HIT_ADDITIONAL_STATS: list[tuple[str, frozenset]] = [
    (stat.value, frozenset(meta.tags))
    for stat, meta in STAT_META.items()
    if meta.pipeline_stage == "additional"
    and "hit" in meta.affects
    and stat.value not in _DEFERRED_ADDITIONAL
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


DAMAGE_TYPES = ["physical", "fire", "cold", "lightning", "erosion"]
_DTYPE_TAG_SET = frozenset(DAMAGE_TYPES)

# Innate base Critical Strike Rating for spells (500 CSR = 5% base crit at 0 gear). Owner-confirmed.
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

    for e in source.source_log:
        if e.stat not in _HIT_ADDITIONAL_KEYS:
            continue
        ident = (e.stat, affix_identity(e.text or ""))
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


def _additional_product(
    source: BuildSource,
    factors: list[tuple[float, frozenset, str]],
    predicate: Callable[[frozenset], bool],
) -> float:
    """Product of (1 + amount) over factors whose tags satisfy predicate. Records consumed_stats
    for the keys that actually apply (parity with the old per-key source.total reads)."""
    p = 1.0
    for amount, tags, stat_key in factors:
        if predicate(tags):
            if source._recording:
                source.consumed_stats.add(stat_key)
            p *= (1.0 + amount)
    return p

# Target dummy baseline mitigation (default calculation target)
# Physical: 50% armor reduction
# Non-physical: 60% of armor (50% × 0.60 = 30% reduction) PLUS 30% elemental/erosion resist (multiplicative)
_DUMMY_ARMOR_PCT = 0.50
_DUMMY_NONPHYS_ARMOR = _DUMMY_ARMOR_PCT * 0.60          # 0.30
_DUMMY_ELEMENTAL_RESIST = 0.30
_DUMMY_PHYS_MULT = 1.0 - _DUMMY_ARMOR_PCT               # 0.50
_DUMMY_NONPHYS_MULT = (1.0 - _DUMMY_NONPHYS_ARMOR) * (1.0 - _DUMMY_ELEMENTAL_RESIST)  # 0.70 × 0.70 = 0.49

_DUMMY_MITIGATION: dict[str, float] = {
    "physical": _DUMMY_PHYS_MULT,
    "fire": _DUMMY_NONPHYS_MULT,
    "cold": _DUMMY_NONPHYS_MULT,
    "lightning": _DUMMY_NONPHYS_MULT,
    "erosion": _DUMMY_NONPHYS_MULT,
}


def _enemy_vuln_mult(source: BuildSource, dtype: str) -> float:
    """Enemy-vulnerability stage: 'the enemy takes more <type> damage' effects, applied as a final
    per-type multiplier on OUTGOING damage — deliberately NOT in the attacker's additional pool, so
    distinct vulnerability sources combine on their own rule and type-scoping stays honest.

    Distinct sources combine MULTIPLICATIVELY (ship default; flip here if in-game testing disproves).
    Future sources (Proximity damage-taken, curses, exposure) plug in here. Today: Numbed only —
    +5% Lightning Damage taken per stack × (1 + numbed_effect_inc), baked into `numbed_lightning_taken`
    by the aggregator (fervor-style). Lightning-scoped. NOT the defensive dmg_taken family (that is
    incoming damage / the immunity tripwire); this is outgoing amplification.
    """
    if dtype == "lightning":
        return 1.0 + source.total("numbed_lightning_taken")
    return 1.0


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


@dataclass
class OffenseResult:
    skill_name: str
    supported: bool             # False = NYI; when False no numeric fields are meaningful
    effective_level: int = 0
    hit_forms: list[HitFormResult] = field(default_factory=list)
    crit_chance: float = 0.0
    crit_multiplier: float = 1.5
    steep_strike_chance: float = 0.0
    attacks_per_second: float = 0.0
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
    # Per-type damage breakdown for the stats screen breakdown table
    flat_dmg_min: dict[str, float] = field(default_factory=dict)  # flat before inc/add
    flat_dmg_max: dict[str, float] = field(default_factory=dict)
    type_inc: dict[str, float] = field(default_factory=dict)      # total increased decimal (e.g. 2.77 = 277% increased)
    type_add: dict[str, float] = field(default_factory=dict)      # total more product (e.g. 1.65 = x1.65)
    above_max_mult: float = 1.0  # additional multiplier from being above max skill level (1.0 = at or below max)
    generic_inc: float = 0.0    # total increased from non-dtype-specific sources (applies uniformly to all types)
    generic_add: float = 1.0    # total more product from non-dtype-specific sources (INCLUDES main-stat Damage Bonus)
    # Main-stat Damage Bonus — the portion of generic_add from the skill's main-stat attributes.
    # main_stat_damage_bonus is the fraction (0.255 = +25.5%); main_stats lists the attributes summed.
    main_stat_damage_bonus: float = 0.0
    main_stats: list[str] = field(default_factory=list)
    # Skill tags and tag-specific mechanics
    skill_tags: list[str] = field(default_factory=list)
    skill_area_inc: float = 0.0  # total increased area of effect (only when "area" in skill_tags)
    # Per-cast hit multiplier from same-target shotgun (Merge + Web). 1.0 = no shotgun. Applied to the
    # DPS totals (NOT the per-hit-form damage — mirrors the in-game tooltip vs Recount split).
    cast_multiplier: float = 1.0
    shotgun_hits: int = 1        # same-target hits per cast (1 = no shotgun)


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


def calculate_offense(
    source: BuildSource,
    skill: ResolvedSkill,
    base_level: int,
    is_main_skill: bool = True,
    extra_additional: float = 0.0,
    support_behavior: dict | None = None,
) -> OffenseResult:
    # extra_additional: a skill-intrinsic generic "additional damage" pool (fraction), evaluated
    # by the caller from the skill's intrinsic_additional + condition state (e.g. Focused Slash's
    # Fervor bonus). Applied as one extra multiplicative pool on every hit.
    if not skill.supported:
        return OffenseResult(skill_name=skill.name, supported=False)

    # 0. Crit — computed here in the offense layer, NOT in the fixed-point loop
    # Weapon CSR (from weapon gear piece) scaled by gear-specific and MH-specific % mods only.
    # Other flat CSR (talents, rings) is NOT scaled by those gear mods.
    weapon_csr = source.total("weapon_crit_rating_flat") * (
        1.0 + source.total("attack_crit_rating_gear") + source.total("attack_crit_rating_mh")
    )
    other_csr = source.total("attack_crit_rating_flat")
    # Innate base Critical Strike Rating for spells: every spell starts at 500 CSR (= 5% base crit)
    # with no weapon to provide it. Attacks derive their crit from weapon CSR and are left unchanged.
    base_csr = _BASE_SPELL_CRIT_RATING if skill.is_spell else 0.0
    # Increased Critical Strike Rating scales the whole CSR pool. crit_rating_inc is the GENERIC
    # "+X% Critical Strike Rating" (applies to both attacks and spells, e.g. Fervor Rating's
    # +2%/point); attack_crit_rating_inc is the attack-only increase. Both stack additively here.
    crit_rating_inc = source.total("crit_rating_inc") + source.total("attack_crit_rating_inc")
    raw_csr = (base_csr + weapon_csr + other_csr) * (1.0 + crit_rating_inc)
    # 100 CSR = 1% crit chance; divide by 10000 to convert to 0–1 float
    crit_chance = min(raw_csr / 10000.0, 1.0)
    crit_mult = 1.5 + source.total("crit_damage")
    crit_factor = 1.0 + crit_chance * (crit_mult - 1.0)

    # 1. Effective level — sum all applicable skill level bonuses from gear/talents/memories
    skill_tags_lower = {t.lower() for t in skill.tags}
    # Tags used for damage increased/additional filtering only — the skill's own tags plus any it
    # borrows (e.g. Moon Strike borrows 'spell' so Spell Damage mods apply to its Attack Damage).
    # NOT used for flat adds / is_spell, so a borrowing skill doesn't pull in off-type flat damage.
    mod_tags = skill_tags_lower | {t.lower() for t in skill.extra_damage_mod_tags}
    effective_level = skill_effective_level(source, skill.tags, base_level, is_main_skill)
    lookup_level = min(effective_level, skill.max_level)

    # 2. Flat damage pool per type: weapon base (× gear inc) + ring/gear/talent flat adds
    #    All sources pool here before any inc or additional multiplier is applied.
    is_attack = "attack" in skill_tags_lower
    is_spell = "spell" in skill_tags_lower

    flat_dmg: dict[str, tuple[float, float]] = {}
    if skill.is_spell:
        # Spell flat pool: the skill's intrinsic per-level base damage (UNSCALED by effectiveness) +
        # spell-tagged added flat (gear/supports), the latter scaled by the skill's added-damage
        # effectiveness. Weapon base does NOT apply to spells. Verified in-game — see
        # docs/CHAIN_LIGHTNING_IMPLEMENTATION_PLAN.md §1.
        # DEFERRED: min/max-damage reshaping (Phase 3, with Lucky); elemental-gear-flat→spell (flagged).
        eff_mult = skill.added_dmg_effectiveness
        base_for_level = skill.base_dmg_by_level.get(lookup_level, {})
        for dtype in DAMAGE_TYPES:
            b_min, b_max = base_for_level.get(dtype, (0.0, 0.0))
            add_min = source.total(f"{dtype}_spell_dmg_flat_min")
            add_max = source.total(f"{dtype}_spell_dmg_flat_max")
            total_min = b_min + add_min * eff_mult
            total_max = b_max + add_max * eff_mult
            if total_min > 0 or total_max > 0:
                flat_dmg[dtype] = (total_min, total_max)
    else:
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

    # 3. Per-type inc and additional — precomputed outside the hit form loop.
    #    Inc: skill-tag-filtered incs PLUS the type-specific inc for that dtype.
    #    Additional: each applicable stat is an independent multiplicative pool.
    #    A dtype-specific stat (e.g. fire_dmg_inc) applies to that dtype even if the
    #    skill is not fire-tagged (e.g. a fire ring add on a physical skill still scales).
    # Additional pools are per-AFFIX (Option A): build the factor list once, then apply the same
    # tag-scope predicates the increased pools use. Each distinct affix multiplies; same-affix
    # positives sum; each negative is its own factor. See docs/ADDITIONAL_DAMAGE_POOLING.md.
    add_factors = _build_additional_factors(source)

    # Generic intrinsic additional multiplier — applies uniformly to EVERY damage type (not per-affix):
    #   • extra_additional: skill-intrinsic pool (e.g. Fervor / Moon Strike's mana bonus), evaluated by caller.
    #   • main_stat_factor: 1 + (Σ the skill's main-stat attribute totals) × 0.5% — the "Damage Bonus" the
    #     attribute panel shows, driven by the skill's main_stat field (NOT tags). Source: TLI Help DB.
    # Folded into BOTH type_add and generic_add below so the per-type breakdown ratio cancels it cleanly
    # (it's a uniform multiplier, not a type-specific one) and "Total Additional" still reflects it.
    main_stat_bonus = sum(source.total(a) for a in skill.main_stat) * _MAIN_STAT_DAMAGE_PER_POINT
    main_stat_factor = 1.0 + main_stat_bonus
    intrinsic_add = (1.0 + extra_additional) * main_stat_factor

    type_inc: dict[str, float] = {}
    type_add: dict[str, float] = {}
    for dtype in flat_dmg:
        dtype_tag = frozenset({dtype})
        type_inc[dtype] = sum(
            source.total(key)
            for key, tags in _HIT_INC_STATS
            if not tags or tags & mod_tags or tags & dtype_tag
        )
        type_add[dtype] = _additional_product(
            source, add_factors,
            lambda tags, dt=dtype_tag: (not tags) or bool(tags & mod_tags) or bool(tags & dt),
        ) * intrinsic_add

    # Generic (non-dtype-specific) multipliers — applies uniformly to every damage type.
    # These are the "All" column values in the stats screen breakdown table.
    generic_inc = sum(
        source.total(key)
        for key, tags in _HIT_INC_STATS
        if not (tags & _DTYPE_TAG_SET) and (not tags or tags & mod_tags)
    )
    generic_add = _additional_product(
        source, add_factors,
        lambda tags: not (tags & _DTYPE_TAG_SET) and ((not tags) or bool(tags & mod_tags)),
    ) * intrinsic_add

    # 4. Steep strike chance: skill's intrinsic passive + stat sources, capped at 1.0
    steep_chance = min(skill.base_steep_strike_chance + source.total("steep_strike_chance"), 1.0)

    # 5. Hit rate (casts/attacks per second).
    if skill.is_spell:
        # Spell: casts/sec = (1 / cast time) × (1 + cast speed inc) × Π(1 + cast speed additional).
        # No weapon APS for spells. Mirrors the attack block below but cast-driven.
        cast_time = skill.base_cast_time or 1.0
        aps = (1.0 / cast_time) * (1.0 + source.total("cast_speed_inc"))
        for key, tags in _CAST_ADDITIONAL_STATS:
            if not tags or tags & skill_tags_lower:
                aps *= (1.0 + source.total(key))
    else:
        # APS: base × (1 + per-weapon gear multipliers) × (1 + inc) × additional pools
        #    attack_speed_gear: per-weapon gear roll (pre-averaged by buildGearPayload for dual-wield;
        #        for single weapon this is applied directly here)
        #    attack_speed_mh: mainhand-only bonus (discarded for offhand by buildGearPayload;
        #        for single weapon this is applied directly here)
        weapon_aps_mult = 1.0 + source.total("attack_speed_gear") + source.total("attack_speed_mh")
        aps = source.total("weapon_attack_speed") * weapon_aps_mult * (1.0 + source.total("attack_speed_inc"))
        # FUTURE (per-affix rework): this attack-speed additional pool still pools by stat-key. Convert
        # to per-affix factors (like _build_additional_factors) when reworking APS additional.
        for key, tags in _APS_ADDITIONAL_STATS:
            if not tags or tags & skill_tags_lower:
                aps *= (1.0 + source.total(key))

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
    for form in skill.hit_forms_by_level.get(lookup_level, []):
        eff = form.effectiveness_pct

        if form.proc_stat_key == "steep_strike_chance":
            proc = steep_chance
        elif form.proc_stat_key == "_complement_steep_strike_chance":
            proc = 1.0 - steep_chance
        else:
            proc = 1.0

        damage_by_type: dict[str, float] = {}
        hit_min_by_type: dict[str, float] = {}
        hit_max_by_type: dict[str, float] = {}
        avg_pre = 0.0
        avg_pre_vs_target = 0.0
        for dtype, (mn, mx) in flat_dmg.items():
            inc = type_inc[dtype]
            # type_add already includes the generic intrinsic multiplier (extra_additional × main-stat).
            add = type_add[dtype]
            # Enemy-vulnerability stage (Numbed etc.) — final per-type multiplier on outgoing damage.
            # Crit is uniform and commutes, so applying it here (pre-crit) is order-equivalent.
            vuln = _enemy_vuln_mult(source, dtype)
            # aug_factor (Augmentation per-Jump multiplies) is a real damage increase → in the per-hit.
            type_min = mn * (eff / 100.0) * (1.0 + inc) * add * above_mult * vuln * aug_factor
            type_max = mx * (eff / 100.0) * (1.0 + inc) * add * above_mult * vuln * aug_factor
            avg = (type_min + type_max) / 2.0
            # Lucky: EV uplift from the flat spread (scale-invariant), applied to the average only.
            if lucky_damage and mx > mn:
                R = mx - mn
                avg *= (mn + (2.0 / 3.0) * R) / (mn + 0.5 * R)
            damage_by_type[dtype] = avg
            hit_min_by_type[dtype] = type_min
            hit_max_by_type[dtype] = type_max
            avg_pre += avg
            avg_pre_vs_target += avg * _DUMMY_MITIGATION.get(dtype, 1.0)

        avg_post = avg_pre * crit_factor
        avg_post_vs_target = avg_pre_vs_target * crit_factor
        hit_forms.append(HitFormResult(
            name=form.name,
            effectiveness_pct=eff,
            form_type=form.form_type,
            proc_chance=proc,
            damage_by_type=damage_by_type,
            avg_hit_pre_crit=avg_pre,
            avg_hit_with_crit=avg_post,
            dps_contribution=avg_post * aps * proc,
            dps_vs_target=avg_post_vs_target * aps * proc,
            hit_min_by_type=hit_min_by_type,
            hit_max_by_type=hit_max_by_type,
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

    return OffenseResult(
        skill_name=skill.name,
        supported=True,
        effective_level=effective_level,
        hit_forms=hit_forms,
        crit_chance=crit_chance,
        crit_multiplier=crit_mult,
        steep_strike_chance=steep_chance,
        attacks_per_second=aps,
        total_dps=sum(f.dps_contribution for f in hit_forms) * cast_multiplier,
        total_dps_vs_target=sum(f.dps_vs_target for f in hit_forms) * cast_multiplier,
        weapon_attack_speed=source.total("weapon_attack_speed"),
        weapon_aps_gear=source.total("attack_speed_gear"),
        weapon_aps_mh=source.total("attack_speed_mh"),
        weapon_crit_rating_flat=source.total("weapon_crit_rating_flat"),
        weapon_csr_gear=source.total("attack_crit_rating_gear"),
        weapon_csr_mh=source.total("attack_crit_rating_mh"),
        flat_dmg_min={dtype: mn for dtype, (mn, _) in flat_dmg.items()},
        flat_dmg_max={dtype: mx for dtype, (_, mx) in flat_dmg.items()},
        type_inc=type_inc,
        type_add=type_add,
        above_max_mult=above_mult,
        generic_inc=generic_inc,
        generic_add=generic_add,
        main_stat_damage_bonus=main_stat_bonus,
        main_stats=list(skill.main_stat),
        skill_tags=skill.tags,
        skill_area_inc=source.total("skill_area_inc") if "area" in skill_tags_lower else 0.0,
        cast_multiplier=cast_multiplier,
        shotgun_hits=shotgun_hits,
        nyi=[
            "Support skill flat damage adds",
            "Elemental conversion",
            "Lucky crit",
            "Ailment DPS",
            *[f"{k} — {reason}" for k, reason in _DEFERRED_ADDITIONAL.items()],
        ],
    )
