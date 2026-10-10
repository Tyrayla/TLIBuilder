"""get_season_summary reads an optional _season.json (label, status, note) and never raises on a bad one."""
import json

import pytest

from persistence import season_manager


@pytest.fixture()
def seasons_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(season_manager, "_SEASONS_DIR", str(tmp_path))
    (tmp_path / "SS99").mkdir()
    return tmp_path / "SS99"


def test_label_status_and_note_come_from_the_file(seasons_dir):
    (seasons_dir / "_season.json").write_text(json.dumps(
        {"label": "SS99 Pre-Season", "status": "pre-season", "note": "Preview dataset."}), encoding="utf-8")
    s = season_manager.get_season_summary("SS99")
    assert s["name"] == "SS99"
    assert s["label"] == "SS99 Pre-Season"
    assert s["status"] == "pre-season"
    assert s["note"] == "Preview dataset."


def test_absent_file_falls_back_to_the_season_name(seasons_dir):
    s = season_manager.get_season_summary("SS99")
    assert (s["label"], s["status"], s["note"]) == ("SS99", None, None)


@pytest.mark.parametrize("content", ["{not json", "[1, 2]", '{"label": 5, "status": null, "note": ""}', ""])
def test_malformed_file_falls_back_without_raising(seasons_dir, content):
    (seasons_dir / "_season.json").write_text(content, encoding="utf-8")
    s = season_manager.get_season_summary("SS99")
    assert (s["label"], s["status"], s["note"]) == ("SS99", None, None)


def test_partial_file_keeps_valid_fields_only(seasons_dir):
    (seasons_dir / "_season.json").write_text(json.dumps({"label": "  Spaced  ", "note": 3}), encoding="utf-8")
    s = season_manager.get_season_summary("SS99")
    assert (s["label"], s["status"], s["note"]) == ("Spaced", None, None)
