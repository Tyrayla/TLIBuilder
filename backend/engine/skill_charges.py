"""Per-skill charges (Help DB: only skills with a cooldown can gain charges).

A skill with a cooldown has charges (default 1, restored over the cooldown); cooldown-less skills have none. Cooldown
isn't a structured field in the skill data — it lives in the description text — so we parse it. `skill_base_charges`
returns the base max charges (None = no cooldown = no charges, which is legitimate for most skills). Mods (+N Max
Charge, e.g. Mass Effect's +1) add on top only when a base exists. `is_charge_ambiguous` flags the genuine gaps —
text that says "cooldown"/"CD" but where no number could be parsed — for manual review (a clean cooldown-less skill
is NOT flagged).
"""
from __future__ import annotations
import re

# First "<number> s" after a cooldown/CD mention on the same clause. \bcd\b avoids matching "cold"/"cdr".
_COOLDOWN_RE = re.compile(r"(?:cooldown|\bcd\b)[^.\n]*?([\d.]+)\s*s\b", re.I)
# Leading number of a structured cooldown string ("10 s" -> 10).
_COOLDOWN_NUM_RE = re.compile(r"([\d.]+)")
_CHARGE_COUNT_RE = re.compile(r"(?:max(?:imum)?\s+)?charges?\s*:?\s*(\d+)", re.I)
_COOLDOWN_MENTION_RE = re.compile(r"cooldown|\bcd\b", re.I)


def _skill_text(skill: dict) -> str:
    parts: list[str] = []
    for k in ("description_lines", "detailed_description", "simple_description", "raw_text"):
        v = skill.get(k)
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, (list, tuple)):
            parts.extend(str(x) for x in v)
    return " \n ".join(parts)


def skill_cooldown(skill: dict) -> float | None:
    """Cooldown (seconds): the structured `cooldown` field the importer now writes ("10 s"/numeric), falling back to
    parsing the skill text for older data. None when no cooldown exists."""
    cd = skill.get("cooldown")
    if isinstance(cd, (int, float)):
        return float(cd)
    if isinstance(cd, str):
        m = _COOLDOWN_NUM_RE.search(cd)
        if m:
            return float(m.group(1))
    m = _COOLDOWN_RE.search(_skill_text(skill))
    return float(m.group(1)) if m else None


def skill_base_charges(skill: dict) -> int | None:
    """Base max charges: the structured `charges` field the importer writes (1 for a cooldown skill, None otherwise),
    falling back for older data to the explicit text count, else 1 for any cooldown skill / None for cooldown-less."""
    if "charges" in skill:
        return skill["charges"]
    if skill_cooldown(skill) is None:
        return None
    m = _CHARGE_COUNT_RE.search(_skill_text(skill))
    if m:
        try:
            return max(1, int(m.group(1)))
        except ValueError:
            pass
    return 1


def is_charge_ambiguous(skill: dict) -> bool:
    """True when the text mentions a cooldown/CD but no cooldown number could be parsed (a real parse gap to
    surface). A clean cooldown-less skill returns False."""
    return bool(_COOLDOWN_MENTION_RE.search(_skill_text(skill))) and skill_cooldown(skill) is None
