import re
from tools.legendary_gear_importer import parse_affix_text


def import_crawler_graft(data: dict) -> dict:
    name = data.get("name", "")
    item_id = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")

    affixes = []
    for a in (data.get("craft_affixes") or []):
        text = a.get("modifier", "")
        parsed = parse_affix_text(text, None)
        try:
            parsed["level"] = int(a.get("level", 0))
        except (ValueError, TypeError):
            parsed["level"] = 0
        try:
            parsed["weight"] = int(a.get("weight", 0))
        except (ValueError, TypeError):
            parsed["weight"] = 0
        parsed["tier"] = a.get("tier", "")
        parsed["affix_type"] = a.get("affix_type", "")
        affixes.append(parsed)

    return {
        "item_id": item_id,
        "name": name,
        "affixes": affixes,
    }


def import_crawler_grafts(items_data: list[dict]) -> list[dict]:
    return [import_crawler_graft(item) for item in items_data if item.get("name")]
