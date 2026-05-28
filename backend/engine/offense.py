from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

from engine.models import BuildSource
from engine.skill_resolver import ResolvedSkill
from models.stat_meta import STAT_META

# Pre-built lookup: (stat_key_str, frozenset_of_lowercase_tags) for all hit-damage
# increased/reduced stats. Empty frozenset = universal (applies to every skill).
_HIT_INC_STATS: list[tuple[str, frozenset]] = [
    (stat.value, frozenset(meta.tags))
    for stat, meta in STAT_META.items()
    if meta.pipeline_stage == "increased_reduced"
    and "hit" in meta.affects
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


def _modifier_applies(modifier_tags: set[str], skill_tags: set[str]) -> bool:
    """A modifier applies if ANY of its tags intersects the skill's tag set.

    A modifier tagged [Physical, Spell] applies to a [Physical, Attack] skill
    because Physical is in the intersection.
    """
    return bool(modifier_tags & skill_tags)


def calculate_offense(
    source: BuildSource,
    skill: ResolvedSkill,
    base_level: int,
) -> OffenseResult:
    if not skill.supported:
        return OffenseResult(skill_name=skill.name, supported=False)

    # 0. Crit — computed here in the offense layer, NOT in the fixed-point loop
    raw_csr = (
        source.total("attack_crit_rating_gear") + source.total("attack_crit_rating_flat")
    ) * (1.0 + source.total("attack_crit_rating_inc"))
    # 100 CSR = 1% crit chance; divide by 10000 to convert to 0–1 float
    crit_chance = min(raw_csr / 10000.0, 1.0)
    crit_mult = 1.5 + source.total("crit_damage")
    crit_factor = 1.0 + crit_chance * (crit_mult - 1.0)

    # 1. Effective level (+skill level sources not yet wired — NYI)
    effective_level = max(1, base_level)
    lookup_level = min(effective_level, skill.max_level)

    # 2. Weapon base damage per type (weapon implicit + gear inc; flat pool before inc/additional)
    weapon_dmg: dict[str, tuple[float, float]] = {}
    for dtype in DAMAGE_TYPES:
        dmg_min = source.total(f"{dtype}_dmg_gear_flat_min")
        dmg_max = source.total(f"{dtype}_dmg_gear_flat_max")
        gear_inc = source.total(f"{dtype}_dmg_gear_inc")
        total_min = dmg_min * (1.0 + gear_inc)
        total_max = dmg_max * (1.0 + gear_inc)
        if total_min > 0 or total_max > 0:
            weapon_dmg[dtype] = (total_min, total_max)

    # 3. Inc damage — one additive pool, tag-filtered from stat_meta
    skill_tags_lower = {t.lower() for t in skill.tags}
    inc_total = sum(
        source.total(key)
        for key, tags in _HIT_INC_STATS
        if not tags or tags & skill_tags_lower
    )

    # 4. Additional multiplier pools — tag-filtered (NYI; placeholder)
    add_multiplier = 1.0  # TODO: wire additional pools

    # 5. Steep strike chance: skill's intrinsic passive + stat sources, capped at 1.0
    steep_chance = min(skill.base_steep_strike_chance + source.total("steep_strike_chance"), 1.0)

    # 6. APS — CONFIRM: verify no separate multiplicative "more attack speed" pool exists
    aps = source.total("weapon_attack_speed") * (1.0 + source.total("attack_speed_inc"))

    # 7. Per hit form
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
        for dtype, (mn, mx) in weapon_dmg.items():
            type_min = mn * (eff / 100.0) * (1.0 + inc_total) * add_multiplier
            type_max = mx * (eff / 100.0) * (1.0 + inc_total) * add_multiplier
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
            "Additional damage multiplier pools (NYI — not yet wired)",
            "Flat damage from supports",
            "Flat damage from talent/ring adds",
            "Elemental conversion",
            "+Skill Level modifiers",
            "Lucky crit",
            "Ailment DPS",
        ],
    )
