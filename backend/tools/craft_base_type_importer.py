import re
from tools.legendary_gear_importer import parse_affix_text

_PAREN_HASH_RE = re.compile(r'\(#\)')

# Maps craft_affixes Library names to the affix_type stored in the DB
_LIBRARY_TO_TYPE = {
    "Basic Affix": "Basic Pre-fix",
    "Advanced Affix": "Advanced Pre-fix",
    "Ultimate Affix": "Ultimate Pre-fix",
}

# Suffix types that only appear in all_affixes (no tier data in craft_affixes)
_SUFFIX_TYPES = {"Basic Suffix", "Advanced Suffix", "Ultimate Suffix"}
_BASE_TYPES = {"Base Affix"}


def _parse_tier(tier_str: str) -> float:
    """Convert tier string to sortable float. '0+' → -0.5, '0' → 0, '1' → 1, etc."""
    s = str(tier_str).strip()
    if s.endswith("+"):
        try:
            return float(s[:-1]) - 0.5
        except ValueError:
            return -0.5
    try:
        return float(s)
    except ValueError:
        return 999.0


def import_crawler_craft_base_type(data: dict) -> dict:
    name = data.get("name", "")
    item_id = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")

    affixes = []

    # --- Base affixes from all_affixes (intrinsic item stats, single tier) ---
    for a in (data.get("all_affixes") or []):
        atype = a.get("Type", "")
        if atype not in _BASE_TYPES:
            continue
        text = a.get("Affix Effect", "")
        parsed = parse_affix_text(text, None)
        parsed["source"] = a.get("Source", "")
        parsed["affix_type"] = atype
        parsed["tier"] = "0"
        affixes.append(parsed)

    # --- Craftable prefix-type affixes from craft_affixes (full tier data) ---
    for a in (data.get("craft_affixes") or []):
        library = a.get("Library", "")
        affix_type = _LIBRARY_TO_TYPE.get(library)
        if not affix_type:
            continue
        text = a.get("Modifier", "")
        tier = str(a.get("Tier", "0"))
        parsed = parse_affix_text(text, None)
        # Normalize expression: fixed-value tiers produce "+#" while range tiers produce "+(#)".
        # Strip the parens so all tiers of the same modifier share one expression key.
        parsed["expression"] = _PAREN_HASH_RE.sub('#', parsed["expression"])
        parsed["source"] = name
        parsed["affix_type"] = affix_type
        parsed["tier"] = tier
        affixes.append(parsed)

    # --- Suffix affixes from all_affixes (no tier data in craft_affixes) ---
    for a in (data.get("all_affixes") or []):
        atype = a.get("Type", "")
        if atype not in _SUFFIX_TYPES:
            continue
        text = a.get("Affix Effect", "")
        parsed = parse_affix_text(text, None)
        parsed["source"] = a.get("Source", "")
        parsed["affix_type"] = atype
        parsed["tier"] = "0"
        affixes.append(parsed)

    raw_base_items = data.get("base_items", [])
    base_items = []
    for bi in raw_base_items:
        raw_implicits = bi.get("implicits") or []
        # Handle both string[] and {modifier_id, text}[] formats from crawler
        implicits = []
        for imp in raw_implicits:
            if isinstance(imp, dict):
                text = imp.get("text", "")
            else:
                text = str(imp)
            if text:
                implicits.append(text)
        base_items.append({
            "name": bi.get("name", ""),
            "required_level": bi.get("required_level", 0),
            "armor": bi.get("armor"),
            "implicits": implicits,
        })

    corrosion_base_affixes = []
    for a in (data.get("corrosion_base") or []):
        text = a.get("Modifier", "").strip()
        if text:
            parsed = parse_affix_text(text, None)
            parsed["modifier_text"] = text
            corrosion_base_affixes.append(parsed)

    return {
        "item_id": item_id,
        "name": name,
        "affixes": affixes,
        "base_items": base_items,
        "corrosion_base_affixes": corrosion_base_affixes,
    }


def import_crawler_craft_base_types(items_data: list[dict]) -> list[dict]:
    return [import_crawler_craft_base_type(item) for item in items_data if item.get("name")]
