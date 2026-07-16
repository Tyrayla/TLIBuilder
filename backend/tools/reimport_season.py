"""Reimport a full season from the tlidb-scraper output directory — every entity type, in order.

Runs IN-PROCESS (no backend server needed): each step calls the same importer + season_manager save
the corresponding /api/dev/import-* endpoint uses, so the result is byte-identical to a manual
DevTools import, minus the server's in-memory caches (start the app fresh afterwards). Repeatable
per season; review the data/ git diff after running.

Usage (from backend/):
    python -m tools.reimport_season [--season SS12] [--crawl <scraper output dir>]
                                    [--only trees,gear,...] [--skip ...] [--list]

Steps (in import order): trees (incl. New God), gear, skills (full rebuild w/ dps_eligible
carry-over, via tools.rebuild_skills), traits, spirits, craft, grafts, blends, destiny, prism,
memories, revival, tower, filter (node_type_filter rebuild from the just-imported trees).
divinity_slate has no data importer (icons only) and is skipped by design.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys


def _load(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _files(crawl: str, sub: str) -> list[str]:
    return sorted(glob.glob(os.path.join(crawl, sub, "*.json")))


def _load_items(crawl: str, sub: str) -> list[dict]:
    return [_load(p) for p in _files(crawl, sub)]


# ── Steps ─────────────────────────────────────────────────────────────────────

def step_trees(season: str, crawl: str) -> str:
    """Mirrors /api/dev/import-crawler-tree (incl. the New God branch)."""
    from persistence import season_manager
    from tools.season_importer import import_crawler_tree, _effect_line

    trees_meta = _load(os.path.join(os.path.dirname(__file__), "..", "..", "data", "trees_meta.json"))
    imported, skipped, new_god = [], [], 0
    for path in _files(crawl, "talent_tree"):
        data = _load(path)
        tree_name = (data.get("name") or "").strip()
        if tree_name == "New God":
            talents = []
            for node in data.get("nodes", []):
                if node.get("type") != "core_talent" or not node.get("name"):
                    continue
                raw_name = node["name"]
                talents.append({
                    "name": raw_name,
                    "item_id": re.sub(r"[^a-z0-9]+", "_", raw_name.lower()).strip("_"),
                    "uuid": node.get("uuid"),
                    "effects": [_effect_line(e) for e in (node.get("effects") or [])],
                    "icon_url": node.get("icon_url", ""),
                    "note": "",
                })
            season_manager.save_new_god_talents(season, talents)
            new_god = len(talents)
            continue
        if tree_name not in trees_meta:
            skipped.append(tree_name or os.path.basename(path))
            continue
        tree_slug = tree_name.lower().replace(" ", "_")
        parsed = import_crawler_tree(data, tree_name)
        parsed["season"] = season
        season_manager.save_season_tree(season, tree_name, tree_slug, parsed)
        imported.append(tree_name)
    out = f"{len(imported)} trees, {new_god} New God talents"
    if skipped:
        out += f", SKIPPED: {skipped}"
    return out


def step_gear(season: str, crawl: str) -> str:
    from persistence import season_manager
    from tools.legendary_gear_importer import import_crawler_items
    items = import_crawler_items(_load_items(crawl, "legendary_gear"))
    season_manager.save_legendary_gear(season, {
        "season": season, "item_count": len(items), "items": items,
    })
    return f"{len(items)} items"


def step_skills(season: str, crawl: str) -> str:
    """Full rebuild with dps_eligible carry-over — the rebuild_skills semantics, not the merge endpoint."""
    from tools.rebuild_skills import build_skills
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = os.path.abspath(os.path.join(repo, "..", "data", "seasons", season, "_skills.json"))
    existing = _load(out) if os.path.exists(out) else {"skills": []}
    existing_by_id = {s["item_id"]: s for s in existing.get("skills", [])}
    skills, notes = build_skills(crawl, existing_by_id)
    payload = {"season": season, "skill_count": len(skills), "skills": skills}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    kept = [s["item_id"] for s in skills if "dps_eligible" in s]
    msg = f"{len(skills)} skills (was {len(existing_by_id)}), dps_eligible kept on {len(kept)}"
    if notes:
        msg += f", collisions: {notes}"
    return msg


def step_traits(season: str, crawl: str) -> str:
    from persistence import season_manager
    from tools.hero_trait_importer import import_crawler_hero_traits, merge_hero_traits
    items = import_crawler_hero_traits(_load_items(crawl, "hero_trait"))
    existing = season_manager.load_hero_traits(season, raw=True) or {"traits": []}
    merged: list[dict] = existing.get("traits", [])
    for item in items:
        merged = merge_hero_traits(merged, item)
    heroes = len({t["hero"] for t in merged if t.get("hero")})
    season_manager.save_hero_traits(season, {
        "season": season, "hero_count": heroes, "trait_count": len(merged), "traits": merged,
    })
    return f"{len(items)} imported, {len(merged)} total, {heroes} heroes"


def step_spirits(season: str, crawl: str) -> str:
    from persistence import season_manager
    from tools.pact_spirit_importer import import_crawler_spirits
    spirits = import_crawler_spirits(_load_items(crawl, "pactspirit"))
    season_manager.save_pact_spirits(season, {
        "season": season, "spirit_count": len(spirits), "spirits": spirits,
    })
    return f"{len(spirits)} spirits"


def step_craft(season: str, crawl: str) -> str:
    from persistence import season_manager
    from tools.craft_base_type_importer import import_crawler_craft_base_types
    base_types = import_crawler_craft_base_types(_load_items(crawl, "craft_base_type"))
    season_manager.save_craft_base_types(season, {
        "season": season, "type_count": len(base_types), "base_types": base_types,
    })
    season_manager.save_craft_base_items(season, {
        "season": season,
        "base_types": [{"item_id": bt["item_id"], "name": bt["name"], "base_items": bt["base_items"]}
                       for bt in base_types],
    })
    return f"{len(base_types)} base types"


def step_grafts(season: str, crawl: str) -> str:
    from persistence import season_manager
    from tools.graft_importer import import_crawler_grafts
    grafts = import_crawler_grafts(_load_items(crawl, "graft"))
    season_manager.save_grafts(season, {
        "season": season, "graft_count": len(grafts), "grafts": grafts,
    })
    return f"{len(grafts)} grafts"


def step_blends(season: str, crawl: str) -> str:
    from persistence import season_manager
    from tools.belt_blend_importer import import_crawler_belt_blends
    result = import_crawler_belt_blends(_load(os.path.join(crawl, "blending_rituals", "blending_rituals.json")))
    season_manager.save_belt_blends(season, {"season": season, **result})
    return f"{result['blend_count']} blends"


def _singleton(season: str, crawl: str, sub: str, importer_name: str, save_name: str, count_key: str) -> str:
    from persistence import season_manager
    from tools import singleton_importer
    parsed = getattr(singleton_importer, importer_name)(_load(os.path.join(crawl, sub, f"{sub}.json")), season)
    getattr(season_manager, save_name)(season, parsed)
    return f"{parsed[count_key]}"


def step_destiny(season, crawl):  return _singleton(season, crawl, "destiny", "import_destiny", "save_destiny", "item_count")
def step_prism(season, crawl):    return _singleton(season, crawl, "ethereal_prism", "import_ethereal_prism", "save_ethereal_prism", "item_count")
def step_memories(season, crawl): return _singleton(season, crawl, "hero_memories", "import_hero_memories", "save_hero_memories", "affix_count")
def step_revival(season, crawl):  return _singleton(season, crawl, "memory_revival", "import_memory_revival", "save_memory_revival", "affix_count")
def step_tower(season, crawl):    return _singleton(season, crawl, "tower_sequence", "import_tower_sequence", "save_tower_sequence", "entry_count")


def step_filter(season: str, crawl: str) -> str:
    """Mirrors /api/dev/rebuild-node-type-filter: tree-driven build over the runtime (string) view.

    `data/node_type_filter.json` is a single GLOBAL file the engine reads for whatever season is
    currently active (`data/seasons/.active`) — it carries no season namespace of its own. Rebuilding
    it from a season that ISN'T the active one would silently clobber the live engine's stat-matching
    data with a different season's node texts. Guard: only rebuild when `season` is the active season;
    otherwise skip (the filter for `season` gets built for real once `.active` flips to it — normally
    via /api/dev/rebuild-node-type-filter or by re-running this step after flipping .active).
    """
    from persistence import season_manager
    from tools.node_type_filter_builder import build_filter, build_node_recipes, save_filter
    active = season_manager.get_active_season()
    if active is not None and active != season:
        return f"SKIPPED — active season is {active!r}, not {season!r} (filter left untouched)"
    season_trees = season_manager.load_all_season_trees(season)
    if not season_trees:
        raise RuntimeError(f"no season trees for {season} — run the trees step first")
    result = build_filter(season_trees)
    result["node_recipes"] = build_node_recipes(season_trees)
    save_filter(result)
    m = result["_meta"]
    return (f"matched={m['matched']} ambiguous={m['ambiguous']} unmatched={m['unmatched']} "
            f"conditional={m['conditional']} node_recipes={len(result['node_recipes'])}")


_STEPS: list[tuple[str, object]] = [
    ("trees", step_trees), ("gear", step_gear), ("skills", step_skills), ("traits", step_traits),
    ("spirits", step_spirits), ("craft", step_craft), ("grafts", step_grafts), ("blends", step_blends),
    ("destiny", step_destiny), ("prism", step_prism), ("memories", step_memories),
    ("revival", step_revival), ("tower", step_tower), ("filter", step_filter),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default="SS12")
    ap.add_argument("--crawl", default="C:/Users/tyray/Documents/tlidb-scraper/output/SS12")
    ap.add_argument("--only", default="", help="comma-separated step names to run")
    ap.add_argument("--skip", default="", help="comma-separated step names to skip")
    ap.add_argument("--list", action="store_true", help="list steps and exit")
    args = ap.parse_args()

    if args.list:
        print("steps:", ", ".join(name for name, _ in _STEPS))
        return 0
    if not os.path.isdir(args.crawl):
        print(f"crawl dir not found: {args.crawl}")
        return 1

    only = {s.strip() for s in args.only.split(",") if s.strip()}
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    for name, fn in _STEPS:
        if (only and name not in only) or name in skip:
            print(f"[skip] {name}")
            continue
        try:
            print(f"[{name}] {fn(args.season, args.crawl)}")
        except Exception as e:
            print(f"[{name}] FAILED: {e}")
            return 1
    print("done — review `git diff data/` and restart the backend (process caches are stale).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
