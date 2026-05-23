"""
Importers for singleton crawler files: destiny, ethereal_prism, hero_memories,
memory_revival, tower_sequence. Each has exactly one file per season.
"""


def _flatten_sections(data: dict, item_key: str | None = None) -> list[dict]:
    """Collect all items across all sections into a flat list."""
    items = []
    for section in (data.get("sections") or []):
        for item in (section.get("items") or []):
            items.append(item if item_key is None else item)
    return items


def import_destiny(data: dict, season_name: str) -> dict:
    raw_items = _flatten_sections(data)
    items = [
        {"name": it.get("name", ""), "text": it.get("text", "")}
        for it in raw_items
        if it.get("name")
    ]
    return {
        "season": season_name,
        "item_count": len(items),
        "items": items,
    }


def import_ethereal_prism(data: dict, season_name: str) -> dict:
    raw_items = _flatten_sections(data)
    modifiers = [it.get("Modifier", "") for it in raw_items if it.get("Modifier")]
    return {
        "season": season_name,
        "modifier_count": len(modifiers),
        "modifiers": modifiers,
    }


def import_hero_memories(data: dict, season_name: str) -> dict:
    raw_items = _flatten_sections(data)
    affixes = [
        {
            "effect": it.get("Affix Effect", ""),
            "source": it.get("Source", ""),
            "affix_type": it.get("Type", ""),
        }
        for it in raw_items
        if it.get("Affix Effect")
    ]
    return {
        "season": season_name,
        "affix_count": len(affixes),
        "affixes": affixes,
    }


def import_memory_revival(data: dict, season_name: str) -> dict:
    raw_items = _flatten_sections(data)
    affixes = []
    for it in raw_items:
        modifier = it.get("Modifier", "")
        if not modifier:
            continue
        try:
            tier = int(it.get("Tier", 0))
        except (ValueError, TypeError):
            tier = 0
        try:
            level = int(it.get("Level", 0))
        except (ValueError, TypeError):
            level = 0
        try:
            weight = int(it.get("Weight", 0))
        except (ValueError, TypeError):
            weight = 0
        affixes.append({"tier": tier, "modifier": modifier, "level": level, "weight": weight})
    return {
        "season": season_name,
        "affix_count": len(affixes),
        "affixes": affixes,
    }


def import_tower_sequence(data: dict, season_name: str) -> dict:
    raw_items = _flatten_sections(data)
    entries = [
        {"affix": it.get("Affix", ""), "source": it.get("Source", "")}
        for it in raw_items
        if it.get("Affix")
    ]
    return {
        "season": season_name,
        "entry_count": len(entries),
        "entries": entries,
    }
