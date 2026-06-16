"""
Imports game-data skill JSON files into a season-stored _skills.json.

Each source file covers one skill category (e.g. "Activation Medium Skill.txt").
Fields kept per skill:
  item_id           — unique identifier (snake_case)
  name              — display name
  description_lines — list of display text lines
  raw_text          — full concatenated text (useful for search / future parsing)
  skill_tags        — list of tag strings (e.g. ["Attack", "Melee", "Active"])
"""

_KEEP_FIELDS = {"item_id", "name", "description_lines", "raw_text", "skill_tags"}


def clean_skill(raw: dict) -> dict:
    """Strip unwanted fields from a raw skill item."""
    cleaned = {k: v for k, v in raw.items() if k in _KEEP_FIELDS}
    # Ensure required fields are present with safe defaults
    cleaned.setdefault("item_id", "")
    cleaned.setdefault("name", "")
    cleaned.setdefault("description_lines", [])
    cleaned.setdefault("raw_text", "")
    cleaned.setdefault("skill_tags", [])
    return cleaned


def parse_skill_file(data: dict) -> list[dict]:
    """
    Parse a single skill JSON file.
    Expected shape: { "items": [ {...}, ... ], "extract_date": "...", ... }
    Returns a list of cleaned skill dicts.
    """
    items = data.get("items", [])
    if not isinstance(items, list):
        raise ValueError("skill file must have an 'items' array")

    skills: list[dict] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        skill = clean_skill(raw)
        if skill["item_id"]:
            skills.append(skill)
    return skills


def merge_skills(existing: list[dict], incoming: list[dict]) -> list[dict]:
    """
    Merge incoming skills into existing list, deduplicating by item_id.
    Incoming entries overwrite existing entries with the same item_id.
    """
    by_id: dict[str, dict] = {s["item_id"]: s for s in existing}
    for skill in incoming:
        by_id[skill["item_id"]] = skill
    return list(by_id.values())


# ── Crawler-format importer ────────────────────────────────────────────────

import re as _re

# The crawler leaves many values as UNREDUCED fractions ("41/4", "21/2", "6/100", "1/2") in both progression
# values and description text — e.g. Electric Overload's Lv1 "41/4" is 10.25, matching its "10.25 %" base.
# This plagues every data type, so normalize at import: evaluate a TWO-number N/M group to a clean decimal.
# The slash is overloaded: a chain of 3+ numbers ("1/3/6/100") is a per-enemy-tier LIST (Normal/Magic/Rare/
# Boss), NOT a fraction, so we match a whole slash-number group and only convert it when it has exactly two
# numbers — chains are left untouched. Ranges use "," or " - " (never "/"). 6 sig-figs drops trailing zeros
# without scientific notation here (41/4 -> "10.25", 21/2 -> "10.5", 1/3 -> "0.333333").
_FRACTION_RE = _re.compile(r"\b\d+(?:/\d+)+\b")
# A "/"-separated WORD list (Normal/Magic/Rare/Boss, Attack/Spell, Max/Min) signals that "/"-separated NUMBERS
# in the same string are a parallel per-category LIST, not a fraction — even a TWO-element one ("Normal/Magic …
# grants 1/3"). When present we skip the whole string, erring toward leaving a value unreduced (a harmless
# miss) rather than corrupting a list (a wrong conversion). No current string contains both, so this is pure
# future-proofing with zero effect on today's data.
_WORD_SLASH_LIST_RE = _re.compile(r"[A-Za-z]+/[A-Za-z]+")


def normalize_fractions(text: str) -> str:
    """Replace each unreduced two-number N/M fraction token in a string with its decimal value (e.g. '41/4'
    -> '10.25'). Slash chains of 3+ numbers (per-tier lists like '1/3/6/100') and any string carrying a
    parallel word-slash-list (a per-category list signal) are left unchanged."""
    if not isinstance(text, str) or "/" not in text or _WORD_SLASH_LIST_RE.search(text):
        return text
    def _sub(m):
        parts = m.group(0).split("/")
        if len(parts) != 2:
            return m.group(0)          # 3+ chain → a list, not a fraction
        num, den = int(parts[0]), int(parts[1])
        return m.group(0) if den == 0 else f"{num / den:.6g}"
    return _FRACTION_RE.sub(_sub, text)


