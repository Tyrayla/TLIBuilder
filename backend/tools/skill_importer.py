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

def import_crawler_skill(data: dict) -> dict:
    """Import a single crawler skill file (one JSON file per skill)."""
    name = data.get("name", "")
    item_id = _re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    variant = (data.get("variants") or [{}])[0]
    glossary = {
        g["term_id"]: {"name": g.get("name", ""), "description": g.get("description", "")}
        for g in (data.get("glossary") or [])
        if g.get("term_id")
    }
    simple = variant.get("simple_description") or ""
    return {
        "item_id": item_id,
        "name": name,
        "internal_id": data.get("internal_id"),
        "skill_type": data.get("skill_type", ""),
        "skill_tags": variant.get("tags") or [],
        "description_lines": [simple] if simple else [],
        "raw_text": variant.get("detailed_description") or "",
        "max_level": variant.get("max_level"),
        "mana_cost": variant.get("mana_cost"),
        "cast_speed": variant.get("cast_speed"),
        "weapon_restriction": variant.get("weapon_restriction"),
        "main_stat": variant.get("main_stat"),
        "progression": data.get("progression") or [],
        "glossary": glossary,
    }


def import_crawler_skills(items_data: list[dict]) -> list[dict]:
    return [import_crawler_skill(item) for item in items_data if item.get("name")]
