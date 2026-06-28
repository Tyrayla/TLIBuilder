"""
Imports hero trait JSON files (one file per trait variant) into a season-stored
_hero_traits.json.

Fields kept per trait:
  trait_id        — unique identifier (e.g. "bing_blast_nova")
  hero            — hero name (e.g. "Bing")
  variant_name    — trait variant display name (e.g. "Blast Nova")
  description     — flavor/mechanic description
  levels          — list of 5 base-trait level objects:
                    { level, effects: [...], unlock_level }
  artificial_moon — hero-specific moon mechanic: { description, effects: [...] }
  advanced_traits — list of advanced trait objects:
                    { name, unlock_level, is_pick_one_from_two, effects: [...] }

Fields discarded: base_skill, status, version, atomic_links (within advanced_traits)
"""

_TRAIT_KEEP = {"trait_id", "hero", "variant_name", "description", "icon_url", "levels",
               "artificial_moon", "advanced_traits"}

_LEVEL_KEEP = {"level", "effects", "unlock_level"}

_ADVANCED_KEEP = {"name", "unlock_level", "is_pick_one_from_two", "effects", "icon_url"}


def _clean_level(raw: dict) -> dict:
    cleaned = {k: v for k, v in raw.items() if k in _LEVEL_KEEP}
    cleaned.setdefault("level", 0)
    cleaned.setdefault("effects", [])
    cleaned.setdefault("unlock_level", 1)
    return cleaned


def _clean_advanced_trait(raw: dict) -> dict:
    cleaned = {k: v for k, v in raw.items() if k in _ADVANCED_KEEP}
    cleaned.setdefault("name", "")
    cleaned.setdefault("unlock_level", 0)
    cleaned.setdefault("is_pick_one_from_two", False)
    cleaned.setdefault("effects", [])
    return cleaned


def clean_hero_trait(raw: dict) -> dict:
    """Strip unwanted fields from a raw hero trait file."""
    cleaned = {k: v for k, v in raw.items() if k in _TRAIT_KEEP}

    cleaned.setdefault("trait_id", "")
    cleaned.setdefault("hero", "")
    cleaned.setdefault("variant_name", "")
    cleaned.setdefault("description", "")

    cleaned["levels"] = [
        _clean_level(lv)
        for lv in (cleaned.get("levels") or [])
        if isinstance(lv, dict)
    ]

    am = cleaned.get("artificial_moon")
    if isinstance(am, dict):
        cleaned["artificial_moon"] = {
            "description": am.get("description", ""),
            "effects": am.get("effects") or [],
        }
    else:
        cleaned["artificial_moon"] = {"description": "", "effects": []}

    cleaned["advanced_traits"] = [
        _clean_advanced_trait(at)
        for at in (cleaned.get("advanced_traits") or [])
        if isinstance(at, dict)
    ]

    return cleaned


def parse_hero_trait_file(data: dict) -> dict:
    """
    Parse a single hero trait JSON file and return a cleaned trait dict.
    Raises ValueError if the file is not a valid hero trait (missing trait_id).
    """
    if not isinstance(data, dict):
        raise ValueError("hero trait file must be a JSON object")
    trait = clean_hero_trait(data)
    if not trait["trait_id"]:
        raise ValueError("hero trait file missing required field 'trait_id'")
    return trait


def merge_hero_traits(existing: list[dict], incoming: dict) -> list[dict]:
    """
    Merge one incoming trait into the existing list, deduplicating by trait_id.
    The incoming entry overwrites any existing entry with the same trait_id.
    """
    by_id: dict[str, dict] = {t["trait_id"]: t for t in existing}
    by_id[incoming["trait_id"]] = incoming
    return list(by_id.values())


# ── Crawler-format importer ────────────────────────────────────────────────

import re as _re
from collections import Counter as _Counter

_HERO_RE = _re.compile(r"HeroTraits/([^/]+)/")
_AM_RE = _re.compile(r"Artificial Moon:\s*.+", _re.I)


