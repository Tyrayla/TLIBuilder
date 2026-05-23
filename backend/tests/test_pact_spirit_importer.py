import pytest
from tools.pact_spirit_importer import import_crawler_spirit, import_crawler_spirits

_SPIRIT = {
    "name": "Abyssal King Soul",
    "description": "Increases Reaping Cooldown, Damage Over Time, and Damage Affliction.",
    "affinities": ["Persistent", "Legendary"],
    "main_skill_name": "Unholy Throne",
    "main_skill_effect": "35 % chance for Damage Over Time to spread to targets in Proximity",
    "upgrade_ranks": [
        {"rank": 1, "modifiers": ["35 % chance for Damage Over Time to spread to targets in Proximity", "+25 % additional Reaping Recovery Speed"]},
        {"rank": 2, "modifiers": ["35 % chance for Damage Over Time to spread to targets in Proximity", "+25 % additional Reaping Recovery Speed", "+2 % additional damage"]},
    ],
    "slots": [
        {"name": "Reaping Cooldown I", "effect": "+5 % Reaping Recovery Speed", "ring": "inner"},
        {"name": "Damage Over Time I", "effect": "+12 % Damage Over Time", "ring": "mid"},
        {"name": "Unholy Throne", "effect": "35 % chance for Damage Over Time to spread to targets in Proximity", "ring": "+25% additionalreapingrecovery speed"},
    ],
    "glossary": [
        {"term_id": "160", "name": "Proximity", "description": "Within 4m"},
        {"term_id": "138", "name": "Reaping", "description": "Deals a certain amount of True Damage"},
    ],
}


def test_item_id_slug():
    r = import_crawler_spirit(_SPIRIT)
    assert r["item_id"] == "abyssal_king_soul"


def test_name_preserved():
    r = import_crawler_spirit(_SPIRIT)
    assert r["name"] == "Abyssal King Soul"


def test_affinities_stored():
    r = import_crawler_spirit(_SPIRIT)
    assert r["affinities"] == ["Persistent", "Legendary"]


def test_upgrade_ranks_stored():
    r = import_crawler_spirit(_SPIRIT)
    assert len(r["upgrade_ranks"]) == 2
    assert r["upgrade_ranks"][0]["rank"] == 1
    assert len(r["upgrade_ranks"][0]["modifiers"]) == 2


def test_ring_normalization():
    r = import_crawler_spirit(_SPIRIT)
    # The last slot has a garbled ring value — should be normalized to "outer"
    outer_slots = [s for s in r["slots"] if s["name"] == "Unholy Throne"]
    assert len(outer_slots) == 1
    assert outer_slots[0]["ring"] == "outer"


def test_valid_rings_preserved():
    r = import_crawler_spirit(_SPIRIT)
    assert r["slots"][0]["ring"] == "inner"
    assert r["slots"][1]["ring"] == "mid"


def test_glossary_list_to_dict():
    r = import_crawler_spirit(_SPIRIT)
    assert "160" in r["glossary"]
    assert r["glossary"]["160"]["name"] == "Proximity"
    assert "138" in r["glossary"]


def test_import_crawler_spirits_filters_nameless():
    items = [_SPIRIT, {"description": "no name here"}]
    result = import_crawler_spirits(items)
    assert len(result) == 1
    assert result[0]["item_id"] == "abyssal_king_soul"
