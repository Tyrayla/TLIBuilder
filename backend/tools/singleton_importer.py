"""
Importers for singleton crawler files: destiny, ethereal_prism, hero_memories,
memory_revival, tower_sequence. Each has exactly one file per season.

Of these, only hero_memories carries scraper-minted ModifierLine cells (the others still emit
plain strings — verified against output/SS12).
"""
import re

from engine.modifier_lines import line_text, slim_checked


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
        {"name": it.get("name", ""), "icon_url": it.get("icon_url", "") or "",
         "implicit": it.get("implicit") or [],   # effect lines (clean)
         "detail": it.get("detail") or []}       # "Install to replace a Micro/Medium Talent Node" + flavor
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


def _prism_item(it: dict, kind: str, replacement_glossary: dict[str, dict] | None = None) -> dict:
    glossary = it.get("glossary") or []
    if kind == "ethereal_prism" and replacement_glossary:
        short_name = it.get("name", "").split(":", 1)[-1].strip()
        term = replacement_glossary.get(short_name.casefold())
        if term and not any((g.get("name") or "").casefold() == short_name.casefold() for g in glossary):
            glossary = [*glossary, term]
    out = {
        "name": it.get("name", ""),
        "kind": kind,
        "icon_url": it.get("icon_url", ""),
        "tags": it.get("tags") or [],
        "detail": it.get("detail") or [],
        "implicit": it.get("implicit") or [],
        # For replace prisms, the glossary carries the replacement Core Talent's name + description.
        "glossary": glossary,
    }
    rr = _parse_temper_ranges(glossary)
    if rr:
        out["roll_ranges"] = rr
    return out


def import_ethereal_prism(data: dict, season_name: str) -> dict:
    """New 4-section crawler format → a structured prism catalog: prism ITEMS (Inverse Image + Ethereal Prisms,
    each with name/icon/tags/detail/implicit and, for Inverse Image, the tempered roll ranges) plus the base- and
    random-affix pools (kept for the future Ethereal-Prism crafting work)."""
    items, base_affixes, random_affixes = [], [], []
    # Replacement effects now live in TLIDB's linked hover-card payloads on the
    # Base Affix table, not inline in each Prism card. Keep the name → glossary
    # relationship while flattening that table so the item's existing `glossary`
    # field can continue feeding the catalog's replacement-description UI.
    replacement_glossary: dict[str, dict] = {}
    for section in (data.get("sections") or []):
        header = (section.get("header") or "").strip().lower()
        sec_items = section.get("items") or []
        def modifier_text(it):
            raw = it.get("Modifier") or it.get("Affix Effect")
            return line_text(raw).strip() if raw else ""

        if header.startswith("base affix"):
            base_affixes = [modifier_text(it) for it in sec_items if modifier_text(it)]
            for row in sec_items:
                modifier = modifier_text(row)
                match = re.search(r"^Replaces the Core Talent.+?\bwith\s+(.+?)\s*$", modifier, re.I)
                if not match:
                    continue
                target = match.group(1).strip()
                for term in row.get("hover_terms") or []:
                    if (term.get("name") or "").strip().casefold() == target.casefold() and term.get("description"):
                        replacement_glossary[target.casefold()] = {
                            key: term[key] for key in ("term_id", "name", "description") if term.get(key)
                        }
                        break
        elif header.startswith("random affix") or header.startswith("prism gauge"):
            random_affixes += [
                {"modifier": modifier_text(it), "type": it.get("Type") or ""}
                for it in sec_items if modifier_text(it)
            ]
        elif header.startswith("inverse image"):
            items += [_prism_item(it, "inverse_image") for it in sec_items if it.get("name")]
        elif header.startswith("item"):
            items += [_prism_item(it, "ethereal_prism", replacement_glossary) for it in sec_items if it.get("name")]
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
    # `modifier` stays a plain string (row shape unchanged); the minted ids ride alongside. The
    # '+'/capitalize normalization is sign/case-only — identity-invariant — which slim_checked verifies.
    line = it.get("Modifier", "")
    ids = slim_checked(line, _normalize_memory_modifier(line_text(line)))
    return {
        "tier": tier,
        "modifier": ids["text"],
        "uuid": ids["uuid"],
        "pooling_uuid": ids["pooling_uuid"],
        "modifier_id": ids["modifier_id"],
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
            "uuid": mt.get("uuid"),
            "internal_id": mt.get("internal_id"),
            "icon_url": mt.get("icon_url", ""),
        }
        for mt in (data.get("memory_types") or [])
        if mt.get("name")
    ]
    total = len(fixed_affixes) + len(random_affixes) + len(base_stats)
    return {
        "season": season_name,
        "uuid": data.get("uuid"),
        "affix_count": total,
        "memory_types": memory_types,
        "fixed_affixes": fixed_affixes,
        "random_affixes": random_affixes,
        "base_stats": base_stats,
    }


def import_memory_revival(data: dict, season_name: str) -> dict:
    raw_items = _flatten_sections(data)
    # Tier-0 named revival mods carry only a NAME in the section 'Modifier' (e.g. "Artificial Moon: Origin");
    # their real effect text lives in the crawl's `glossary` (keyed by that name). Merge the glossary description
    # in so the Builder gets the full text (rarity cap / penalty / base-slot wording) instead of a bare name.
    # (T1/T2 mods already carry their full text in 'Modifier', so they have no separate glossary entry to merge.)
    gloss = {
        (g.get("name") or "").strip(): (g.get("description") or "").strip()
        for g in (data.get("glossary") or [])
    }
    affixes = []
    for it in raw_items:
        modifier = it.get("Modifier") or it.get("Affix Effect", "")
        if not modifier:
            continue
        tier_known = it.get("Tier") not in (None, "")
        def optional_int(value):
            if value in (None, ""):
                return None
            try:
                return int(value)
            except (ValueError, TypeError):
                return None

        entry = {
            "tier": optional_int(it.get("Tier")),
            "modifier": modifier,
            "level": optional_int(it.get("Level")),
            "weight": optional_int(it.get("Weight")),
            "source": it.get("Source") or "revival",
            "type": it.get("Type"),
            "tier_known": tier_known,
        }
        desc = gloss.get(modifier.strip())
        if desc and desc != modifier.strip():
            entry["description"] = desc
        affixes.append(entry)
    return {
        "season": season_name,
        "affix_count": len(affixes),
        "affixes": affixes,
    }


def import_tower_sequence(data: dict, season_name: str) -> dict:
    raw_items = _flatten_sections(data)
    entries = []
    for it in raw_items:
        affix = it.get("Affix") or it.get("Affix Effect", "")
        if not affix:
            continue
        sequence_type = (it.get("Type") or "").strip()
        if sequence_type and not affix.rstrip().endswith(sequence_type):
            affix = f"{affix.rstrip()} {sequence_type}"
        sources = it.get("Source", "")
        if isinstance(sources, list):
            source_names = sources
        else:
            source_names = str(sources).split(",")
        for source in dict.fromkeys(name.strip() for name in source_names if name.strip()):
            entries.append({"affix": affix, "source": source})
    return {
        "season": season_name,
        "entry_count": len(entries),
        "entries": entries,
    }
