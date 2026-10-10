"""Ring of Blades' slot-local support effects.

Blade Formation's damage lines stay in the generic support resolver. Its behavioral flag is consumed by the
orbital rate path. Razor Edge emits its per-stack Projectile Speed as one slot-local additional source.
"""
from __future__ import annotations

import re

from engine.models import SourceEntry
from engine.support_resolver import _explicit_roll, _progression_for_tier, _tier_value

SKILL_ID = "ring_of_blades"
BLADE_FORMATION = "ring_of_blades_blade_formation_magnificent"
RAZOR_EDGE = "ring_of_blades_razor_edge_noble"
STRENGTH_IN_NUMBERS = "ring_of_blades_strength_in_numbers_noble"

_RANGE = r"\(?\s*([-?]?\d+(?:\.\d+)?)\s*[^0-9\s]\s*([-?]?\d+(?:\.\d+)?)\s*\)?"
_RAZOR_EDGE_RE = re.compile(
    _RANGE + r"\s*%\s*additional Projectile Speed for every channeled stack", re.I
)

LINE_SPECS = [
    {"support_ids": {BLADE_FORMATION},
     "phrase": re.compile(r"creates all Projectiles at once", re.I), "keys": [], "range_re": None},
    {"support_ids": {BLADE_FORMATION},
     "phrase": re.compile(r"Max Projectiles.*Projectile Quantity.*up to \+?7", re.I),
     "keys": [], "range_re": None},
    {"support_ids": {RAZOR_EDGE},
     "phrase": re.compile(r"additional Projectile Speed for every channeled stack", re.I),
     "keys": ["projectile_speed_additional"], "range_re": _RAZOR_EDGE_RE},
]


def _tier_line(data: dict, sup: dict) -> str:
    entry = _progression_for_tier(data.get("progression"), _tier_value(sup.get("level")))
    return str((entry.get("values") or {}).get("name", "")) if entry else ""


def apply_slot_effects(*, source, resolved, slot, attached_supports, skills_by_id, **_) -> dict:
    """Emit Razor Edge's rolled additional Projectile Speed into this Ring of Blades slot only."""
    for sup in attached_supports or []:
        if (sup.get("item_id") != RAZOR_EDGE or sup.get("slot", 1) != slot
                or not sup.get("enabled", True)):
            continue
        data = skills_by_id.get(RAZOR_EDGE) or {}
        line = _tier_line(data, sup)
        match = _RAZOR_EDGE_RE.search(line)
        if not match:
            continue
        per_stack = _explicit_roll(sup, line)
        if per_stack is None:
            per_stack = (float(match.group(1)) + float(match.group(2))) / 200.0
        base_max = int(getattr(resolved.channeled, "max_stacks", 0)) if resolved.channeled else 0
        stacks = max(1, base_max + int(source.total("max_channeled_stacks_flat")))
        amount = per_stack * stacks
        if amount:
            name = data.get("name") or "Razor Edge"
            source.add_slotted("projectile_speed_additional", amount, slot, None, SourceEntry(
                stat="projectile_speed_additional", amount=amount, source_type="support",
                label="Ring of Blades: Razor Edge", source_name=name,
                text=(f"+{per_stack * 100:.2f}% additional Projectile Speed per channeled stack "
                      f"x{stacks} |{RAZOR_EDGE}|projectile_speed"),
                points=1,
            ))
        break
    # Skill Area changes orbit radius, not hit damage, for this skill.
    return {"remove_mod_tags": {"area"}}