def _normalize_deep(obj):
    """Recursively apply normalize_fractions to every string in a nested dict/list (e.g. progression values)."""
    if isinstance(obj, str):
        return normalize_fractions(obj)
    if isinstance(obj, list):
        return [_normalize_deep(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _normalize_deep(v) for k, v in obj.items()}
    return obj


def _as_lines(val) -> list[str]:
    """Normalize a description field to a list of non-empty lines (the recrawl emits lists; older data a string)."""
    if isinstance(val, list):
        return [str(x) for x in val if str(x).strip()]
    if isinstance(val, str) and val.strip():
        return [val]
    return []


def _dedup_lines(lines: list[str]) -> list[str]:
    """Drop duplicate description lines (the recrawl emits each effect line twice for most supports — ~59/60
    support_skill, ~41/60 noble), preserving first-occurrence order. Keyed on collapsed whitespace so trivial
    spacing differences still dedup. Exact-duplicate description lines are always the crawler artifact, never
    meaningful, so this is safe across all skill types (active descriptions have no dupes and are unaffected)."""
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        key = " ".join(line.split())
        if key and key not in seen:
            seen.add(key)
            out.append(line)
    return out


def import_crawler_skill(data: dict) -> dict:
    """Import a single crawler skill file (one JSON file per skill).

    The recrawl emits `simple_description` (Lv1) and `detailed_description` (Lv20) as SPLIT LINE LISTS, plus a
    `sealed_mana` reservation amount. We keep both anchor descriptions (for aura/focus per-level interpolation)
    and `sealed_mana`; `description_lines` mirrors the simple (Lv1) lines for back-compat with existing readers.
    """
    name = data.get("name", "")
    item_id = _re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    variant = (data.get("variants") or [{}])[0]
    glossary = {
        g["term_id"]: {"name": g.get("name", ""), "description": g.get("description", "")}
        for g in (data.get("glossary") or [])
        if g.get("term_id")
    }
    simple = _dedup_lines([normalize_fractions(l) for l in _as_lines(variant.get("simple_description"))])
    detailed = _dedup_lines([normalize_fractions(l) for l in _as_lines(variant.get("detailed_description"))])
    out = {
        "item_id": item_id,
        "name": name,
        "internal_id": data.get("internal_id"),
        "skill_type": data.get("skill_type", ""),
        "skill_tags": variant.get("tags") or [],
        "description_lines": simple,                     # Lv1 lines (back-compat readers use this)
        "simple_description": simple,                    # Lv1 anchor (split lines)
        "detailed_description": detailed,                # Lv20 anchor (split lines)
        "raw_text": " ".join(detailed or simple),
        "max_level": variant.get("max_level"),
        "mana_cost": variant.get("mana_cost"),
        "sealed_mana": variant.get("sealed_mana"),       # reservation amount, e.g. "50%"
        "cast_speed": variant.get("cast_speed"),
        "effectiveness_of_added_damage": variant.get("effectiveness_of_added_damage"),
        "weapon_restriction": variant.get("weapon_restriction"),
        "main_stat": variant.get("main_stat"),
        "progression": _normalize_deep(data.get("progression") or variant.get("progression") or []),
        "glossary": glossary,
    }
    # Dev-set "can contribute to DPS" override — only persist when explicitly present (else /api/skills
    # derives it from skill_type). Never write null, which would read as "explicitly ineligible".
    if "dps_eligible" in data:
        out["dps_eligible"] = bool(data["dps_eligible"])
    return out


def import_crawler_skills(items_data: list[dict]) -> list[dict]:
    return [import_crawler_skill(item) for item in items_data if item.get("name")]
