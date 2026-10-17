from persistence import season_manager
from tools import reimport_season


def test_step_trees_preserves_existing_connections_and_glossary(monkeypatch):
    crawler_data = {
        "name": "Alchemist",
        "nodes": [
            {"talent_id": "01010100", "name": "A", "type": "micro_talent",
             "column": 1, "row": 1, "max_rank": 1, "effects": ["+5% damage"],
             "pts_required": 0, "icon_url": "", "prerequisites": []},
            {"talent_id": "01020100", "name": "B", "type": "micro_talent",
             "column": 2, "row": 1, "max_rank": 1, "effects": ["+6% damage"],
             "pts_required": 0, "icon_url": "", "prerequisites": []},
        ],
        "glossary": [],
    }
    existing = {
        "connections": [{"from": "alchemist_c0_r0", "to": "alchemist_c1_r0"}],
        "glossary": {"719": {"name": "Tenacity Blessing", "description": "Existing definition."}},
    }
    saved = {}

    def fake_load(path):
        return {"Alchemist": {}} if path.endswith("trees_meta.json") else crawler_data

    monkeypatch.setattr(reimport_season, "_load", fake_load)
    monkeypatch.setattr(
        reimport_season, "_files",
        lambda crawl, sub: ["alchemist.json"] if sub == "talent_tree" else [],
    )
    monkeypatch.setattr(season_manager, "load_season_tree", lambda season, slug, raw=False: existing)
    monkeypatch.setattr(
        season_manager, "save_season_tree",
        lambda season, tree_name, tree_slug, data: saved.update(data),
    )

    result = reimport_season.step_trees("SS14", "unused-crawl-dir")

    assert result == "1 trees, 0 New God talents"
    assert saved["connections"] == [{"from": "alchemist_c0_r0", "to": "alchemist_c1_r0"}], \
        "bulk reimport dropped the hand-authored connection"
    assert saved["glossary"]["719"]["description"] == "Existing definition.", \
        "bulk reimport dropped the existing glossary definition"
