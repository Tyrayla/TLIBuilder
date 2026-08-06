"""
Tests: persistence/season_manager.py — season-tree file reads reject path traversal (CWE-22).

An untrusted slate `selectedNodeId` (carried through a shared tli1_ build code) reaches
load_season_tree()/save_season_tree() as `tree_slug` and flows into os.path.join()/open().
These tests pin that:
  - a legitimate slug still round-trips to the same file, and
  - any slug that could climb out of data/seasons/<season>/ is refused at the sink.
"""
import os
import pytest

from persistence import season_manager


@pytest.fixture(autouse=True)
def isolated_seasons_dir(tmp_path, monkeypatch):
    """Point the season store at a per-test temp dir (no real data/seasons/ writes)."""
    seasons = tmp_path / "seasons"
    seasons.mkdir()
    monkeypatch.setattr(season_manager, "_SEASONS_DIR", str(seasons))
    season_manager._season_trees_cache.clear()
    return seasons


def test_legit_slug_round_trips():
    season_manager.save_season_tree("SS12", "War God", "war_god", {"nodes": [], "tree_name": "War God"})
    loaded = season_manager.load_season_tree("SS12", "war_god")
    assert loaded is not None
    assert loaded["tree_name"] == "War God"


def test_missing_legit_slug_returns_none_not_raises():
    # A legitimate-but-absent slug must still return None (unchanged behavior), not raise.
    assert season_manager.load_season_tree("SS12", "no_such_tree") is None


@pytest.mark.parametrize("evil_slug", [
    "../../../../etc/passwd",
    "..\\..\\..\\windows\\win.ini",
    "../secret",
    "..",
    "a/b",
    "a\\b",
    "C:/Windows/System32/config",
    "foo:bar",
])
def test_load_rejects_traversal_slug(evil_slug):
    with pytest.raises(ValueError):
        season_manager.load_season_tree("SS12", evil_slug)


@pytest.mark.parametrize("evil_slug", [
    "../../../../tmp/pwned",
    "..\\..\\evil",
    "a/b",
    "foo:bar",
])
def test_save_rejects_traversal_slug(evil_slug, isolated_seasons_dir):
    with pytest.raises(ValueError):
        season_manager.save_season_tree("SS12", "x", evil_slug, {"nodes": []})
    # And nothing was written outside the season directory.
    assert not (isolated_seasons_dir.parent / "pwned").exists()


def test_traversal_cannot_read_sibling_file(tmp_path):
    # Plant a file OUTSIDE the season dir and confirm a crafted slug can't reach it.
    secret = tmp_path / "secret.json"
    secret.write_text('{"stolen": true}', encoding="utf-8")
    # data/seasons/<season>/../../secret  → would resolve to tmp_path/secret without the guard.
    with pytest.raises(ValueError):
        season_manager.load_season_tree("SS12", "../../secret")
