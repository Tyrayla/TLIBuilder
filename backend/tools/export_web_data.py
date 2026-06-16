"""Export the season-global reference catalogs as static JSON for the web (CDN) build.

Runs the SAME endpoint logic the desktop app already consumes (server.py's catalog handlers), so the static
files are byte-for-byte what the app expects — the web build fetches these from a CDN instead of hitting the
Python backend, removing ~16 MB + the catalog endpoints from the server (Phase 1 of the web-hosting plan).

Output layout (cache-busted by season):
    <out>/manifest.json                  -> {"season": "SS12"}
    <out>/<season>/<catalog>.json        -> e.g. SS12/skills.json

Usage:  python backend/tools/export_web_data.py [--out DIR]   (default: <repo>/web-data)
"""
import argparse
import json
import os
import shutil
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import server  # noqa: E402  (path set above)

# endpoint handler -> output filename (matches the names the web client will request)
CATALOGS = {
    "conditions": server.get_conditions,
    "skills": server.get_skills,
    "hero_traits": server.get_hero_traits,
    "legendary_gear_index": server.get_legendary_gear_index,
    "legendary_gear": server.get_legendary_gear,
    "pact_spirits": server.get_pact_spirits,
    "craft_base_types": server.get_craft_base_types,
    "craft_base_items": server.get_craft_base_items,
    "grafts": server.get_grafts,
    "hero_memories": server.get_hero_memories,
}


def _jsonable(v):
    return v.model_dump() if hasattr(v, "model_dump") else v


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(_BACKEND), "web-data"))
    args = ap.parse_args()

    season = server.season_manager.get_active_season()
    if not season:
        raise SystemExit("No active season — set one before exporting.")
    season_dir = os.path.join(args.out, season)
    os.makedirs(season_dir, exist_ok=True)

    total = 0
    print(f"Exporting season {season} -> {season_dir}")
    for name, fn in CATALOGS.items():
        data = _jsonable(fn())
        path = os.path.join(season_dir, f"{name}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        size = os.path.getsize(path)
        total += size
        print(f"  {name:22s} {size / 1024:9.1f} KB")

    # Entity icons (served via ICON_BASE on web). Copy the bundled icons dir to <out>/icons so the CDN serves
    # /icons/<category>/<file>.webp, matching iconUrl(). ~10 MB of webp; cached per-icon on demand.
    icons_src = os.path.join(server._DATA_ROOT, "images", "icons")
    if os.path.isdir(icons_src):
        icons_dst = os.path.join(args.out, "icons")
        shutil.rmtree(icons_dst, ignore_errors=True)
        shutil.copytree(icons_src, icons_dst)
        n_icons = sum(len(fs) for _, _, fs in os.walk(icons_dst))
        print(f"  icons                  {n_icons} files copied")

    with open(os.path.join(args.out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"season": season}, f)

    # Cloudflare Pages _headers: allow cross-origin fetch (the web app / localhost reads this data domain) and
    # cache for an hour (season-in-path means a new season is a new URL; re-exports propagate within the hour).
    with open(os.path.join(args.out, "_headers"), "w", encoding="utf-8", newline="\n") as f:
        f.write("/*\n  Access-Control-Allow-Origin: *\n  Cache-Control: public, max-age=3600\n")

    print(f"  {'TOTAL':22s} {total / 1024:9.1f} KB  (~{total / 1048576:.1f} MB raw; CDN gzip/brotli -> ~1 MB on the wire)")
    print(f"  manifest.json -> {{'season': '{season}'}}")


if __name__ == "__main__":
    main()
