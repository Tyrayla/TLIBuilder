import pytest
from tools.graft_importer import import_crawler_graft, import_crawler_grafts

_GRAFT = {
    "name": "Vorax Aberrant Limb: Digits",
    "craft_affixes": [
        {"tier": "0+", "modifier": "+(287–372) Max Life", "level": "1", "weight": "0", "affix_type": "Basic Affix"},
        {"tier": "0",  "modifier": "+(221–286) Max Life", "level": "1", "weight": "1", "affix_type": "Basic Affix"},
        {"tier": "1",  "modifier": "+(155–220) Max Life", "level": "1", "weight": "1", "affix_type": "Basic Affix"},
        {"tier": "0+", "modifier": "+(25–29) % Life Regeneration Speed", "level": "1", "weight": "0", "affix_type": "Basic Affix"},
        {"tier": "0",  "modifier": "Immune to Blinding", "level": "1", "weight": "1", "affix_type": "Implicit Affix"},
    ],
}


def test_item_id_slug():
    r = import_crawler_graft(_GRAFT)
    assert r["item_id"] == "vorax_aberrant_limb_digits"


def test_name_preserved():
    r = import_crawler_graft(_GRAFT)
    assert r["name"] == "Vorax Aberrant Limb: Digits"


def test_all_tiers_stored():
    r = import_crawler_graft(_GRAFT)
    assert len(r["affixes"]) == 5


def test_numeric_affix_parsed():
    r = import_crawler_graft(_GRAFT)
    first = r["affixes"][0]
    assert first["affix_kind"] == "numeric"
    assert first["numeric_values"][0]["min"] == 287.0
    assert first["numeric_values"][0]["max"] == 372.0
    assert first["expression"] == "+(#) Max Life"


def test_tier_and_weight_stored():
    r = import_crawler_graft(_GRAFT)
    first = r["affixes"][0]
    assert first["tier"] == "0+"
    assert first["level"] == 1
    assert first["weight"] == 0
    assert first["affix_type"] == "Basic Affix"


def test_weight_as_int():
    r = import_crawler_graft(_GRAFT)
    # tier "0" has weight "1" in source → should be int 1
    assert r["affixes"][1]["weight"] == 1


def test_special_affix():
    r = import_crawler_graft(_GRAFT)
    immune = r["affixes"][4]
    assert immune["affix_kind"] == "special"
    assert immune["affix_type"] == "Implicit Affix"


def test_import_crawler_grafts_filters_nameless():
    items = [_GRAFT, {"craft_affixes": []}]
    result = import_crawler_grafts(items)
    assert len(result) == 1
    assert result[0]["item_id"] == "vorax_aberrant_limb_digits"
