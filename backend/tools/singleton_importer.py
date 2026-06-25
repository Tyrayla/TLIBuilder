"""
Importers for singleton crawler files: destiny, ethereal_prism, hero_memories,
memory_revival, tower_sequence. Each has exactly one file per season.
"""
import re


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


_TEMPER_RANGE_RE = re.compile(
    r'\[(Micro|Medium|Legendary Medium) Talent Effect Range:\s*(-?\d+)\s*-\s*(-?\d+)\]', re.I)
_TEMPER_KEY = {"micro": "micro", "medium": "medium", "legendary medium": "legendary"}


def _parse_temper_ranges(glossary) -> dict | None:
    """Pull the per-tier roll ranges out of an Inverse Image's 'Temper' glossary description, e.g.
    '[Micro Talent Effect Range: -100-200][Medium ...: -100-100][Legendary Medium ...: -100-50]'."""
    for g in (glossary or []):
        desc = g.get("description", "") if isinstance(g, dict) else ""
        if "Talent Effect Range" not in desc:
            continue
        ranges = {}
        for label, lo, hi in _TEMPER_RANGE_RE.findall(desc):
            ranges[_TEMPER_KEY[label.lower()]] = [int(lo), int(hi)]
        if ranges:
            return ranges
    return None


def _prism_item(it: dict, kind: str) -> dict:
    out = {
        "name": it.get("name", ""),
        "kind": kind,
        "icon_url": it.get("icon_url", ""),
        "tags": it.get("tags") or [],
        "detail": it.get("detail") or [],
        "implicit": it.get("implicit") or [],
        # For replace prisms, the glossary carries the replacement Core Talent's name + description.
        "glossary": it.get("glossary") or [],
    }
    rr = _parse_temper_ranges(it.get("glossary"))
    if rr:
        out["roll_ranges"] = rr
    return out


def import_ethereal_prism(data: dict, season_name: str) -> dict:
    """New 4-section crawler format → a structured prism catalog: prism ITEMS (Inverse Image + Ethereal Prisms,
    each with name/icon/tags/detail/implicit and, for Inverse Image, the tempered roll ranges) plus the base- and
    random-affix pools (kept for the future Ethereal-Prism crafting work)."""
    items, base_affixes, random_affixes = [], [], []
    for section in (data.get("sections") or []):
        header = (section.get("header") or "").strip().lower()
        sec_items = section.get("items") or []
        if header.startswith("base affix"):
            base_affixes = [it.get("Modifier", "") for it in sec_items if it.get("Modifier")]
        elif header.startswith("random affix"):
            random_affixes = [{"modifier": it.get("Modifier", ""), "type": it.get("Type", "")}
                              for it in sec_items if it.get("Modifier")]
        elif header.startswith("inverse image"):
            items += [_prism_item(it, "inverse_image") for it in sec_items if it.get("name")]
        elif header.startswith("item"):
            items += [_prism_item(it, "ethereal_prism") for it in sec_items if it.get("name")]
    return {
        "season": season_name,
        "item_count": len(items),
        "items": items,
        "base_affixes": base_affixes,
        "random_affixes": random_affixes,
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
