import pytest
from tools.craft_base_type_importer import import_crawler_craft_base_type, import_crawler_craft_base_types

_BELT = {
    "name": "Belt",
    "all_affixes": [
        {"Affix Effect": "+(54–74) Max Life", "Source": "Belt", "Type": "Base Affix"},
        {"Affix Effect": "+(5–10) % Fire Resistance", "Source": "Belt", "Type": "Base Affix"},
        {"Affix Effect": "Immune to Paralysis Immune to Blinding", "Source": "Belt", "Type": "Base Affix"},
    ],
}


def test_item_id_slug():
    r = import_crawler_craft_base_type(_BELT)
    assert r["item_id"] == "belt"


def test_name_preserved():
    r = import_crawler_craft_base_type(_BELT)
    assert r["name"] == "Belt"


def test_affixes_count():
    r = import_crawler_craft_base_type(_BELT)
    assert len(r["affixes"]) == 3


def test_numeric_affix_parsed():
    r = import_crawler_craft_base_type(_BELT)
    first = r["affixes"][0]
    assert first["affix_kind"] == "numeric"
    assert len(first["numeric_values"]) == 1
    assert first["numeric_values"][0]["kind"] == "range"
    assert first["numeric_values"][0]["min"] == 54.0
    assert first["numeric_values"][0]["max"] == 74.0
    assert first["expression"] == "+(#) Max Life"


def test_special_affix_parsed():
    r = import_crawler_craft_base_type(_BELT)
    immune = r["affixes"][2]
    assert immune["affix_kind"] == "special"
    assert immune["numeric_values"] == []


def test_source_and_type_stored():
    r = import_crawler_craft_base_type(_BELT)
    for a in r["affixes"]:
        assert a["source"] == "Belt"
        assert a["affix_type"] == "Base Affix"


def test_import_crawler_craft_base_types_filters_nameless():
    items = [_BELT, {"all_affixes": []}]
    result = import_crawler_craft_base_types(items)
    assert len(result) == 1
    assert result[0]["item_id"] == "belt"
