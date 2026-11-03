"""Hero-memory log crosswalk fields are exposed to the renderer importer."""

from fastapi.testclient import TestClient

import server
from persistence import season_manager


def test_hero_memories_endpoint_exposes_log_affixes_when_season_catalog_is_missing(monkeypatch):
    log_affixes = [{"id": 71001, "name": "Memory Power", "type": "fixed"}]
    monkeypatch.setattr(season_manager, "get_active_season", lambda: "SS14")
    monkeypatch.setattr(season_manager, "load_hero_memories", lambda _season: None)
    monkeypatch.setattr(
        season_manager,
        "load_hero_memory_log_crosswalk",
        lambda _season: {"base_stats": [{"id": 71002}], "affixes": log_affixes},
    )

    response = TestClient(server.app).get("/api/hero-memories")

    assert response.status_code == 200
    assert response.json()["season"] == "SS14"
    assert response.json()["log_base_stats"] == [{"id": 71002}]
    assert response.json()["log_affixes"] == log_affixes
