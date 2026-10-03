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


def _write_zip(entries: list[tuple[str, str]], zpath: str) -> None:
    """Write (source path, arcname) entries in the given order, byte-for-byte reproducibly.

    z.write() would stamp each entry with the file's mtime and the OS's attributes, so identical data produced a
    different zip on every build (and on Windows vs Linux): data deploys re-uploaded it and the post-deploy check
    couldn't tell a current CDN from a stale one. Every entry gets the same fixed timestamp and attributes instead.
    """
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path, arcname in entries:
            info = zipfile.ZipInfo(arcname, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3                      # "made on Unix" regardless of the build OS
            info.external_attr = 0o100644 << 16         # regular file, rw-r--r--
            with open(path, "rb") as f:
                z.writestr(info, f.read(), compresslevel=9)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(_BACKEND), "web-data"))
    args = ap.parse_args()

    season = server.season_manager.get_active_season()
    if not season:
        raise SystemExit("No active season — set one before exporting.")
    os.makedirs(args.out, exist_ok=True)
    zpath = os.path.join(args.out, "engine-data.zip")

    entries: list[tuple[str, str]] = []
    # Root-level config the engine reads (json at the data root; skip dirs incl. images/ builds/ seasons/).
    for name in sorted(os.listdir(DATA)):
        p = os.path.join(DATA, name)
        if os.path.isfile(p) and name.endswith(".json") and name not in _WEB_SKIP_ROOT:
            entries.append((p, name))
    # The active season's files (trees, _skills.json, _belt_blends.json, ...).
    sdir = os.path.join(DATA, "seasons", season)
    for name in sorted(os.listdir(sdir)):
        p = os.path.join(sdir, name)
        if os.path.isfile(p) and name not in _WEB_SKIP_SEASON:
            entries.append((p, f"seasons/{season}/{name}"))
    _write_zip(entries, zpath)

    size = os.path.getsize(zpath)
    print(f"engine-data.zip  season={season}  {len(entries)} files  {size / 1048576:.1f} MB (zip)  -> {zpath}")


if __name__ == "__main__":
    main()
