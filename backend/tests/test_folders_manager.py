"""
Tests: persistence/folders_manager.py — the folders.json manifest (folder tree, per-build
assignment, manual display order) that lives alongside the saved build .txt files.

Scope: file I/O only; writes to a temp directory via TLI_PERSIST_DIR, no real data/builds/ writes.

folders_manager API:
  load() -> dict                      (always returns all four keys)
  save(manifest: dict) -> dict        (raises ValueError on structural invariant violations;
                                        silently drops dangling references)
  remove_build(build_id: str) -> None (prunes assignment + order membership; no-op without a
                                        manifest file)
"""
import json
import os
import pytest


@pytest.fixture(autouse=True)
def isolated_builds_dir(tmp_path, monkeypatch):
    """Redirect folders_manager's (and builds_manager's) storage to a per-test temp dir."""
    monkeypatch.setenv("TLI_PERSIST_DIR", str(tmp_path))
    builds_path = str(tmp_path / "builds")
    os.makedirs(builds_path, exist_ok=True)
    yield builds_path


# Import after the path is set (conftest.py adds backend to sys.path)
from persistence import folders_manager
from persistence.builds_manager import save_build


def _touch_build(isolated_builds_dir, build_id="build1"):
    """Create a real build .txt file via builds_manager so folders_manager's _build_exists check
    passes for it."""
    save_build({"id": build_id, "name": "T", "slots": [None, None, None, None]})


def _manifest(folders=None, assignments=None, order=None, folder_order=None):
    return {
        "folders": folders if folders is not None else [],
        "assignments": assignments if assignments is not None else {},
        "order": order if order is not None else {},
        "folderOrder": folder_order if folder_order is not None else {},
    }


