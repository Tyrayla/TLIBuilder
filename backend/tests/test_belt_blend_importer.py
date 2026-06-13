import pytest
from tools.belt_blend_importer import import_crawler_belt_blends, _normalize_talent_type

_DATA = {
    "entries": [
        {  # medium: modifier text inline, no name
            "modifier_id": "3401000", "talent_id": "340001",
            "effect": "+40 % Defense gained from Chest Armor",
            "talent_type": "Medium Talent Lv.0",
            "materials": [{"name": "Sage Lv. 1", "quantity": 4}, {"name": "Silver Mound Lv. 2", "quantity": 4}],
        },
        {  # core: "[Name] <text>"
            "modifier_id": "3402000", "talent_id": "340201",
            "effect": "[Sacrifice] Changes the base effect of Tenacity Blessing to: +8% additional damage",
            "talent_type": "Core Talents Lv.0",
            "materials": [{"name": "Gloomy Daffodil Lv. 5", "quantity": 3}],
        },
        {  # aromatic: name only → text from glossary
            "modifier_id": "3704000", "talent_id": "370001",
            "effect": "Divine Grace",
            "talent_type": "Aromatic Talent Lv.0",
            "materials": [],
        },
    ],
    "glossary": [
        {"term_id": "10148", "name": "Divine Grace",
         "description": "Changes the base effect of all Blessings to: +4% additional damage and -4% additional damage taken"},
        {"term_id": "719", "name": "Tenacity Blessing", "description": "..."},
    ],
}


def test_counts_and_glossary():
    out = import_crawler_belt_blends(_DATA)
    assert out["blend_count"] == 3
    assert out["glossary"]["10148"]["name"] == "Divine Grace"


def test_medium_inline_text_no_name():
    b = import_crawler_belt_blends(_DATA)["blends"][0]
    assert b["talent_type"] == "medium" and b["talent_name"] is None
    assert b["effect_text"] == "+40 % Defense gained from Chest Armor"
    assert b["materials"][0] == {"name": "Sage Lv. 1", "quantity": 4}


def test_core_bracket_name_and_inline_text():
    b = import_crawler_belt_blends(_DATA)["blends"][1]
    assert b["talent_type"] == "core" and b["talent_name"] == "Sacrifice"
    assert b["effect_text"] == "Changes the base effect of Tenacity Blessing to: +8% additional damage"
    assert b["effect_raw"].startswith("[Sacrifice]")


def test_aromatic_resolves_text_from_glossary():
    b = import_crawler_belt_blends(_DATA)["blends"][2]
    assert b["talent_type"] == "aromatic" and b["talent_name"] == "Divine Grace"
    # effect_raw is just the name; effect_text is joined from the glossary description
    assert b["effect_raw"] == "Divine Grace"
    assert b["effect_text"].startswith("Changes the base effect of all Blessings")
    assert b["affix"]["affix_kind"] == "numeric"  # parsed (+4 / -4), stat resolution deferred


def test_normalize_talent_type():
    assert _normalize_talent_type("Medium Talent Lv.0") == ("medium", 0)
    assert _normalize_talent_type("Core Talents Lv.0") == ("core", 0)
    assert _normalize_talent_type("Aromatic Talent Lv.0") == ("aromatic", 0)
