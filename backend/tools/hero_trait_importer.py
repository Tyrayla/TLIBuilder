"""
Imports hero trait JSON files (one file per trait variant) into a season-stored
_hero_traits.json.

Fields kept per trait:
  trait_id        — unique identifier (e.g. "bing_blast_nova")
  hero            — hero name (e.g. "Bing")
  variant_name    — trait variant display name (e.g. "Blast Nova")
  description     — flavor/mechanic description
  levels          — list of 5 base-trait level objects:
                    { level, effects: [...], unlock_level }
  artificial_moon — hero-specific moon mechanic: { description, effects: [...] }
  advanced_traits — list of advanced trait objects:
                    { name, unlock_level, is_pick_one_from_two, effects: [...] }

Fields discarded: base_skill, status, version, atomic_links (within advanced_traits)
"""

_TRAIT_KEEP = {"trait_id", "hero", "variant_name", "description", "levels",
               "artificial_moon", "advanced_traits"}

_LEVEL_KEEP = {"level", "effects", "unlock_level"}

_ADVANCED_KEEP = {"name", "unlock_level", "is_pick_one_from_two", "effects"}


def _clean_level(raw: dict) -> dict:
    cleaned = {k: v for k, v in raw.items() if k in _LEVEL_KEEP}
    cleaned.setdefault("level", 0)
    cleaned.setdefault("effects", [])
    cleaned.setdefault("unlock_level", 1)
    return cleaned


def _clean_advanced_trait(raw: dict) -> dict:
    cleaned = {k: v for k, v in raw.items() if k in _ADVANCED_KEEP}
    cleaned.setdefault("name", "")
    cleaned.setdefault("unlock_level", 0)
    cleaned.setdefault("is_pick_one_from_two", False)
    cleaned.setdefault("effects", [])
    return cleaned


def clean_hero_trait(raw: dict) -> dict:
    """Strip unwanted fields from a raw hero trait file."""
    cleaned = {k: v for k, v in raw.items() if k in _TRAIT_KEEP}

    cleaned.setdefault("trait_id", "")
    cleaned.setdefault("hero", "")
    cleaned.setdefault("variant_name", "")
    cleaned.setdefault("description", "")

    cleaned["levels"] = [
        _clean_level(lv)
        for lv in (cleaned.get("levels") or [])
        if isinstance(lv, dict)
    ]

    am = cleaned.get("artificial_moon")
    if isinstance(am, dict):
        cleaned["artificial_moon"] = {
            "description": am.get("description", ""),
            "effects": am.get("effects") or [],
        }
    else:
        cleaned["artificial_moon"] = {"description": "", "effects": []}

    cleaned["advanced_traits"] = [
        _clean_advanced_trait(at)
        for at in (cleaned.get("advanced_traits") or [])
        if isinstance(at, dict)
    ]

    return cleaned


def parse_hero_trait_file(data: dict) -> dict:
    """
    Parse a single hero trait JSON file and return a cleaned trait dict.
    Raises ValueError if the file is not a valid hero trait (missing trait_id).
    """
    if not isinstance(data, dict):
        raise ValueError("hero trait file must be a JSON object")
    trait = clean_hero_trait(data)
    if not trait["trait_id"]:
        raise ValueError("hero trait file missing required field 'trait_id'")
    return trait


def merge_hero_traits(existing: list[dict], incoming: dict) -> list[dict]:
    """
    Merge one incoming trait into the existing list, deduplicating by trait_id.
    The incoming entry overwrites any existing entry with the same trait_id.
    """
    by_id: dict[str, dict] = {t["trait_id"]: t for t in existing}
    by_id[incoming["trait_id"]] = incoming
    return list(by_id.values())


# ── Crawler-format importer ────────────────────────────────────────────────

import re as _re
from collections import Counter as _Counter

_HERO_RE = _re.compile(r"HeroTraits/([^/]+)/")
_AM_RE = _re.compile(r"Artificial Moon:\s*.+", _re.I)


def import_crawler_hero_trait(data: dict) -> dict:
    """Import a single crawler hero trait file (one JSON file per trait variant)."""
    name = data.get("name", "")
    trait_id = _re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    traits = data.get("traits") or []

    # Base trait = first entry with levels; advanced = entries without levels
    base = next((t for t in traits if t.get("levels")), {})
    advanced_raw = [t for t in traits if not t.get("levels")]

    # Extract hero from base trait icon_url
    icon_url = base.get("icon_url", "")
    hero_m = _HERO_RE.search(icon_url)
    hero = hero_m.group(1) if hero_m else ""

    # Build levels; extract Artificial Moon text when found
    am_effects: list[str] = []
    levels: list[dict] = []
    for lv in (base.get("levels") or []):
        desc = lv.get("description", "")
        am_m = _AM_RE.search(desc)
        if am_m and not am_effects:
            am_effects = [am_m.group(0)]
            desc = desc[: am_m.start()].rstrip()
        levels.append({
            "level": lv.get("level", 0),
            "effects": [desc] if desc else [],
            "unlock_level": 1,
        })

    # Determine is_pick_one_from_two by counting traits per required_level
    level_counts = _Counter(t.get("required_level", 0) for t in advanced_raw)
    advanced_traits = [
        {
            "name": t.get("name", ""),
            "unlock_level": t.get("required_level", 0),
            "is_pick_one_from_two": level_counts[t.get("required_level", 0)] > 1,
            "effects": [t["description"]] if t.get("description") else [],
        }
        for t in advanced_raw
    ]

    glossary = {
        g["term_id"]: {"name": g.get("name", ""), "description": g.get("description", "")}
        for g in (data.get("glossary") or [])
        if g.get("term_id")
    }

    return {
        "trait_id": trait_id,
        "hero": hero,
        "variant_name": name,
        "description": "",
        "levels": levels,
        "artificial_moon": {"description": "", "effects": am_effects},
        "advanced_traits": advanced_traits,
        "max_level": data.get("max_level"),
        "glossary": glossary,
    }


def import_crawler_hero_traits(items_data: list[dict]) -> list[dict]:
    return [import_crawler_hero_trait(item) for item in items_data if item.get("name")]