def _write_raw_manifest(isolated_builds_dir, obj):
    """Write a hand-corrupted folders.json directly to disk, bypassing save()'s validation entirely —
    simulates the file having been hand-edited or otherwise gone structurally bad out-of-band."""
    path = os.path.join(isolated_builds_dir, "folders.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


# ---------------------------------------------------------------------------
# load() defaults
# ---------------------------------------------------------------------------

class TestLoadDefaults:
    def test_load_with_no_manifest_returns_empty_defaults(self):
        manifest = folders_manager.load()
        assert manifest == {"folders": [], "assignments": {}, "order": {}, "folderOrder": {}}

    def test_load_with_corrupt_json_returns_empty_defaults(self, isolated_builds_dir):
        path = os.path.join(isolated_builds_dir, "folders.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not valid json")
        manifest = folders_manager.load()
        assert manifest == folders_manager._empty_manifest()

    def test_load_with_non_object_json_returns_empty_defaults(self, isolated_builds_dir):
        path = os.path.join(isolated_builds_dir, "folders.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump([1, 2, 3], f)
        manifest = folders_manager.load()
        assert manifest == folders_manager._empty_manifest()

    def test_load_fills_missing_keys_with_defaults(self, isolated_builds_dir):
        path = os.path.join(isolated_builds_dir, "folders.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"folders": [{"id": "f1", "name": "F1", "parentId": None}]}, f)
        manifest = folders_manager.load()
        assert manifest["folders"] == [{"id": "f1", "name": "F1", "parentId": None}]
        assert manifest["assignments"] == {}
        assert manifest["order"] == {}
        assert manifest["folderOrder"] == {}


# ---------------------------------------------------------------------------
# save/load round-trip
# ---------------------------------------------------------------------------

class TestSaveLoadRoundTrip:
    def test_round_trip_basic(self, isolated_builds_dir):
        _touch_build(isolated_builds_dir, "build1")
        manifest = _manifest(
            folders=[{"id": "f1", "name": "Favorites", "parentId": None}],
            assignments={"build1": "f1"},
            order={"root": [], "f1": ["build1"]},
            folder_order={"root": ["f1"]},
        )
        saved = folders_manager.save(manifest)
        loaded = folders_manager.load()
        assert saved == loaded
        assert loaded["folders"] == [{"id": "f1", "name": "Favorites", "parentId": None}]
        assert loaded["assignments"] == {"build1": "f1"}
        assert loaded["order"] == {"root": [], "f1": ["build1"]}
        assert loaded["folderOrder"] == {"root": ["f1"]}

    def test_save_strips_extraneous_folder_keys_and_trims_name(self, isolated_builds_dir):
        manifest = _manifest(folders=[{"id": "f1", "name": "  Trimmed  ", "parentId": None, "extra": "x"}])
        saved = folders_manager.save(manifest)
        assert saved["folders"] == [{"id": "f1", "name": "Trimmed", "parentId": None}]

    def test_nested_folder_parent_id_round_trips(self, isolated_builds_dir):
        manifest = _manifest(folders=[
            {"id": "parent", "name": "Parent", "parentId": None},
            {"id": "child", "name": "Child", "parentId": "parent"},
        ])
        loaded = folders_manager.save(manifest)
        by_id = {f["id"]: f for f in loaded["folders"]}
        assert by_id["child"]["parentId"] == "parent"

    def test_atomic_write_leaves_no_tmp_file(self, isolated_builds_dir):
        folders_manager.save(_manifest(folders=[{"id": "f1", "name": "F", "parentId": None}]))
        assert os.path.isfile(os.path.join(isolated_builds_dir, "folders.json"))
        assert not os.path.isfile(os.path.join(isolated_builds_dir, "folders.json.tmp"))


# ---------------------------------------------------------------------------
# Validation errors (each maps to a 400 at the server layer)
# ---------------------------------------------------------------------------

class TestValidationErrors:
    def test_unsafe_folder_id_rejected(self):
        with pytest.raises(ValueError):
            folders_manager.save(_manifest(folders=[{"id": "bad id!", "name": "F", "parentId": None}]))

    def test_unsafe_folder_id_path_traversal_rejected(self):
        with pytest.raises(ValueError):
            folders_manager.save(_manifest(folders=[{"id": "../etc", "name": "F", "parentId": None}]))

    def test_non_string_folder_id_rejected(self):
        with pytest.raises(ValueError):
            folders_manager.save(_manifest(folders=[{"id": 123, "name": "F", "parentId": None}]))

    def test_duplicate_folder_id_rejected(self):
        with pytest.raises(ValueError):
            folders_manager.save(_manifest(folders=[
                {"id": "f1", "name": "One", "parentId": None},
                {"id": "f1", "name": "Two", "parentId": None},
            ]))

    def test_literal_root_folder_id_rejected(self):
        with pytest.raises(ValueError):
            folders_manager.save(_manifest(folders=[{"id": "root", "name": "F", "parentId": None}]))

    def test_unknown_parent_id_rejected(self):
        with pytest.raises(ValueError):
            folders_manager.save(_manifest(folders=[{"id": "f1", "name": "F", "parentId": "ghost"}]))

    def test_self_parent_cycle_rejected(self):
        with pytest.raises(ValueError):
            folders_manager.save(_manifest(folders=[{"id": "f1", "name": "F", "parentId": "f1"}]))

    def test_two_node_parent_cycle_rejected(self):
        with pytest.raises(ValueError):
            folders_manager.save(_manifest(folders=[
                {"id": "a", "name": "A", "parentId": "b"},
                {"id": "b", "name": "B", "parentId": "a"},
            ]))

    def test_three_node_parent_cycle_rejected(self):
        with pytest.raises(ValueError):
            folders_manager.save(_manifest(folders=[
                {"id": "a", "name": "A", "parentId": "b"},
                {"id": "b", "name": "B", "parentId": "c"},
                {"id": "c", "name": "C", "parentId": "a"},
            ]))

    def test_empty_name_rejected(self):
        with pytest.raises(ValueError):
            folders_manager.save(_manifest(folders=[{"id": "f1", "name": "", "parentId": None}]))

    def test_whitespace_only_name_rejected(self):
        with pytest.raises(ValueError):
            folders_manager.save(_manifest(folders=[{"id": "f1", "name": "   ", "parentId": None}]))

    def test_non_string_name_rejected(self):
        with pytest.raises(ValueError):
            folders_manager.save(_manifest(folders=[{"id": "f1", "name": None, "parentId": None}]))

    def test_non_object_folder_entry_rejected(self):
        with pytest.raises(ValueError):
            folders_manager.save(_manifest(folders=["not-an-object"]))

    def test_non_dict_manifest_rejected(self):
        with pytest.raises(ValueError):
            folders_manager.save(["not", "a", "dict"])

    def test_invalid_parent_id_type_rejected(self):
        with pytest.raises(ValueError):
            folders_manager.save(_manifest(folders=[{"id": "f1", "name": "F", "parentId": 42}]))

    def test_rejected_save_does_not_persist(self, isolated_builds_dir):
        # A prior valid save exists; a subsequent invalid save must not clobber it.
        folders_manager.save(_manifest(folders=[{"id": "f1", "name": "Keep", "parentId": None}]))
        with pytest.raises(ValueError):
            folders_manager.save(_manifest(folders=[{"id": "root", "name": "Bad", "parentId": None}]))
        loaded = folders_manager.load()
        assert loaded["folders"] == [{"id": "f1", "name": "Keep", "parentId": None}]


# ---------------------------------------------------------------------------
# Silent cleaning (dangling references are dropped, not errors)
# ---------------------------------------------------------------------------

class TestSilentCleaning:
    def test_assignment_to_nonexistent_folder_dropped(self, isolated_builds_dir):
        _touch_build(isolated_builds_dir, "build1")
        saved = folders_manager.save(_manifest(assignments={"build1": "ghost-folder"}))
        assert saved["assignments"] == {}

    def test_assignment_for_nonexistent_build_dropped(self, isolated_builds_dir):
        # f1 is a real folder, but "ghost-build" has no build file on disk.
        saved = folders_manager.save(_manifest(
            folders=[{"id": "f1", "name": "F1", "parentId": None}],
            assignments={"ghost-build": "f1"},
        ))
        assert saved["assignments"] == {}

    def test_valid_assignment_survives_cleaning(self, isolated_builds_dir):
        _touch_build(isolated_builds_dir, "build1")
        saved = folders_manager.save(_manifest(
            folders=[{"id": "f1", "name": "F1", "parentId": None}],
            assignments={"build1": "f1"},
        ))
        assert saved["assignments"] == {"build1": "f1"}

    def test_order_key_for_missing_folder_dropped(self):
        saved = folders_manager.save(_manifest(order={"ghost-folder": []}))
        assert "ghost-folder" not in saved["order"]

    def test_order_root_key_preserved(self, isolated_builds_dir):
        _touch_build(isolated_builds_dir, "build1")
        saved = folders_manager.save(_manifest(order={"root": ["build1"]}))
        assert saved["order"] == {"root": ["build1"]}

    def test_order_prunes_missing_build_ids_inside_array(self, isolated_builds_dir):
        _touch_build(isolated_builds_dir, "build1")
        saved = folders_manager.save(_manifest(order={"root": ["build1", "ghost-build"]}))
        assert saved["order"] == {"root": ["build1"]}

    def test_order_non_list_value_dropped(self):
        saved = folders_manager.save(_manifest(
            folders=[{"id": "f1", "name": "F1", "parentId": None}],
            order={"f1": "not-a-list"},
        ))
        assert "f1" not in saved["order"]

    def test_folder_order_key_for_missing_folder_dropped(self):
        saved = folders_manager.save(_manifest(folder_order={"ghost-folder": []}))
        assert "ghost-folder" not in saved["folderOrder"]

    def test_folder_order_root_key_preserved(self):
        saved = folders_manager.save(_manifest(
            folders=[{"id": "f1", "name": "F1", "parentId": None}],
            folder_order={"root": ["f1"]},
        ))
        assert saved["folderOrder"] == {"root": ["f1"]}

    def test_folder_order_prunes_missing_folder_ids_inside_array(self):
        saved = folders_manager.save(_manifest(
            folders=[{"id": "f1", "name": "F1", "parentId": None}],
            folder_order={"root": ["f1", "ghost-folder"]},
        ))
        assert saved["folderOrder"] == {"root": ["f1"]}

    def test_non_string_assignment_entries_dropped(self, isolated_builds_dir):
        _touch_build(isolated_builds_dir, "build1")
        saved = folders_manager.save(_manifest(
            folders=[{"id": "f1", "name": "F1", "parentId": None}],
            assignments={"build1": 42},
        ))
        assert saved["assignments"] == {}

    def test_order_array_deduped_first_occurrence_wins(self, isolated_builds_dir):
        _touch_build(isolated_builds_dir, "build1")
        saved = folders_manager.save(_manifest(order={"root": ["build1", "build1"]}))
        assert saved["order"]["root"] == ["build1"]

    def test_order_array_dedup_preserves_first_occurrence_position(self, isolated_builds_dir):
        _touch_build(isolated_builds_dir, "b1")
        _touch_build(isolated_builds_dir, "b2")
        saved = folders_manager.save(_manifest(order={"root": ["b1", "b2", "b1"]}))
        assert saved["order"]["root"] == ["b1", "b2"]

    def test_folder_order_array_deduped_first_occurrence_wins(self, isolated_builds_dir):
        saved = folders_manager.save(_manifest(
            folders=[{"id": "f1", "name": "F1", "parentId": None}],
            folder_order={"root": ["f1", "f1"]},
        ))
        assert saved["folderOrder"]["root"] == ["f1"]


# ---------------------------------------------------------------------------
# remove_build()
# ---------------------------------------------------------------------------

class TestRemoveBuild:
    def test_remove_build_prunes_assignment(self, isolated_builds_dir):
        _touch_build(isolated_builds_dir, "build1")
        folders_manager.save(_manifest(
            folders=[{"id": "f1", "name": "F1", "parentId": None}],
            assignments={"build1": "f1"},
        ))
        folders_manager.remove_build("build1")
        loaded = folders_manager.load()
        assert "build1" not in loaded["assignments"]

    def test_remove_build_prunes_order_membership(self, isolated_builds_dir):
        _touch_build(isolated_builds_dir, "build1")
        _touch_build(isolated_builds_dir, "build2")
        folders_manager.save(_manifest(order={"root": ["build1", "build2"]}))
        folders_manager.remove_build("build1")
        loaded = folders_manager.load()
        assert loaded["order"]["root"] == ["build2"]

    def test_remove_build_prunes_from_multiple_order_arrays(self, isolated_builds_dir):
        _touch_build(isolated_builds_dir, "build1")
        folders_manager.save(_manifest(
            folders=[{"id": "f1", "name": "F1", "parentId": None}],
            order={"root": ["build1"], "f1": ["build1"]},
        ))
        folders_manager.remove_build("build1")
        loaded = folders_manager.load()
        assert loaded["order"]["root"] == []
        assert loaded["order"]["f1"] == []

    def test_remove_build_no_manifest_is_noop(self, isolated_builds_dir):
        # No manifest file exists at all — must not raise or create one.
        folders_manager.remove_build("build1")
        assert not os.path.isfile(os.path.join(isolated_builds_dir, "folders.json"))

    def test_remove_build_unaffected_when_not_referenced(self, isolated_builds_dir):
        _touch_build(isolated_builds_dir, "build1")
        _touch_build(isolated_builds_dir, "build2")
        folders_manager.save(_manifest(order={"root": ["build1", "build2"]}))
        folders_manager.remove_build("nonexistent-build-id")
        loaded = folders_manager.load()
        assert loaded["order"]["root"] == ["build1", "build2"]


# ---------------------------------------------------------------------------
# load()'s non-raising _best_effort_clean() — hand-corrupted folders.json files that save() would
# have rejected with a ValueError. load() must never raise or hang; it degrades the manifest instead.
# ---------------------------------------------------------------------------

class TestBestEffortCleanOnLoad:
    def test_two_node_parent_cycle_both_dropped(self, isolated_builds_dir):
        _write_raw_manifest(isolated_builds_dir, _manifest(folders=[
            {"id": "a", "name": "A", "parentId": "b"},
            {"id": "b", "name": "B", "parentId": "a"},
        ]))
        manifest = folders_manager.load()  # must not raise
        ids = {f["id"] for f in manifest["folders"]}
        assert ids == set()

    def test_folder_pointing_into_dropped_cycle_survives_rerooted_to_null(self, isolated_builds_dir):
        _write_raw_manifest(isolated_builds_dir, _manifest(folders=[
            {"id": "a", "name": "A", "parentId": "b"},
            {"id": "b", "name": "B", "parentId": "a"},
            {"id": "c", "name": "C", "parentId": "a"},
        ]))
        manifest = folders_manager.load()
        by_id = {f["id"]: f for f in manifest["folders"]}
        assert set(by_id.keys()) == {"c"}
        assert by_id["c"]["parentId"] is None

    def test_duplicate_folder_id_first_occurrence_kept(self, isolated_builds_dir):
        _write_raw_manifest(isolated_builds_dir, _manifest(folders=[
            {"id": "f1", "name": "First", "parentId": None},
            {"id": "f1", "name": "Second", "parentId": None},
        ]))
        manifest = folders_manager.load()
        assert manifest["folders"] == [{"id": "f1", "name": "First", "parentId": None}]

    def test_unsafe_id_folder_dropped(self, isolated_builds_dir):
        _write_raw_manifest(isolated_builds_dir, _manifest(folders=[
            {"id": "bad id!", "name": "Bad", "parentId": None},
            {"id": "ok", "name": "OK", "parentId": None},
        ]))
        manifest = folders_manager.load()
        assert [f["id"] for f in manifest["folders"]] == ["ok"]

    def test_literal_root_id_folder_dropped(self, isolated_builds_dir):
        _write_raw_manifest(isolated_builds_dir, _manifest(folders=[
            {"id": "root", "name": "Bad", "parentId": None},
            {"id": "ok", "name": "OK", "parentId": None},
        ]))
        manifest = folders_manager.load()
        assert [f["id"] for f in manifest["folders"]] == ["ok"]

    def test_empty_name_folder_dropped(self, isolated_builds_dir):
        _write_raw_manifest(isolated_builds_dir, _manifest(folders=[
            {"id": "f1", "name": "", "parentId": None},
            {"id": "f2", "name": "   ", "parentId": None},
            {"id": "ok", "name": "OK", "parentId": None},
        ]))
        manifest = folders_manager.load()
        assert [f["id"] for f in manifest["folders"]] == ["ok"]

    def test_dangling_parent_id_nulled_not_dropped(self, isolated_builds_dir):
        _write_raw_manifest(isolated_builds_dir, _manifest(folders=[
            {"id": "f1", "name": "F1", "parentId": "ghost-parent"},
        ]))
        manifest = folders_manager.load()
        assert manifest["folders"] == [{"id": "f1", "name": "F1", "parentId": None}]

    def test_order_arrays_deduped_and_pruned_on_load(self, isolated_builds_dir):
        _touch_build(isolated_builds_dir, "build1")
        _write_raw_manifest(isolated_builds_dir, _manifest(
            order={"root": ["build1", "build1", "ghost-build"]},
        ))
        manifest = folders_manager.load()
        assert manifest["order"]["root"] == ["build1"]

    def test_folder_order_arrays_deduped_and_pruned_on_load(self, isolated_builds_dir):
        _write_raw_manifest(isolated_builds_dir, _manifest(
            folders=[{"id": "f1", "name": "F1", "parentId": None}],
            folder_order={"root": ["f1", "f1", "ghost-folder"]},
        ))
        manifest = folders_manager.load()
        assert manifest["folderOrder"]["root"] == ["f1"]

    def test_assignments_to_dropped_folders_pruned(self, isolated_builds_dir):
        _touch_build(isolated_builds_dir, "build1")
        _write_raw_manifest(isolated_builds_dir, _manifest(
            folders=[
                {"id": "a", "name": "A", "parentId": "b"},
                {"id": "b", "name": "B", "parentId": "a"},
            ],
            assignments={"build1": "a"},  # "a" is part of the cycle and gets dropped
        ))
        manifest = folders_manager.load()
        assert manifest["assignments"] == {}

    def test_load_never_raises_on_a_thoroughly_corrupted_manifest(self, isolated_builds_dir):
        # Combines several corruption modes in one file: a cycle, a duplicate id, an unsafe id, an
        # empty name, a dangling parentId, dangling assignments, and dirty order/folderOrder arrays.
        _touch_build(isolated_builds_dir, "build1")
        _write_raw_manifest(isolated_builds_dir, {
            "folders": [
                {"id": "a", "name": "A", "parentId": "b"},
                {"id": "b", "name": "B", "parentId": "a"},
                {"id": "dup", "name": "Dup1", "parentId": None},
                {"id": "dup", "name": "Dup2", "parentId": None},
                {"id": "bad id!", "name": "Bad", "parentId": None},
                {"id": "empty-name", "name": "", "parentId": None},
                {"id": "orphan", "name": "Orphan", "parentId": "ghost"},
                "not-an-object",
            ],
            "assignments": {"build1": "a", "ghost-build": "dup"},
            "order": {"root": ["build1", "build1"], "ghost-key": ["build1"]},
            "folderOrder": {"root": ["dup", "dup", "ghost-folder"]},
        })
        manifest = folders_manager.load()  # must not raise
        ids = {f["id"] for f in manifest["folders"]}
        assert ids == {"dup", "orphan"}


# ---------------------------------------------------------------------------
# Server endpoint coverage (module-level: fastapi.testclient unavailable in this
# environment — httpx2 not installed — so the endpoint functions are exercised directly,
# same pattern used elsewhere in this suite, e.g. test_dreamweaver.py's `from server import ...`).
# ---------------------------------------------------------------------------

class TestServerEndpoints:
    def test_get_returns_defaults_when_absent(self, isolated_builds_dir):
        from server import get_build_folders
        result = get_build_folders()
        assert result == {"folders": [], "assignments": {}, "order": {}, "folderOrder": {}}

    def test_put_round_trips_through_get(self, isolated_builds_dir):
        from server import get_build_folders, put_build_folders, FoldersManifest
        req = FoldersManifest(folders=[{"id": "f1", "name": "Favorites", "parentId": None}])
        put_build_folders(req)
        assert get_build_folders()["folders"] == [{"id": "f1", "name": "Favorites", "parentId": None}]

    def test_put_invalid_manifest_raises_400(self, isolated_builds_dir):
        from server import put_build_folders, FoldersManifest
        from fastapi import HTTPException
        req = FoldersManifest(folders=[{"id": "root", "name": "Bad", "parentId": None}])
        with pytest.raises(HTTPException) as exc_info:
            put_build_folders(req)
        assert exc_info.value.status_code == 400

    def test_put_rejects_extra_top_level_fields(self, isolated_builds_dir):
        from server import FoldersManifest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            FoldersManifest(folders=[], unexpectedField="x")