def _collapse_tiers(descs: list[str]) -> list[str]:
    """Collapse a node's per-level descriptions into ONE rank-accurate line using `(a/b/c/d/e)` tier syntax that the
    resolvers already understand (resolveLevel in the UI, _expandTraitTier in the engine), so a per-rank node shows
    only its selected tier instead of dumping every tier. Single/empty -> as-is."""
    descs = [d.strip() for d in descs if d and d.strip()]
    if len(descs) <= 1:
        return descs
    toks = [d.split() for d in descs]            # whitespace-normalized tokens
    if len({len(t) for t in toks}) == 1:
        # Same token count across tiers: merge per column, grouping only the columns that differ.
        merged = [col[0] if all(c == col[0] for c in col) else "(" + "/".join(col) + ")" for col in zip(*toks)]
        return [" ".join(merged)]
    # Tiers differ in length (e.g. the 0% tier drops a clause): keep the common prefix/suffix and wrap the differing
    # middle of each tier in one slash-group (an empty middle, e.g. the 0% tier, becomes an empty slot).
    minlen = min(len(t) for t in toks)
    p = 0
    while p < minlen and all(t[p] == toks[0][p] for t in toks):
        p += 1
    s = 0
    while s < minlen - p and all(t[len(t) - 1 - s] == toks[0][-1 - s] for t in toks):
        s += 1
    prefix = toks[0][:p]
    suffix = toks[0][len(toks[0]) - s:] if s else []
    group = "(" + "/".join(" ".join(t[p:len(t) - s]) for t in toks) + ")"
    return [" ".join(prefix + [group] + suffix)]


# Hand-authored advanced-node grouping for traits whose in-game layout the count-based inference can't express —
# a GUARANTEED node and/or MULTIPLE pick groups at one level. Only Creative Genius needs this. Maps node name ->
# (group_role, group_id within its level, ordered top->bottom). Every other trait derives its grouping: a lone node
# at a level is "guaranteed"; 2+ nodes form a single "pick" group (group_id 0).
_TRAIT_STRUCTURE: dict[str, dict[str, tuple[str, int]]] = {
    "creative_genius": {
        "Inspiration Overflow": ("guaranteed", 0),                 # L45 top (always granted)
        "Super Sonic Protocol": ("pick", 1), "Over-Shield Module": ("pick", 1),   # L45 pick-of-2
        "Mind Domain": ("pick", 0), "Trouble Maker": ("pick", 0),                 # L60 top pick-of-2
        "Law of Ingenuity": ("pick", 1), "Ingenious Chaos Principle": ("pick", 1),
        "Auto-Ingenuity Program": ("pick", 1),                                    # L60 bottom pick-of-3
        "Brainstorm": ("pick", 0), "Flash of Brilliance": ("pick", 0),            # L75 top pick-of-2
        "Multi-Coupling Equation": ("pick", 1), "Hyper-Resonance Hypothesis": ("pick", 1),
        "Contingency Inspiration Delivery": ("pick", 1),                          # L75 bottom pick-of-3
    },
}


def _node_group(trait_id: str, name: str, level_count: int) -> tuple[str, int]:
    """(group_role, group_id) for an advanced node — hand-authored override if present, else derived."""
    override = _TRAIT_STRUCTURE.get(trait_id, {}).get(name)
    if override:
        return override
    return ("pick", 0) if level_count > 1 else ("guaranteed", 0)


def _clean_ingredients(data: dict) -> list[dict]:
    """Carry the crawler's `ingredients[]` (Licorice Note) into the season trait. Each entry is keyed by the granting
    `trait_name`; per-level entries (Basic/Special, which scale with a trait level) collapse each item's effect
    across levels into `(a/b/c/d/e)` tier syntax (like advanced nodes); inline-tier entries (Pungent) pass through.
    Output: [{trait_name, categories: [{category, items: [{name, effect}]}]}]."""
    out: list[dict] = []
    for ing in (data.get("ingredients") or []):
        tname = ing.get("trait_name", "")
        levels = ing.get("levels") or []
        if levels:
            # Per-level categories → gather each item's effect per level (in level order), then collapse to tiers.
            order: list[str] = []
            by_cat: dict[str, dict[str, list[str]]] = {}
            for lv in levels:
                for cat in (lv.get("categories") or []):
                    cname = cat.get("category", "")
                    if cname not in by_cat:
                        by_cat[cname] = {}
                        order.append(cname)
                    for it in (cat.get("items") or []):
                        by_cat[cname].setdefault(it.get("name", ""), []).append(it.get("effect", ""))
            categories = [{
                "category": cname,
                "items": [{"name": nm, "effect": (_collapse_tiers(effs) or [effs[-1] if effs else ""])[0]}
                          for nm, effs in by_cat[cname].items()],
            } for cname in order]
        else:
            categories = [{
                "category": c.get("category", ""),
                "items": [{"name": it.get("name", ""), "effect": it.get("effect", "")} for it in (c.get("items") or [])],
            } for c in (ing.get("categories") or [])]
        out.append({"trait_name": tname, "categories": categories})
    return out


