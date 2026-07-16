"""
Tests: builds_manager save/read round-trip persists customMods and conditionState (both were
silently dropped by the fixed-schema file writer before).
"""
import os
import time

from persistence import builds_manager


def _save_read(tmp_path, monkeypatch, build):
    monkeypatch.setenv("TLI_PERSIST_DIR", str(tmp_path))
    builds_manager.save_build(build)
    return builds_manager._read_file(build["id"])


def test_custom_mods_and_condition_state_roundtrip(tmp_path, monkeypatch):
    loaded = _save_read(tmp_path, monkeypatch, {
        "id": "rt1", "name": "T", "slots": [None, None, None, None],
        "customMods": ["+10% Critical Strike Rating", "+5 Strength"],
        "conditionState": {"fervor_rating": 100.0, "dual_wielding": True},
    })
    assert loaded["customMods"] == ["+10% Critical Strike Rating", "+5 Strength"]
    assert loaded["conditionState"] == {"fervor_rating": 100.0, "dual_wielding": True}


def test_slate_inventory_roundtrip(tmp_path, monkeypatch):
    # bug-181: slateInventory was dropped by the file writer, so shared/reopened builds lost saved slates.
    inv = [{"id": "inv1", "kind": "micro", "orientationIndex": 0, "shapeIndex": 0, "slots": []}]
    loaded = _save_read(tmp_path, monkeypatch, {
        "id": "rt3", "name": "T", "slots": [None, None, None, None],
        "slateInventory": inv,
    })
    assert loaded["slateInventory"] == inv


def test_defaults_when_absent(tmp_path, monkeypatch):
    loaded = _save_read(tmp_path, monkeypatch, {
        "id": "rt2", "name": "x", "slots": [None, None, None, None],
    })
    assert loaded["customMods"] == []
    assert loaded["conditionState"] == {}
    assert loaded["slateInventory"] == []


# ---------------------------------------------------------------------------
# Timestamps (createdAt / updatedAt)
# ---------------------------------------------------------------------------

def test_timestamps_stamped_on_first_save(tmp_path, monkeypatch):
    monkeypatch.setenv("TLI_PERSIST_DIR", str(tmp_path))
    fixed = 1_700_000_000.0
    monkeypatch.setattr(time, "time", lambda: fixed)
    build = builds_manager.save_build({"id": "ts1", "name": "T", "slots": [None, None, None, None]})
    assert build["createdAt"] == fixed
    assert build["updatedAt"] == fixed
    loaded = builds_manager._read_file("ts1")
    assert loaded["createdAt"] == fixed
    assert loaded["updatedAt"] == fixed


def test_created_at_preserved_updated_at_bumped_on_resave(tmp_path, monkeypatch):
    monkeypatch.setenv("TLI_PERSIST_DIR", str(tmp_path))
    first, second = 1_700_000_000.0, 1_700_000_500.0

    monkeypatch.setattr(time, "time", lambda: first)
    build = builds_manager.save_build({"id": "ts2", "name": "First", "slots": [None, None, None, None]})
    assert build["createdAt"] == first
    assert build["updatedAt"] == first

    monkeypatch.setattr(time, "time", lambda: second)
    build["name"] = "Second"
    build = builds_manager.save_build(build)
    assert build["createdAt"] == first
    assert build["updatedAt"] == second

    loaded = builds_manager._read_file("ts2")
    assert loaded["createdAt"] == first
    assert loaded["updatedAt"] == second


def test_client_supplied_timestamps_are_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("TLI_PERSIST_DIR", str(tmp_path))
    fixed = 1_700_000_000.0
    monkeypatch.setattr(time, "time", lambda: fixed)
    # Client sends spoofed/forged timestamps — the server must never trust them.
    build = builds_manager.save_build({
        "id": "ts3", "name": "T", "slots": [None, None, None, None],
        "createdAt": 1.0, "updatedAt": 2.0,
    })
    assert build["createdAt"] == fixed
    assert build["updatedAt"] == fixed
    loaded = builds_manager._read_file("ts3")
    assert loaded["createdAt"] == fixed
    assert loaded["updatedAt"] == fixed


def test_client_supplied_timestamps_ignored_on_resave(tmp_path, monkeypatch):
    monkeypatch.setenv("TLI_PERSIST_DIR", str(tmp_path))
    first, second = 1_700_000_000.0, 1_700_000_500.0
    monkeypatch.setattr(time, "time", lambda: first)
    build = builds_manager.save_build({"id": "ts4", "name": "T", "slots": [None, None, None, None]})

    monkeypatch.setattr(time, "time", lambda: second)
    build["createdAt"] = 999.0  # client tries to spoof createdAt on re-save
    build["updatedAt"] = 999.0
    build = builds_manager.save_build(build)
    assert build["createdAt"] == first  # preserved from disk, not the client value
    assert build["updatedAt"] == second  # always "now", not the client value


def test_mtime_fallback_for_legacy_file_without_timestamps(tmp_path, monkeypatch):
    monkeypatch.setenv("TLI_PERSIST_DIR", str(tmp_path))
    builds_dir = tmp_path / "builds"
    os.makedirs(builds_dir, exist_ok=True)
    legacy_content = (
        "id=legacy-ts\n"
        "name=Legacy Build\n"
        "slot1_tree=\n"
        "slot1_nodes=\n"
        "slot2_tree=\n"
        "slot2_nodes=\n"
        "slot3_tree=\n"
        "slot3_nodes=\n"
        "slot4_tree=\n"
        "slot4_nodes=\n"
    )
    path = builds_dir / "legacy-ts.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write(legacy_content)
    mtime = os.path.getmtime(str(path))

    loaded = builds_manager._read_file("legacy-ts")
    assert loaded["createdAt"] == mtime
    assert loaded["updatedAt"] == mtime


# ---------------------------------------------------------------------------
# delete_build prunes the folders manifest
# ---------------------------------------------------------------------------

def test_delete_build_prunes_folders_manifest(tmp_path, monkeypatch):
    from persistence import folders_manager
    monkeypatch.setenv("TLI_PERSIST_DIR", str(tmp_path))
    build = builds_manager.save_build({"id": "del1", "name": "T", "slots": [None, None, None, None]})
    folders_manager.save({
        "folders": [{"id": "f1", "name": "F1", "parentId": None}],
        "assignments": {build["id"]: "f1"},
        "order": {"root": [], "f1": [build["id"]]},
        "folderOrder": {"root": ["f1"]},
    })

    builds_manager.delete_build(build["id"])

    manifest = folders_manager.load()
    assert build["id"] not in manifest["assignments"]
    assert build["id"] not in manifest["order"]["f1"]
