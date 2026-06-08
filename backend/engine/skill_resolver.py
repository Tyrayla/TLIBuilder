from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Literal
import re


@dataclass
class SkillHitForm:
    name: str
    effectiveness_pct: float       # at a specific level, before above-max scaling
    form_type: Literal["additive", "exclusive"]
    proc_stat_key: str | None = None
    # "steep_strike_chance"               → fires when steep procs
    # "_complement_steep_strike_chance"   → fires when steep does NOT proc (= 1 - steep_chance)
    # None                                → additive form; always fires


@dataclass
class IntrinsicAdditional:
    """A skill-intrinsic 'additional damage' pool that scales with a numeric condition (and
    optionally an effect % stat). E.g. Focused Slash: +0.4% additional damage per Fervor Rating,
    'affected by Fervor Effect'. Evaluated in compute.py (which has both the source and the
    condition state) and applied as one extra additional pool in calculate_offense.
        bonus_fraction = per * rating_value * (1 + effect_value)
    """
    per: float               # fraction of additional damage per 1 unit of rating (0.004 = 0.4%)
    rating_key: str          # numeric condition key whose value multiplies `per` (e.g. 'fervor_rating')
    effect_key: str | None = None  # optional % stat that scales the whole bonus (e.g. 'fervor_effect_inc')


@dataclass
class ResolvedSkill:
    skill_id: str
    name: str
    tags: list[str]
    max_level: int
    hit_forms_by_level: dict[int, list[SkillHitForm]]
    supported: bool = True  # False when skill_id is not in registry
    base_steep_strike_chance: float = 0.0  # intrinsic passive from skill text (e.g. "This skill +20% Steep Strike chance")
    intrinsic_additional: list[IntrinsicAdditional] = field(default_factory=list)


_REGISTRY: dict[str, Callable[[dict], ResolvedSkill]] = {}


def _register(skill_id: str):
    def decorator(fn: Callable) -> Callable:
        _REGISTRY[skill_id] = fn
        return fn
    return decorator


# ── Slash-Strike skills (Berserking Blade, Focused Slash) ──────────────────────
# Both have the same two mutually-exclusive forms per cast: Sweep Slash (fires when Steep does NOT
# proc) | Steep Strike (fires on the Steep proc). The form text differs slightly between skills —
# "Sweep Slash: 210% Weapon Attack Damage" vs "Sweep Slash: Deals 154% Weapon Attack Damage" —
# so the optional "Deals " is part of the regex.
_BB_FORM_RE = re.compile(
    r"([A-Z][A-Za-z ]+):\s*(?:Deals\s+)?(\d+(?:\.\d+)?)%\s*Weapon Attack Damage", re.IGNORECASE
)
_SKILL_STEEP_CHANCE_RE = re.compile(
    r"This skill \+(\d+(?:\.\d+)?)\s*%\s*Steep Strike chance", re.IGNORECASE
)


def _resolve_slash_skill(
    skill_data: dict, intrinsic_additional: list[IntrinsicAdditional] | None = None,
) -> ResolvedSkill:
    """Shared resolver for the Sweep Slash / Steep Strike skill family."""
    max_level = skill_data.get("max_level", 20)
    progression = {
        entry["level"]: entry["values"]
        for entry in skill_data.get("progression", [])
    }
    forms_by_level: dict[int, list[SkillHitForm]] = {}
    for lvl, values in progression.items():
        matches = _BB_FORM_RE.findall(values.get("Descript", ""))
        if len(matches) != 2:
            raise ValueError(
                f"{skill_data.get('item_id', '?')}: expected 2 hit forms at level {lvl}, "
                f"got {len(matches)}: {values.get('Descript', '')!r}"
            )
        # matches[0] = Sweep Slash (fires when steep does NOT proc)
        # matches[1] = Steep Strike (fires when steep procs)
        forms_by_level[lvl] = [
            SkillHitForm(matches[0][0].strip(), float(matches[0][1]), "exclusive", "_complement_steep_strike_chance"),
            SkillHitForm(matches[1][0].strip(), float(matches[1][1]), "exclusive", "steep_strike_chance"),
        ]
    m = _SKILL_STEEP_CHANCE_RE.search(skill_data.get("raw_text", ""))
    base_steep = float(m.group(1)) / 100.0 if m else 0.0

    return ResolvedSkill(
        skill_id=skill_data["item_id"],
        name=skill_data["name"],
        tags=skill_data.get("skill_tags", []),
        max_level=max_level,
        hit_forms_by_level=forms_by_level,
        supported=True,
        base_steep_strike_chance=base_steep,
        intrinsic_additional=intrinsic_additional or [],
    )


# Berserking Blade — Tags: Attack, Melee, Area, Physical, Slash-Strike, Persistent.
# (Its "50% chance for an extra buff stack on hit" mechanic is unmodeled, like other secondary procs.)
@_register("berserking_blade")
def _resolve_berserking_blade(skill_data: dict) -> ResolvedSkill:
    return _resolve_slash_skill(skill_data)


# Focused Slash — Tags: Attack, Melee, Area, Physical, Slash-Strike.
# Intrinsic Fervor bonus: "+0.4% additional damage for this skill per 1 Fervor Rating, affected by
# Fervor Effect" → one additional pool = 0.004 * fervor_rating * (1 + fervor_effect_inc).
@_register("focused_slash")
def _resolve_focused_slash(skill_data: dict) -> ResolvedSkill:
    return _resolve_slash_skill(
        skill_data,
        [IntrinsicAdditional(per=0.004, rating_key="fervor_rating", effect_key="fervor_effect_inc")],
    )


def resolve_skill(skill_data: dict) -> ResolvedSkill:
    """Return a ResolvedSkill; supported=False for any skill not in the registry.

    Never falls back to a partial or guessed calculation.
    """
    handler = _REGISTRY.get(skill_data.get("item_id", ""))
    if handler is None:
        return ResolvedSkill(
            skill_id=skill_data.get("item_id", ""),
            name=skill_data.get("name", ""),
            tags=[],
            max_level=0,
            hit_forms_by_level={},
            supported=False,
        )
    return handler(skill_data)
