"""
Tests: persistence/builds_manager.py — build save, load, and delete round-trips.
Scope: file I/O only; writes to a temp directory, no real data/builds/ writes.

builds_manager API:
  load() -> list[dict]
  save_build(build: dict) -> dict   (mutates/sets build['id'] if missing)
  delete_build(build_id: str) -> bool
"""
import json
import os
import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_builds_dir(tmp_path):
    """Redirect builds_manager._DIR to a per-test temp directory."""
    builds_path = str(tmp_path / "builds")
    os.makedirs(builds_path, exist_ok=True)
    with patch("persistence.builds_manager._DIR", builds_path):
        yield builds_path


# Import after the path is set (conftest.py adds backend to sys.path)
from persistence.builds_manager import load, save_build, delete_build


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slot(tree="Warrior"):
    return {"treeName": tree, "nodeStates": {"warrior_c0_r0": 2}}


def _slate(slate_id="slate-1"):
    return {
        "id": slate_id,
        "kind": "circle",
        "cells": [[0, 0]],
        "orientationIndex": 0,
        "shapeIndex": 0,
        "anchor": [0, 0],
        "slots": [],
    }


def _build(name="Test Build", slots=None, slates=None):
    return {
        "name": name,
        "slots": slots if slots is not None else [_slot(), None, None, None],
        "slates": slates if slates is not None else [],
    }


# ---------------------------------------------------------------------------
# Save / Load round-trips
# ---------------------------------------------------------------------------

class TestSaveLoadRoundTrip:
    def test_save_assigns_id(self):
        build = save_build(_build())
        assert "id" in build
        assert build["id"]

    def test_save_then_load_returns_same_name(self):
        save_build(_build("My Build"))
        builds = load()
        assert len(builds) == 1
        assert builds[0]["name"] == "My Build"

    def test_save_then_load_preserves_tree_name(self):
        save_build(_build(slots=[_slot("Ranger"), None, None, None]))
        builds = load()
        assert builds[0]["slots"][0]["treeName"] == "Ranger"

    def test_null_slots_round_trip(self):
        save_build(_build(slots=[_slot(), None, None, None]))
        builds = load()
        # Positions 2-4 should be None
        assert builds[0]["slots"][1] is None

    def test_save_then_load_preserves_slates(self):
        slate = _slate("my-slate")
        save_build(_build(slates=[slate]))
        builds = load()
        loaded = builds[0]["slates"]
        assert len(loaded) == 1
        assert loaded[0]["id"] == "my-slate"
        assert loaded[0]["kind"] == "circle"

    def test_save_without_slates_loads_empty_list(self):
        save_build(_build(slates=[]))
        builds = load()
        assert builds[0]["slates"] == []

    def test_multiple_builds_all_load(self):
        save_build(_build("Build A"))
        save_build(_build("Build B"))
        builds = load()
        names = {b["name"] for b in builds}
        assert names == {"Build A", "Build B"}

    def test_update_existing_build_by_id(self):
        build = save_build(_build("Original"))
        build_id = build["id"]
        build["name"] = "Updated"
        build["slots"] = [_slot("Assassin"), None, None, None]
        save_build(build)
        builds = load()
        assert len(builds) == 1
        assert builds[0]["name"] == "Updated"
        assert builds[0]["id"] == build_id

    def test_node_states_round_trip(self):
        slot = {"treeName": "Warrior", "nodeStates": {"warrior_c0_r0": 2, "warrior_c1_r1": 3}}
        save_build(_build(slots=[slot, None, None, None]))
        builds = load()
        ns = builds[0]["slots"][0]["nodeStates"]
        assert ns["warrior_c0_r0"] == 2
        assert ns["warrior_c1_r1"] == 3

    def test_zero_point_nodes_not_stored(self):
        """Nodes with 0 points are not serialized (they're unallocated)."""
        slot = {"treeName": "Warrior", "nodeStates": {"warrior_c0_r0": 1, "warrior_c1_r1": 0}}
        save_build(_build(slots=[slot, None, None, None]))
        builds = load()
        ns = builds[0]["slots"][0]["nodeStates"]
        # The zero-point node should not be present (stripped during write)
        assert "warrior_c1_r1" not in ns


class TestDeleteBuild:
    def test_delete_removes_build(self):
        build = save_build(_build())
        delete_build(build["id"])
        assert load() == []

    def test_delete_nonexistent_returns_false(self):
        result = delete_build("nonexistent-id-999")
        assert result is False

    def test_delete_one_leaves_others(self):
        keep = save_build(_build("Keep"))
        remove = save_build(_build("Remove"))
        delete_build(remove["id"])
        remaining = load()
        assert len(remaining) == 1
        assert remaining[0]["name"] == "Keep"


class TestBackwardCompatibility:
    """Builds saved without a slates= line must load with slates: []."""

    def test_legacy_file_without_slates_line(self, isolated_builds_dir):
        legacy_content = (
            "id=legacy-001\n"
            "name=Legacy Build\n"
            "slot1_tree=Warrior\n"
            "slot1_nodes=warrior_c0_r0:2\n"
            "slot2_tree=\n"
            "slot2_nodes=\n"
            "slot3_tree=\n"
            "slot3_nodes=\n"
            "slot4_tree=\n"
            "slot4_nodes=\n"
        )
        path = os.path.join(isolated_builds_dir, "legacy-001.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(legacy_content)

        builds = load()
        assert len(builds) == 1
        assert builds[0]["slates"] == []
        assert builds[0]["name"] == "Legacy Build"
        assert builds[0]["slots"][0]["treeName"] == "Warrior"
