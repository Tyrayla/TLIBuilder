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
import warnings
from collections import Counter as _Counter

from engine.modifier_lines import line_text, slim, slim_checked

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


# Dance of the Deep (Selena's second hero trait) is the ONLY hero_trait entry using a tree-allocation
# schema (allocation_mode:"tree" + tree_root_id + tree_nodes[column/row/x/y] + tree_connections edges)
# instead of the generic advanced_traits/group_id/is_pick_one_from_two schema every other trait uses.
# That layout is OWNER HAND-AUTHORED (owner-confirmed 2026-07-30, not sourced from TLIDB) and is restored
# here byte-for-byte from main's pre-regression _hero_traits.json - node_ids/column/row/x/y/edges are
# NEVER re-derived. Only the CONTENT (effects text, icon_url) is refreshed, from this season's live
# recrawl - keyed onto the fixed layout by the raw crawler node name, same as every other trait's
# advanced nodes (see `advanced_traits` below, which this reuses rather than re-deriving parsing logic).
_DANCE_OF_THE_DEEP_TREE_ROOT = "dance_of_the_deep"
_DANCE_OF_THE_DEEP_LAYOUT = [
    # (node_id, raw crawler node name to match against `advanced_traits`, column, row, x, y)
    ("silencing_severance", "Silencing Severance", 1, 1, 0.72, 0.27),
    ("drenched_hem", "Drenched Hem", 1, 2, 0.87, 0.52),
    ("the_paradise", "The Paradise I Curse", 3, 1, 0.28, 0.27),
    ("the_cycle", "The Cycle I Resist", 3, 2, 0.13, 0.52),
    ("crimson_endless_dance", "Crimson Endless Dance", 5, 1, 0.67, 0.6),
    ("dreambreakers_gyre", "Dreambreaker's Gyre", 7, 1, 0.5, 0.36),
    ("layered_hem", "Layered Hem", 7, 2, 0.38, 0.6),
    ("lonely_ensemble", "Lonely Ensemble", 7, 3, 0.5, 0.82),
]
_DANCE_OF_THE_DEEP_CONNECTIONS = [
    (_DANCE_OF_THE_DEEP_TREE_ROOT, "silencing_severance"),
    ("silencing_severance", "drenched_hem"),
    (_DANCE_OF_THE_DEEP_TREE_ROOT, "the_paradise"),
    ("the_paradise", "the_cycle"),
    (_DANCE_OF_THE_DEEP_TREE_ROOT, "crimson_endless_dance"),
    (_DANCE_OF_THE_DEEP_TREE_ROOT, "dreambreakers_gyre"),
    ("dreambreakers_gyre", "layered_hem"),
    ("layered_hem", "lonely_ensemble"),
]


def _dance_of_the_deep_hub_effects(levels: list[dict], am_effects: list[dict]) -> list[str]:
    """Collapse the 5 base-trait level lines into ONE tiered line (same `(a/b/c/d/e)` syntax as every
    other collapsed node), plus the Artificial Moon line as a second entry - mirrors main's hub-node
    shape exactly."""
    level_texts = [line_text(e) for lv in levels for e in lv.get("effects", [])]
    hub_effects = list(_collapse_tiers(level_texts))
    if am_effects:
        hub_effects.append(line_text(am_effects[0]))
    return hub_effects


