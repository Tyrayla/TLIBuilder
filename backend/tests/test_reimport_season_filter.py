"""
Tests: tools/reimport_season.py — step_filter()'s active-season guard.

`data/node_type_filter.json` is a single GLOBAL file with no season namespace of its own; the
engine always reads it for whatever season `data/seasons/.active` currently points to. Before the
fix, `step_filter` unconditionally rebuilt that file from whatever `--season` was passed on the
command line, so reimporting an OLD season (e.g. to regenerate a stale artifact) would silently
clobber the live engine's active-season filter with a different season's node texts.

Fix: step_filter now reads `season_manager.get_active_season()` first and returns a "SKIPPED —
..." string WITHOUT calling `build_filter`/`build_node_recipes`/`save_filter` whenever the active
season differs from the `season` argument. When they match (or no season is active yet), it
proceeds exactly as before.

Scope: mocks `persistence.season_manager.get_active_season` / `load_all_season_trees` and
`tools.node_type_filter_builder.build_filter` / `build_node_recipes` / `save_filter` so the real
`data/node_type_filter.json` and `data/seasons/**` are never touched (mirrors the mocking style in
test_folders_manager.py / test_builds_manager.py, adapted for step_filter's function-local
imports — patching the target module's attribute is enough since `from ... import name` re-reads
the attribute at call time).
"""
from unittest.mock import MagicMock

from tools.reimport_season import step_filter


def _patch_filter_builder(monkeypatch):
    """Patch the three node_type_filter_builder entry points step_filter calls, and return the
    mocks so callers can assert on them."""
    mock_build_filter = MagicMock(return_value={
        "_meta": {"matched": 1, "ambiguous": 0, "unmatched": 0, "conditional": 0},
    })
    mock_build_node_recipes = MagicMock(return_value={"node1": []})
    mock_save_filter = MagicMock()
    monkeypatch.setattr("tools.node_type_filter_builder.build_filter", mock_build_filter)
    monkeypatch.setattr("tools.node_type_filter_builder.build_node_recipes", mock_build_node_recipes)
    monkeypatch.setattr("tools.node_type_filter_builder.save_filter", mock_save_filter)
    return mock_build_filter, mock_build_node_recipes, mock_save_filter


def test_step_filter_skips_when_active_season_differs(monkeypatch):
    monkeypatch.setattr("persistence.season_manager.get_active_season", lambda: "SS11")
    mock_build_filter, mock_build_node_recipes, mock_save_filter = _patch_filter_builder(monkeypatch)

    result = step_filter("SS12", "unused-crawl-dir")

    assert "SKIPPED" in result
    assert "SS11" in result
    assert "SS12" in result
    mock_build_filter.assert_not_called()
    mock_build_node_recipes.assert_not_called()
    mock_save_filter.assert_not_called()


def test_step_filter_proceeds_when_active_season_matches(monkeypatch):
    monkeypatch.setattr("persistence.season_manager.get_active_season", lambda: "SS12")
    monkeypatch.setattr("persistence.season_manager.load_all_season_trees", lambda season, raw=False: {"tree1": {}})
    mock_build_filter, mock_build_node_recipes, mock_save_filter = _patch_filter_builder(monkeypatch)

    result = step_filter("SS12", "unused-crawl-dir")

    assert "SKIPPED" not in result
    assert "matched=1" in result
    mock_build_filter.assert_called_once()
    mock_build_node_recipes.assert_called_once()
    mock_save_filter.assert_called_once()


def test_step_filter_proceeds_when_no_season_is_active_yet(monkeypatch):
    """`active is None` (no `.active` file yet, e.g. a fresh install) must NOT be treated as a
    mismatch — the guard only skips when there IS an active season and it differs."""
    monkeypatch.setattr("persistence.season_manager.get_active_season", lambda: None)
    monkeypatch.setattr("persistence.season_manager.load_all_season_trees", lambda season, raw=False: {"tree1": {}})
    mock_build_filter, mock_build_node_recipes, mock_save_filter = _patch_filter_builder(monkeypatch)

    result = step_filter("SS12", "unused-crawl-dir")

    assert "SKIPPED" not in result
    mock_save_filter.assert_called_once()
