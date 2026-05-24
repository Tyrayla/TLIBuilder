import re
from tools.legendary_gear_importer import parse_affix_text


def _parse_affix_list(raw: list[dict], tier_key: str = "tier", modifier_key: str = "modifier",
                      level_key: str = "level", weight_key: str = "weight",
                      affix_type_key: str | None = "affix_type",
                      default_affix_type: str = "") -> list[dict]:
    result = []
    for a in raw:
        text = a.get(modifier_key, "")
        parsed = parse_affix_text(text, None)
        try:
            parsed["level"] = int(a.get(level_key, 0) or 0)
        except (ValueError, TypeError):
            parsed["level"] = 0
        try:
            parsed["weight"] = int(a.get(weight_key, 0) or 0)
        except (ValueError, TypeError):
            parsed["weight"] = 0
        parsed["tier"] = str(a.get(tier_key, ""))
        parsed["affix_type"] = a.get(affix_type_key, default_affix_type) if affix_type_key else default_affix_type
        result.append(parsed)
    return result


def import_crawler_graft(data: dict) -> dict:
    name = data.get("name", "")
    item_id = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")

    affixes = _parse_affix_list(data.get("craft_affixes") or [])

    # base_affixes use capitalized keys and have no affix_type field
    base_affixes = _parse_affix_list(
        data.get("base_affixes") or [],
        tier_key="Tier", modifier_key="Modifier",
        level_key="Level", weight_key="Weight",
        affix_type_key=None, default_affix_type="Base Affix",
    )

    legendary_items = [
        item["name"]
        for item in (data.get("legendary_items") or [])
        if item.get("name")
    ]

    return {
        "item_id": item_id,
        "name": name,
        "legendary_items": legendary_items,
        "base_affixes": base_affixes,
        "affixes": affixes,
    }


def import_crawler_grafts(items_data: list[dict]) -> list[dict]:
    return [import_crawler_graft(item) for item in items_data if item.get("name")]