def _dance_of_the_deep_tree_fields(advanced_traits: list[dict], levels: list[dict],
                                    am_effects: list[dict], variant_name: str, icon_url: str) -> dict | None:
    """allocation_mode/tree_root_id/tree_nodes/tree_connections for Dance of the Deep - hand-authored
    layout above, content pulled from `advanced_traits` (already collapsed via `_adv_effects`).
    Returns None (caller falls back to the generic advanced_traits schema) unless every hand-authored
    node name is actually present in this data - guards against a synthetic/degenerate fixture that
    happens to slug to trait_id "dance_of_the_deep" (e.g. a minimal regression fixture for an unrelated
    bug) being force-fit into a tree with missing nodes."""
    by_name = {a["name"]: a for a in advanced_traits}
    missing = [name for _, name, *_ in _DANCE_OF_THE_DEEP_LAYOUT if name not in by_name]
    if missing:
        # Loud, not silent: this fallback reproduces the exact flat-list regression this fix exists
        # to fix, so a future recrawl renaming/dropping one of the 8 hand-authored node names must
        # surface here rather than silently degrading to the generic advanced_traits schema again.
        warnings.warn(
            f"hero_trait_importer: dance_of_the_deep tree layout missing node name(s) {missing!r} in "
            f"this data - falling back to the flat advanced_traits schema instead of allocation_mode:'tree'",
            stacklevel=2,
        )
        return None
    nodes = [{
        "node_id": _DANCE_OF_THE_DEEP_TREE_ROOT,
        "name": variant_name,
        "column": 4, "row": 0, "x": 0.5, "y": 0.1,
        "effects": _dance_of_the_deep_hub_effects(levels, am_effects),
        "icon_url": icon_url or None,
    }]
    for node_id, name, column, row, x, y in _DANCE_OF_THE_DEEP_LAYOUT:
        matched = by_name[name]   # guaranteed present — every name was checked above
        nodes.append({
            "node_id": node_id,
            "name": matched["name"],
            "column": column, "row": row, "x": x, "y": y,
            "effects": [line_text(e) for e in matched["effects"]],
            "icon_url": matched.get("icon_url") or None,
        })
    return {
        "allocation_mode": "tree",
        "tree_root_id": _DANCE_OF_THE_DEEP_TREE_ROOT,
        "tree_nodes": nodes,
        "tree_connections": [{"from": f, "to": t} for f, t in _DANCE_OF_THE_DEEP_CONNECTIONS],
    }


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

    # Extract hero from base trait icon_url. `icon_url` may be JSON `null` (not just absent) for
    # entities tlidb hasn't backfilled yet at season launch — `.get(..., "")` only covers the
    # missing-key case, so null-coalesce explicitly. A missing/null icon degrades to no hero-from-
    # icon rather than crashing the whole import.
    icon_url = base.get("icon_url") or ""
    hero_m = _HERO_RE.search(icon_url)
    hero = hero_m.group(1) if hero_m else ""

    # Build levels; extract Artificial Moon text when found. Stored effects are slim modifier-line
    # dicts; the AM split CHANGES the wording, so both halves become uuid-less lines (carry rule).
    am_effects: list[dict] = []
    levels: list[dict] = []
    for lv in (base.get("levels") or []):
        raw_desc = lv.get("description", "")
        desc = line_text(raw_desc)
        am_m = _AM_RE.search(desc)
        if am_m and not am_effects:
            am_effects = [slim(am_m.group(0))]
            desc = desc[: am_m.start()].rstrip()
            effect = slim(desc) if desc else None            # truncated wording → uuid-less
        else:
            effect = slim(raw_desc) if desc else None        # unsplit line → ids carry
        levels.append({
            "level": lv.get("level", 0),
            "effects": [effect] if effect else [],
            "unlock_level": 1,
        })

    # Advanced-node effects: nodes with a per-level `levels` array carry their text there (their top-level
    # `description` is null); others use `description`. Per-level descriptions are COLLAPSED into a single line
    # using the `(a/b/c/d/e)` tier syntax the resolvers already understand (resolveLevel in the UI,
    # _expandTraitTier in the engine), so the tooltip/engine pick the selected rank instead of listing all tiers.
    def _adv_effects(t: dict) -> list[dict]:
        lv = t.get("levels")
        if lv:
            lines = [e.get("description") for e in lv if line_text(e.get("description")).strip()]
            collapsed = _collapse_tiers([line_text(d) for d in lines])
            if not collapsed:
                return []
            # Tier collapse is value-only when tiers differ only in numbers → ids carry from the first
            # tier line; slim_checked degrades to uuid-less if the tiers differed in wording.
            return [slim_checked(lines[0], collapsed[0])]
        d = t.get("description")
        return [slim(d)] if line_text(d).strip() else []

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
            "icon_url": t.get("icon_url") or "",
        })

    glossary = {
        g["term_id"]: {"name": g.get("name", ""), "description": g.get("description", "")}
        for g in (data.get("glossary") or [])
        if g.get("term_id")
    }

    result = {
        "trait_id": trait_id,
        "hero": hero,
        "uuid": data.get("uuid"),
        "variant_name": name,
        "description": "",
        "icon_url": icon_url,   # base-trait icon; UI pairs on its basename to a bundled hero_trait webp
        "levels": levels,
        "artificial_moon": {"description": "", "effects": am_effects},
        "ingredients": _clean_ingredients(data),
        "max_level": data.get("max_level"),
        "glossary": glossary,
    }
    tree_fields = (
        _dance_of_the_deep_tree_fields(advanced_traits, levels, am_effects, name, icon_url)
        if trait_id == _DANCE_OF_THE_DEEP_TREE_ROOT else None
    )
    if tree_fields is not None:
        result.update(tree_fields)
    else:
        result["advanced_traits"] = advanced_traits
    return result


def import_crawler_hero_traits(items_data: list[dict]) -> list[dict]:
    return [import_crawler_hero_trait(item) for item in items_data if item.get("name")]
