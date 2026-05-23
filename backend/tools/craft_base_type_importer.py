import re
from tools.legendary_gear_importer import parse_affix_text


def import_crawler_craft_base_type(data: dict) -> dict:
    name = data.get("name", "")
    item_id = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")

    affixes = []
    for a in (data.get("all_affixes") or []):
        text = a.get("Affix Effect", "")
        parsed = parse_affix_text(text, None)
        parsed["source"] = a.get("Source", "")
        parsed["affix_type"] = a.get("Type", "")
        affixes.append(parsed)

    return {
        "item_id": item_id,
        "name": name,
        "affixes": affixes,
    }


def import_crawler_craft_base_types(items_data: list[dict]) -> list[dict]:
    return [import_crawler_craft_base_type(item) for item in items_data if item.get("name")]
