from __future__ import annotations
from dataclasses import dataclass, field
from math import prod
from typing import Literal

from engine.models import BuildSource
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


DAMAGE_TYPES = ["physical", "fire", "cold", "lightning", "erosion"]

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


def _scale_effectiveness(base_pct: float, effective_level: int, max_level: int) -> float:
    """Apply above-max-level compounding multipliers.

    Levels max+1 to max+10: ×1.10 per level.
    Levels max+11+:         ×1.08 per level (compound on top of tier1).
    CONFIRM: verify these multipliers and tier breakpoints against actual game data.
    """
    extra = effective_level - max_level
    if extra <= 0:
        return base_pct
    tier1 = min(extra, 10)
    result = base_pct * (1.10 ** tier1)
    tier2 = max(0, extra - 10)
    if tier2 > 0:
        result *= 1.08 ** tier2
    return result


def calculate_offense(
    source: BuildSource,
    skill: ResolvedSkill,
    base_level: int,
) -> OffenseResult:
    if not skill.supported:
        return OffenseResult(skill_name=skill.name, supported=False)

    # 0. Crit — computed here in the offense layer, NOT in the fixed-point loop
    # Weapon CSR (from weapon gear piece) scaled by gear-specific and MH-specific % mods only.
    # Other flat CSR (talents, rings) is NOT scaled by those gear mods.
    weapon_csr = source.total("weapon_crit_rating_flat") * (
        1.0 + source.total("attack_crit_rating_gear") + source.total("attack_crit_rating_mh")
    )
    other_csr = source.total("attack_crit_rating_flat")
    raw_csr = (weapon_csr + other_csr) * (1.0 + source.total("attack_crit_rating_inc"))
    # 100 CSR = 1% crit chance; divide by 10000 to convert to 0–1 float
    crit_chance = min(raw_csr / 10000.0, 1.0)
    crit_mult = 1.5 + source.total("crit_damage")
    crit_factor = 1.0 + crit_chance * (crit_mult - 1.0)

    # 1. Effective level (+skill level sources not yet wired — NYI)
    effective_level = max(1, base_level)
    lookup_level = min(effective_level, skill.max_level)

    # 2. Flat damage pool per type: weapon base (× gear inc) + ring/gear/talent flat adds
    #    All sources pool here before any inc or additional multiplier is applied.
    skill_tags_lower = {t.lower() for t in skill.tags}
    is_attack = "attack" in skill_tags_lower
    is_spell = "spell" in skill_tags_lower

    flat_dmg: dict[str, tuple[float, float]] = {}
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

    # 3. Per-type inc and additional — precomputed outside the hit form loop.
    #    Inc: skill-tag-filtered incs PLUS the type-specific inc for that dtype.
    #    Additional: each applicable stat is an independent multiplicative pool.
    #    A dtype-specific stat (e.g. fire_dmg_inc) applies to that dtype even if the
    #    skill is not fire-tagged (e.g. a fire ring add on a physical skill still scales).
    type_inc: dict[str, float] = {}
    type_add: dict[str, float] = {}
    for dtype in flat_dmg:
        dtype_tag = frozenset({dtype})
        type_inc[dtype] = sum(
            source.total(key)
            for key, tags in _HIT_INC_STATS
            if not tags or tags & skill_tags_lower or tags & dtype_tag
        )
        type_add[dtype] = prod(
            1.0 + source.total(key)
            for key, tags in _HIT_ADDITIONAL_STATS
            if not tags or tags & skill_tags_lower or tags & dtype_tag
        )

    # 4. Steep strike chance: skill's intrinsic passive + stat sources, capped at 1.0
    steep_chance = min(skill.base_steep_strike_chance + source.total("steep_strike_chance"), 1.0)

    # 5. APS: base × (1 + inc) × each additional pool independently
    #    CONFIRM: verify no further multiplicative APS pools exist beyond these two
    aps = source.total("weapon_attack_speed") * (1.0 + source.total("attack_speed_inc"))
    for key, tags in _APS_ADDITIONAL_STATS:
        if not tags or tags & skill_tags_lower:
            aps *= (1.0 + source.total(key))

    # 6. Per hit form
    hit_forms: list[HitFormResult] = []
    for form in skill.hit_forms_by_level.get(lookup_level, []):
        eff = _scale_effectiveness(form.effectiveness_pct, effective_level, skill.max_level)

        if form.proc_stat_key == "steep_strike_chance":
            proc = steep_chance
        elif form.proc_stat_key == "_complement_steep_strike_chance":
            proc = 1.0 - steep_chance
        else:
            proc = 1.0

        damage_by_type: dict[str, float] = {}
        avg_pre = 0.0
        avg_pre_vs_target = 0.0
        for dtype, (mn, mx) in flat_dmg.items():
            inc = type_inc[dtype]
            add = type_add[dtype]
            type_min = mn * (eff / 100.0) * (1.0 + inc) * add
            type_max = mx * (eff / 100.0) * (1.0 + inc) * add
            avg = (type_min + type_max) / 2.0
            damage_by_type[dtype] = avg
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
        ))

    return OffenseResult(
        skill_name=skill.name,
        supported=True,
        effective_level=effective_level,
        hit_forms=hit_forms,
        crit_chance=crit_chance,
        crit_multiplier=crit_mult,
        steep_strike_chance=steep_chance,
        attacks_per_second=aps,
        total_dps=sum(f.dps_contribution for f in hit_forms),
        total_dps_vs_target=sum(f.dps_vs_target for f in hit_forms),
        nyi=[
            "Support skill flat damage adds",
            "Elemental conversion",
            "+Skill Level modifiers",
            "Lucky crit",
            "Ailment DPS",
            *[f"{k} — {reason}" for k, reason in _DEFERRED_ADDITIONAL.items()],
        ],
    )
