"""
Build folders — a manifest (folders.json) living alongside the saved build .txt files, tracking a
client-authored folder tree, per-build folder assignment, and manual display order.

Deliberately self-contained (does NOT import builds_manager) so builds_manager can import THIS module
(to prune folder state on build delete) without a circular import. Duplicates the small bits of
builds_manager's convention it needs: the safe-id regex and the per-call persist-dir resolution.

Manifest shape (all four keys always present on load/save):
    {
      "folders": [{"id": "<folderId>", "name": "<name>", "parentId": "<folderId>" | null}, ...],
      "assignments": {"<buildId>": "<folderId>"},
      "order": {"root": ["<buildId>", ...], "<folderId>": [...]},
      "folderOrder": {"root": ["<folderId>", ...], "<folderId>": [...]},
    }

Folder ids are client-generated, must match _SAFE_ID, and must never be the literal "root" (reserved
key meaning top level).
"""
import json
import os
import re

_SAFE_ID = re.compile(r'^[A-Za-z0-9_-]+$')
_ROOT = 'root'
_MANIFEST_FILENAME = 'folders.json'


def _dir() -> str:
    # Same builds directory builds_manager._dir() resolves to (folders.json lives alongside the build
    # .txt files). Evaluated per-call, not at import, for the same reason builds_manager does: the web
    # worker repoints TLI_PERSIST_DIR after this module may already be imported.
    root = os.environ.get('TLI_PERSIST_DIR') or os.environ.get('TLI_DATA_DIR') or os.path.normpath(
        os.path.join(os.path.dirname(__file__), '..', '..', 'data'))
    return os.path.normpath(os.path.join(root, 'builds'))


def _manifest_path() -> str:
    return os.path.join(_dir(), _MANIFEST_FILENAME)


def _build_file_path(build_id: str) -> str | None:
    """Returns the path a build .txt file would live at, or None if build_id is not a safe filename
    component (an unsafe id can never correspond to a real saved build)."""
    if not isinstance(build_id, str) or not _SAFE_ID.fullmatch(build_id):
        return None
    return os.path.join(_dir(), f"{build_id}.txt")


def _build_exists(build_id: str) -> bool:
    path = _build_file_path(build_id)
    return path is not None and os.path.isfile(path)


def _empty_manifest() -> dict:
    return {"folders": [], "assignments": {}, "order": {}, "folderOrder": {}}


