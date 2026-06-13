"""
Tests: builds_manager save/read round-trip persists customMods and conditionState (both were
silently dropped by the fixed-schema file writer before).
"""
from persistence import builds_manager


def _save_read(tmp_path, monkeypatch, build):
    monkeypatch.setattr(builds_manager, "_DIR", str(tmp_path))
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


def test_defaults_when_absent(tmp_path, monkeypatch):
    loaded = _save_read(tmp_path, monkeypatch, {
        "id": "rt2", "name": "x", "slots": [None, None, None, None],
    })
    assert loaded["customMods"] == []
    assert loaded["conditionState"] == {}
