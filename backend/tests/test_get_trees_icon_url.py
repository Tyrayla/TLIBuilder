"""Coverage for GET /api/trees (server.get_trees()) icon_url field, sourced from
season_manager.load_talent_tree_selector_icons(active_season), keyed by name.replace(' ', '_')."""
from persistence import season_manager
from server import get_trees, TREES


def test_no_active_season_icon_url_is_none_for_all_trees(monkeypatch):
    monkeypatch.setattr(season_manager, "get_active_season", lambda: None)
    result = get_trees()
    assert result, "get_trees() returned nothing to check"
    assert all(t["icon_url"] is None for t in result)


def test_active_season_with_icons_present_populates_known_tree(monkeypatch):
    monkeypatch.setattr(season_manager, "get_active_season", lambda: "SS13")
    monkeypatch.setattr(
        season_manager, "load_talent_tree_selector_icons",
        lambda season: {"God_of_Might": "https://example.com/god_of_might.webp"},
    )
    result = get_trees()
    by_name = {t["name"]: t for t in result}
    assert "God of Might" in by_name
    assert by_name["God of Might"]["icon_url"] == "https://example.com/god_of_might.webp"


def test_tree_absent_from_icon_map_yields_none_not_error():
    # "Nether King" is a real, confirmed gap in data/seasons/SS13/_talent_tree_selector_icons.json
    # (no icon upstream — see season_manager.load_talent_tree_selector_icons docstring), so this
    # exercises the real SS13 season data rather than a synthetic map.
    assert "Nether King" in TREES, "fixture assumption: 'Nether King' tree missing from trees_meta.json"
    monkeypatch_active = season_manager.get_active_season()
    assert monkeypatch_active == "SS13", (
        f"active season is {monkeypatch_active!r}, not SS13 — this test targets the SS13 "
        "'Nether King' icon gap; re-verify against the new active season's icon map before updating."
    )

    result = get_trees()
    by_name = {t["name"]: t for t in result}
    assert "Nether King" in by_name
    assert by_name["Nether King"]["icon_url"] is None