def _dedupe_preserve_order(seq: list[str]) -> list[str]:
    """First-occurrence-wins de-dup, so a payload like ["b1", "b1"] never reaches the renderer (which
    keys list items by id — a duplicate produces duplicate React keys)."""
    seen: set[str] = set()
    out: list[str] = []
    for item in seq:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _best_effort_clean(raw: dict) -> dict:
    """Non-raising structural clean used by load(). A hand-edited/corrupted folders.json must never
    reach the renderer with a parent cycle, a duplicate folder id, or another structurally poisonous
    shape — but load() also must never 500 or hang the renderer over it. Unlike _validate_and_clean
    (used by save(), which raises on these same problems so the caller can 400), this always returns a
    structurally sound manifest: whatever can't be salvaged is dropped, never errored. Degrades to
    "some folders fall back to root, or disappear if they were themselves part of a cycle" — never
    silently keeps a cycle or a dangling reference."""
    folders_in = raw.get('folders')
    if not isinstance(folders_in, list):
        folders_in = []
    assignments_in = raw.get('assignments')
    if not isinstance(assignments_in, dict):
        assignments_in = {}
    order_in = raw.get('order')
    if not isinstance(order_in, dict):
        order_in = {}
    folder_order_in = raw.get('folderOrder')
    if not isinstance(folder_order_in, dict):
        folder_order_in = {}

    # -- folders: keep the first occurrence of each well-shaped id; drop anything structurally broken
    # outright (bad shape, unsafe/duplicate/"root" id, empty name) rather than trying to salvage it --
    seen_ids: set[str] = set()
    candidate_folders: list[dict] = []
    for entry in folders_in:
        if not isinstance(entry, dict):
            continue
        fid = entry.get('id')
        name = entry.get('name')
        parent_id = entry.get('parentId')

        if not isinstance(fid, str) or not _SAFE_ID.fullmatch(fid) or fid == _ROOT:
            continue
        if fid in seen_ids:
            continue  # duplicate id — first occurrence wins, later ones are dropped
        if not isinstance(name, str) or not name.strip():
            continue
        if parent_id is not None and not isinstance(parent_id, str):
            parent_id = None  # malformed parentId degrades to root rather than dropping the folder

        seen_ids.add(fid)
        candidate_folders.append({"id": fid, "name": name.strip(), "parentId": parent_id})

    # A parentId referencing an id that didn't survive the pass above is unresolvable — fall back to root.
    live_ids = {f['id'] for f in candidate_folders}
    for f in candidate_folders:
        if f['parentId'] is not None and f['parentId'] not in live_ids:
            f['parentId'] = None

    # Cycle detection: any folder whose parent chain revisits itself is part of a cycle and gets
    # dropped entirely (nulling just one member's parentId would arbitrarily pick which folder "wins";
    # dropping the whole cycle is the unambiguous safe choice). A folder outside the cycle that merely
    # pointed INTO it is not itself dropped — its parentId gets re-rooted below instead.
    parent_map = {f['id']: f['parentId'] for f in candidate_folders}
    in_cycle: set[str] = set()
    for fid in parent_map:
        chain: list[str] = []
        cur = fid
        while cur is not None:
            if cur in chain:
                in_cycle.update(chain[chain.index(cur):])
                break
            chain.append(cur)
            cur = parent_map.get(cur)

    cleaned_folders = [f for f in candidate_folders if f['id'] not in in_cycle]
    live_ids -= in_cycle
    for f in cleaned_folders:
        if f['parentId'] is not None and f['parentId'] not in live_ids:
            f['parentId'] = None

    # -- assignments / order / folderOrder: same dangling-reference pruning + array dedup as save() --
    cleaned_assignments: dict[str, str] = {}
    for build_id, folder_id in assignments_in.items():
        if not isinstance(build_id, str) or not isinstance(folder_id, str):
            continue
        if folder_id not in live_ids:
            continue
        if not _build_exists(build_id):
            continue
        cleaned_assignments[build_id] = folder_id

    cleaned_order: dict[str, list[str]] = {}
    for key, ids in order_in.items():
        if key != _ROOT and key not in live_ids:
            continue
        if not isinstance(ids, list):
            continue
        cleaned_order[key] = _dedupe_preserve_order(
            [bid for bid in ids if isinstance(bid, str) and _build_exists(bid)])

    cleaned_folder_order: dict[str, list[str]] = {}
    for key, ids in folder_order_in.items():
        if key != _ROOT and key not in live_ids:
            continue
        if not isinstance(ids, list):
            continue
        cleaned_folder_order[key] = _dedupe_preserve_order(
            [f for f in ids if isinstance(f, str) and f in live_ids])

    return {
        "folders": cleaned_folders,
        "assignments": cleaned_assignments,
        "order": cleaned_order,
        "folderOrder": cleaned_folder_order,
    }


def load() -> dict:
    path = _manifest_path()
    if not os.path.isfile(path):
        return _empty_manifest()
    try:
        with open(path, encoding='utf-8') as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return _empty_manifest()
    if not isinstance(raw, dict):
        return _empty_manifest()
    return _best_effort_clean(raw)


