import re

_VALID_RINGS = {"inner", "mid", "outer"}


def import_crawler_spirit(data: dict) -> dict:
    name = data.get("name", "")
    item_id = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")

    # Normalize each slot: ring → a known ring (default "outer"); effect → ALWAYS a list of atomic stat
    # lines. The reworked crawler emits effect as a list (one stat per entry); coerce a legacy string into
    # a single-element list so the season format is uniform and consumers can always iterate it.
    slots = []
    for s in (data.get("slots") or []):
        ring = s.get("ring", "")
        eff = s.get("effect", [])
        if isinstance(eff, str):
            eff = [eff] if eff.strip() else []
        slots.append({
            "name": s.get("name", ""),
            "effect": eff,
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
