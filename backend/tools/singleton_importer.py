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


def _normalize_memory_modifier(modifier: str) -> str:
    """Ensure modifier has leading '+' if numeric, and capitalize first letter."""
    if not modifier:
        return modifier
    # Add leading + if modifier starts with a digit (e.g. '35.2 % Attack Speed')
    if modifier[0].isdigit():
        modifier = '+' + modifier
    # Capitalize first letter for non-numeric starts (e.g. 'attack Crit...' -> 'Attack Crit...')
    if modifier and modifier[0] not in ('+', '(', '-'):
        modifier = modifier[0].upper() + modifier[1:]
    return modifier


def _parse_memory_affix(it: dict) -> dict:
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
    return {
        "tier": tier,
        "modifier": _normalize_memory_modifier(it.get("Modifier", "")),
        "level": level,
        "weight": weight,
        "source": it.get("Source", ""),
    }


def import_hero_memories(data: dict, season_name: str) -> dict:
    fixed_affixes = [
        _parse_memory_affix(it)
        for it in (data.get("fixed_affixes") or [])
        if it.get("Modifier")
    ]
    random_affixes = [
        _parse_memory_affix(it)
        for it in (data.get("random_affixes") or [])
        if it.get("Modifier")
    ]
    base_stats = [
        _parse_memory_affix(it)
        for it in (data.get("base_stats") or [])
        if it.get("Modifier")
    ]
    memory_types = [
        {
            "name": mt.get("name", ""),
            "internal_id": mt.get("internal_id"),
            "icon_url": mt.get("icon_url", ""),
        }
        for mt in (data.get("memory_types") or [])
        if mt.get("name")
    ]
    total = len(fixed_affixes) + len(random_affixes) + len(base_stats)
    return {
        "season": season_name,
        "affix_count": total,
        "memory_types": memory_types,
        "fixed_affixes": fixed_affixes,
        "random_affixes": random_affixes,
        "base_stats": base_stats,
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
