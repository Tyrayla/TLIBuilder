import json

import models.conditions as conditions


def test_load_preserves_dynamic_enum_options_source(tmp_path, monkeypatch):
    path = tmp_path / "conditions.json"
    path.write_text(json.dumps({
        "conditions": [{
            "key": "merged_slot",
            "label": "Merged Magus",
            "category": "Hero Trait",
            "value_type": "enum",
            "enum_values": [],
            "default_enum": "",
            "options_source": "spirit_magus_slots",
        }],
    }), encoding="utf-8")
    monkeypatch.setattr(conditions, "_CONDITIONS_PATH", str(path))

    loaded, _, _ = conditions._load()

    assert loaded[0].options_source == "spirit_magus_slots"


def test_conditions_endpoint_exposes_dynamic_enum_options_source(monkeypatch):
    from fastapi.testclient import TestClient
    from models.conditions import ConditionDef
    import server

    monkeypatch.setattr(conditions, "ALL_CONDITIONS", [ConditionDef(
        key="merged_slot",
        label="Merged Magus",
        category="Hero Trait",
        value_type="enum",
        options_source="spirit_magus_slots",
    )])
    monkeypatch.setattr(conditions, "DERIVED_ACTIVE_KEYS", {})

    response = TestClient(server.app).get("/api/conditions")

    assert response.status_code == 200
    assert response.json()["Hero Trait"][0]["options_source"] == "spirit_magus_slots"