def import_crawler_hero_trait(data: dict) -> dict:
    """Import a single crawler hero trait file (one JSON file per trait variant)."""
    name = data.get("name", "")
    trait_id = _re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    traits = data.get("traits") or []

    # Base trait = the required_level==1 entry; advanced = every level-45/60/75 node.
    # NOTE: some ADVANCED nodes also carry a per-level `levels` array (their tier scaling), so the base must be
    # detected by required_level, NOT by "has a levels field" — otherwise those advanced nodes get dropped.
    base = next((t for t in traits if t.get("required_level", 1) == 1), {})
    advanced_raw = [t for t in traits if t.get("required_level", 1) != 1]

    # Extract hero from base trait icon_url
    icon_url = base.get("icon_url", "")
    hero_m = _HERO_RE.search(icon_url)
    hero = hero_m.group(1) if hero_m else ""

    # Build levels; extract Artificial Moon text when found
    am_effects: list[str] = []
    levels: list[dict] = []
    for lv in (base.get("levels") or []):
        desc = lv.get("description", "")
        am_m = _AM_RE.search(desc)
        if am_m and not am_effects:
            am_effects = [am_m.group(0)]
            desc = desc[: am_m.start()].rstrip()
        levels.append({
            "level": lv.get("level", 0),
            "effects": [desc] if desc else [],
            "unlock_level": 1,
        })

    # Advanced-node effects: nodes with a per-level `levels` array carry their text there (their top-level
    # `description` is null); others use `description`. Per-level descriptions are COLLAPSED into a single line
    # using the `(a/b/c/d/e)` tier syntax the resolvers already understand (resolveLevel in the UI,
    # _expandTraitTier in the engine), so the tooltip/engine pick the selected rank instead of listing all tiers.
    def _adv_effects(t: dict) -> list[str]:
        lv = t.get("levels")
        if lv:
            return _collapse_tiers([e.get("description", "") for e in lv if e.get("description")])
        return [t["description"]] if t.get("description") else []

    # Count nodes per unlock level (drives is_pick_one_from_two + the derived grouping).
    level_counts = _Counter(t.get("required_level", 0) for t in advanced_raw)
    advanced_traits = []
    for t in advanced_raw:
        nm = t.get("name", "")
        ul = t.get("required_level", 0)
        role, gid = _node_group(trait_id, nm, level_counts[ul])
        advanced_traits.append({
            "name": nm,
            "unlock_level": ul,
            "is_pick_one_from_two": level_counts[ul] > 1,
            "group_role": role,   # "guaranteed" (always granted) | "pick" (choose 1 of the group)
            "group_id": gid,      # group within the level, top->bottom (0,1,…)
            "effects": _adv_effects(t),
            "icon_url": t.get("icon_url", ""),
        })

    glossary = {
        g["term_id"]: {"name": g.get("name", ""), "description": g.get("description", "")}
        for g in (data.get("glossary") or [])
        if g.get("term_id")
    }

    return {
        "trait_id": trait_id,
        "hero": hero,
        "variant_name": name,
        "description": "",
        "icon_url": icon_url,   # base-trait icon; UI pairs on its basename to a bundled hero_trait webp
        "levels": levels,
        "artificial_moon": {"description": "", "effects": am_effects},
        "advanced_traits": advanced_traits,
        "ingredients": _clean_ingredients(data),
        "max_level": data.get("max_level"),
        "glossary": glossary,
    }


def import_crawler_hero_traits(items_data: list[dict]) -> list[dict]:
    return [import_crawler_hero_trait(item) for item in items_data if item.get("name")]
