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