def _validate_and_clean(manifest: dict) -> dict:
    """Validate structural invariants (raises ValueError with a human message on failure — the caller
    maps that to HTTP 400) and silently clean stale references (dangling assignments/order entries)."""
    folders_in = manifest.get('folders')
    if not isinstance(folders_in, list):
        folders_in = []
    assignments_in = manifest.get('assignments')
    if not isinstance(assignments_in, dict):
        assignments_in = {}
    order_in = manifest.get('order')
    if not isinstance(order_in, dict):
        order_in = {}
    folder_order_in = manifest.get('folderOrder')
    if not isinstance(folder_order_in, dict):
        folder_order_in = {}

    # -- folders: ids safe + unique + not "root", names non-empty, parentId shape --
    seen_ids: set[str] = set()
    cleaned_folders: list[dict] = []
    parent_map: dict[str, str | None] = {}
    for entry in folders_in:
        if not isinstance(entry, dict):
            raise ValueError("Each folder entry must be an object")
        fid = entry.get('id')
        name = entry.get('name')
        parent_id = entry.get('parentId')

        if not isinstance(fid, str) or not _SAFE_ID.fullmatch(fid):
            raise ValueError(f"Invalid folder id: {fid!r}")
        if fid == _ROOT:
            raise ValueError('Folder id "root" is reserved')
        if fid in seen_ids:
            raise ValueError(f"Duplicate folder id: {fid!r}")
        if parent_id is not None and not isinstance(parent_id, str):
            raise ValueError(f"Folder {fid!r} has an invalid parentId")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Folder {fid!r} must have a non-empty name")

        seen_ids.add(fid)
        parent_map[fid] = parent_id
        cleaned_folders.append({"id": fid, "name": name.strip(), "parentId": parent_id})

    # parentId must reference a folder id present in this same payload
    for entry in cleaned_folders:
        pid = entry['parentId']
        if pid is not None and pid not in seen_ids:
            raise ValueError(f"Folder {entry['id']!r} has unknown parentId {pid!r}")

    # cycle detection (walk each folder's parent chain)
    for fid in parent_map:
        visited: set[str] = set()
        cur = fid
        while cur is not None:
            if cur in visited:
                raise ValueError(f"Folder parent cycle detected at {fid!r}")
            visited.add(cur)
            cur = parent_map.get(cur)

    # -- assignments: drop entries whose folder id or build file doesn't exist --
    cleaned_assignments: dict[str, str] = {}
    for build_id, folder_id in assignments_in.items():
        if not isinstance(build_id, str) or not isinstance(folder_id, str):
            continue
        if folder_id not in seen_ids:
            continue
        if not _build_exists(build_id):
            continue
        cleaned_assignments[build_id] = folder_id

    # -- order: keys must be "root" or a live folder id; prune array entries to live build ids and
    # dedupe (first occurrence wins) so a repeated id never round-trips into duplicate React keys --
    cleaned_order: dict[str, list[str]] = {}
    for key, ids in order_in.items():
        if key != _ROOT and key not in seen_ids:
            continue
        if not isinstance(ids, list):
            continue
        cleaned_order[key] = _dedupe_preserve_order(
            [bid for bid in ids if isinstance(bid, str) and _build_exists(bid)])

    # -- folderOrder: keys must be "root" or a live folder id; prune + dedupe array entries the same way --
    cleaned_folder_order: dict[str, list[str]] = {}
    for key, ids in folder_order_in.items():
        if key != _ROOT and key not in seen_ids:
            continue
        if not isinstance(ids, list):
            continue
        cleaned_folder_order[key] = _dedupe_preserve_order(
            [f for f in ids if isinstance(f, str) and f in seen_ids])

    return {
        "folders": cleaned_folders,
        "assignments": cleaned_assignments,
        "order": cleaned_order,
        "folderOrder": cleaned_folder_order,
    }


def _atomic_write(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, separators=(',', ':'))
    os.replace(tmp_path, path)


def save(manifest: dict) -> dict:
    if not isinstance(manifest, dict):
        raise ValueError("Manifest must be an object")
    cleaned = _validate_and_clean(manifest)
    _atomic_write(_manifest_path(), cleaned)
    return cleaned


def remove_build(build_id: str) -> None:
    """Drop build_id's folder assignment and prune it from every order array. No-op if the manifest
    file doesn't exist yet (nothing to prune) — intentionally does not re-run full validation, so a
    delete never fails because of unrelated manifest drift."""
    path = _manifest_path()
    if not os.path.isfile(path):
        return
    try:
        with open(path, encoding='utf-8') as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return
    if not isinstance(raw, dict):
        return

    changed = False
    assignments = raw.get('assignments')
    if isinstance(assignments, dict) and build_id in assignments:
        del assignments[build_id]
        changed = True

    order = raw.get('order')
    if isinstance(order, dict):
        for key, ids in list(order.items()):
            if isinstance(ids, list) and build_id in ids:
                order[key] = [bid for bid in ids if bid != build_id]
                changed = True

    if not changed:
        return
    _atomic_write(path, raw)
