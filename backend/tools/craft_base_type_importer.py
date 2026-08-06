import re
from engine.modifier_lines import line_text, line_pooling_uuid, slim
from tools.legendary_gear_importer import parse_affix_text

_PAREN_HASH_RE = re.compile(r'\(#\)')


def _parse_affix_line(line) -> dict:
    """parse_affix_text over a ModifierLine dict (legacy: plain string), carrying the minted ids."""
    parsed = parse_affix_text(line_text(line), line.get("modifier_id") if isinstance(line, dict) else None)
    parsed["uuid"] = line.get("uuid") if isinstance(line, dict) else None
    parsed["pooling_uuid"] = line_pooling_uuid(line)
    return parsed

# Maps craft_affixes / craft_suffix_affixes Library names (the affix quality) to the affix_type stored in
# the DB. Same Library names appear in both tables; the prefix/suffix distinction comes from which table.
_LIBRARY_TO_TYPE = {
    "Basic Affix": "Basic Pre-fix",
    "Advanced Affix": "Advanced Pre-fix",
    "Ultimate Affix": "Ultimate Pre-fix",
}
_LIBRARY_TO_SUFFIX_TYPE = {
    "Basic Affix": "Basic Suffix",
    "Advanced Affix": "Advanced Suffix",
    "Ultimate Affix": "Ultimate Suffix",
}

# Suffix types in all_affixes — used only as a single-tier FALLBACK when the crawler has no
# craft_suffix_affixes tier data for this base type.
_SUFFIX_TYPES = {"Basic Suffix", "Advanced Suffix", "Ultimate Suffix"}
_BASE_TYPES = {"Base Affix"}


def import_crawler_craft_base_type(data: dict) -> dict:
    name = data.get("name", "")
    item_id = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")

    affixes = []

    # --- Base affixes from all_affixes (intrinsic item stats, single tier) ---
    for a in (data.get("all_affixes") or []):
        atype = a.get("Type", "")
        if atype not in _BASE_TYPES:
            continue
        parsed = _parse_affix_line(a.get("Affix Effect", ""))
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
        tier = str(a.get("Tier", "0"))
        parsed = _parse_affix_line(a.get("Modifier", ""))
        # Normalize expression: fixed-value tiers produce "+#" while range tiers produce "+(#)".
        # Strip the parens so all tiers of the same modifier share one expression key.
        parsed["expression"] = _PAREN_HASH_RE.sub('#', parsed["expression"])
        parsed["source"] = name
        parsed["affix_type"] = affix_type
        parsed["tier"] = tier
        affixes.append(parsed)

    # --- Craftable SUFFIX affixes from craft_suffix_affixes (full tier data, mirrors the prefix block) ---
    craft_suffixes = data.get("craft_suffix_affixes") or []
    for a in craft_suffixes:
        affix_type = _LIBRARY_TO_SUFFIX_TYPE.get(a.get("Library", ""))
        if not affix_type:
            continue
        parsed = _parse_affix_line(a.get("Modifier", ""))
        parsed["expression"] = _PAREN_HASH_RE.sub('#', parsed["expression"])
        parsed["source"] = name
        parsed["affix_type"] = affix_type
        parsed["tier"] = str(a.get("Tier", "0"))
        affixes.append(parsed)

    # --- Suffix affixes from all_affixes — FALLBACK only when the crawler emitted no suffix tier data
    # (older outputs without craft_suffix_affixes). Single tier "0" per suffix, as before. ---
    if not craft_suffixes:
        for a in (data.get("all_affixes") or []):
            atype = a.get("Type", "")
            if atype not in _SUFFIX_TYPES:
                continue
            parsed = _parse_affix_line(a.get("Affix Effect", ""))
            parsed["source"] = a.get("Source", "")
            parsed["affix_type"] = atype
            parsed["tier"] = "0"
            affixes.append(parsed)

    raw_base_items = data.get("base_items", [])
    base_items = []
    for bi in raw_base_items:
        # Implicits stored as slim modifier-line dicts (crawler emits ModifierLine dicts; older
        # outputs had string[] / {modifier_id, text}[] — all coerce through slim()).
        implicits = [slim(imp) for imp in (bi.get("implicits") or []) if line_text(imp)]
        base_items.append({
            "name": bi.get("name", ""),
            "required_level": bi.get("required_level", 0),
            "armor": bi.get("armor"),
            "implicits": implicits,
        })

    corrosion_base_affixes = []
    for a in (data.get("corrosion_base") or []):
        line = a.get("Modifier", "")
        text = line_text(line).strip()
        if text:
            parsed = _parse_affix_line(line)
            parsed["modifier_text"] = text
            corrosion_base_affixes.append(parsed)

    # Sweet Dream Affix rows arrive in one of two shapes depending on which DOM path the crawler
    # took (see tlidb-crawler schemas/__init__.py CraftBaseTypeRecord.sweet_dream_affixes): the
    # historical dedicated-pane shape (Tier/Modifier/Level/Weight, same as corrosion_base) or the
    # 2026-07-30 fallback shape filtered from the shared #Affix pane (Affix Effect/Source/Type,
    # same as all_affixes). Normalize both into the same modifier_text/parsed shape.
    sweet_dream_affixes = []
    for a in (data.get("sweet_dream_affixes") or []):
        line = a.get("Modifier") if "Modifier" in a else a.get("Affix Effect", "")
        text = line_text(line).strip()
        if text:
            parsed = _parse_affix_line(line)
            parsed["modifier_text"] = text
            sweet_dream_affixes.append(parsed)

    return {
        "item_id": item_id,
        "name": name,
        "uuid": data.get("uuid"),
        "affixes": affixes,
        "base_items": base_items,
        "corrosion_base_affixes": corrosion_base_affixes,
        "sweet_dream_affixes": sweet_dream_affixes,
    }


def import_crawler_craft_base_types(items_data: list[dict]) -> list[dict]:
    return [import_crawler_craft_base_type(item) for item in items_data if item.get("name")]
