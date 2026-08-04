"""Bundle the raw data files the ENGINE reads, for the in-browser Pyodide worker to fetch + unpack.

Distinct from export_web_data.py (which emits the transformed UI catalogs): this is the server-side data the
compute path loads via open()/season_manager — the root config files + the active season's tree/skill/etc files.
Excludes data/images/ (icons load separately via the CDN) and data/builds/ (user data). Arcnames are relative to
the data root, so the worker unpacks it into its Pyodide FS data dir and the engine finds everything unchanged.

Output: <out>/engine-data.zip   (default <repo>/web-data/engine-data.zip)
Usage:  python backend/tools/export_engine_bundle.py [--out DIR]
"""
import argparse
import os
import sys
import zipfile

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import server  # noqa: E402

DATA = server._DATA_ROOT

# Files whose only readers on the web are unreachable. The six season files + help_db.json feed catalog
# endpoints the web client never calls — it intercepts those paths and serves the transformed JSON from the
# data CDN (client.ts STATIC_CATALOGS); shipping the raw files too was ~40% of the zip for nothing.
# node_type_filter_overrides.json is different: its only readers are /api/dev override endpoints (DevTools,
# desktop-only). NOTE: this list is safe only while STATIC_CATALOGS covers those endpoints — a future
# un-intercepted reader would degrade silently to empty (season_manager.load_* returns None on a missing
# file), so re-check here before de-listing a catalog. The engine itself never opens any of these.
_WEB_SKIP_ROOT = {"help_db.json", "node_type_filter_overrides.json"}
_WEB_SKIP_SEASON = {
    "_craft_base_types.json", "_craft_base_items.json", "_grafts.json",
    "_pact_spirits.json", "_hero_memories.json", "_legendary_gear_index.json",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(_BACKEND), "web-data"))
    args = ap.parse_args()

    season = server.season_manager.get_active_season()
    if not season:
        raise SystemExit("No active season — set one before exporting.")
    os.makedirs(args.out, exist_ok=True)
    zpath = os.path.join(args.out, "engine-data.zip")

    n = 0
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        # Root-level config the engine reads (json at the data root; skip dirs incl. images/ builds/ seasons/).
        for name in sorted(os.listdir(DATA)):
            p = os.path.join(DATA, name)
            if os.path.isfile(p) and name.endswith(".json") and name not in _WEB_SKIP_ROOT:
                z.write(p, name); n += 1
        # The active season's files (trees, _skills.json, _belt_blends.json, ...).
        sdir = os.path.join(DATA, "seasons", season)
        for name in sorted(os.listdir(sdir)):
            p = os.path.join(sdir, name)
            if os.path.isfile(p) and name not in _WEB_SKIP_SEASON:
                z.write(p, f"seasons/{season}/{name}"); n += 1

    size = os.path.getsize(zpath)
    print(f"engine-data.zip  season={season}  {n} files  {size / 1048576:.1f} MB (zip)  -> {zpath}")


if __name__ == "__main__":
    main()
