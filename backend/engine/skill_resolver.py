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
class ResolvedSkill:
    skill_id: str
    name: str
    tags: list[str]
    max_level: int
    hit_forms_by_level: dict[int, list[SkillHitForm]]
    supported: bool = True  # False when skill_id is not in registry
    base_steep_strike_chance: float = 0.0  # intrinsic passive from skill text (e.g. "This skill +20% Steep Strike chance")


_REGISTRY: dict[str, Callable[[dict], ResolvedSkill]] = {}


def _register(skill_id: str):
    def decorator(fn: Callable) -> Callable:
        _REGISTRY[skill_id] = fn
        return fn
    return decorator


# ── Berserking Blade ──────────────────────────────────────────────────────────
# Tags: Attack, Melee, Area, Physical, Slash-Strike, Persistent
# Two mutually exclusive forms per cast: Sweep Slash (normal) | Steep Strike (proc)
_BB_FORM_RE = re.compile(
    r"([A-Z][A-Za-z ]+):\s*(\d+(?:\.\d+)?)%\s*Weapon Attack Damage", re.IGNORECASE
)
_SKILL_STEEP_CHANCE_RE = re.compile(
    r"This skill \+(\d+(?:\.\d+)?)\s*%\s*Steep Strike chance", re.IGNORECASE
)


@_register("berserking_blade")
def _resolve_berserking_blade(skill_data: dict) -> ResolvedSkill:
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
                f"Berserking Blade: expected 2 hit forms at level {lvl}, "
                f"got {len(matches)}: {values.get('Descript', '')!r}"
            )
        # matches[0] = Sweep Slash (fires when steep does NOT proc)
        # matches[1] = Steep Strike (fires when steep procs)
        forms_by_level[lvl] = [
            SkillHitForm(
                name=matches[0][0].strip(),
                effectiveness_pct=float(matches[0][1]),
                form_type="exclusive",
                proc_stat_key="_complement_steep_strike_chance",
            ),
            SkillHitForm(
                name=matches[1][0].strip(),
                effectiveness_pct=float(matches[1][1]),
                form_type="exclusive",
                proc_stat_key="steep_strike_chance",
            ),
        ]
    raw_text = skill_data.get("raw_text", "")
    m = _SKILL_STEEP_CHANCE_RE.search(raw_text)
    base_steep = float(m.group(1)) / 100.0 if m else 0.0

    return ResolvedSkill(
        skill_id=skill_data["item_id"],
        name=skill_data["name"],
        tags=skill_data.get("skill_tags", []),
        max_level=max_level,
        hit_forms_by_level=forms_by_level,
        supported=True,
        base_steep_strike_chance=base_steep,
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
