import re

_VALID_RINGS = {"inner", "mid", "outer"}


def import_crawler_spirit(data: dict) -> dict:
    name = data.get("name", "")
    item_id = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")

    # Normalize ring field: if not a known ring name, default to "outer"
    slots = []
    for s in (data.get("slots") or []):
        ring = s.get("ring", "")
        slots.append({
            "name": s.get("name", ""),
            "effect": s.get("effect", ""),
            "ring": ring if ring in _VALID_RINGS else "outer",
        })

    glossary = {
        g["term_id"]: {"name": g.get("name", ""), "description": g.get("description", "")}
        for g in (data.get("glossary") or [])
        if g.get("term_id")
    }

    return {
        "item_id": item_id,
        "name": name,
        "description": data.get("description", ""),
        "affinities": data.get("affinities") or [],
        "main_skill_name": data.get("main_skill_name", ""),
        "main_skill_effect": data.get("main_skill_effect", ""),
        "upgrade_ranks": data.get("upgrade_ranks") or [],
        "slots": slots,
        "glossary": glossary,
    }


def import_crawler_spirits(items_data: list[dict]) -> list[dict]:
    return [import_crawler_spirit(item) for item in items_data if item.get("name")]
