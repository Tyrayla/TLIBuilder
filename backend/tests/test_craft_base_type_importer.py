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


_SWORD_WITH_SUFFIX_TIERS = {
    "name": "One-Handed Sword",
    "all_affixes": [
        # Single tier-1 representative — must be IGNORED when craft_suffix_affixes is present.
        {"Affix Effect": "+(77–108) % Elemental Damage", "Source": "One-Handed Sword", "Type": "Basic Suffix"},
    ],
    "craft_suffix_affixes": [
        {"Tier": "0", "Modifier": "+(109–140) % Elemental Damage", "Lv": "100", "Weight": "0", "Library": "Basic Affix"},
        {"Tier": "1", "Modifier": "+(77–108) % Elemental Damage", "Lv": "86", "Weight": "100", "Library": "Basic Affix"},
        {"Tier": "2", "Modifier": "+(55–76) % Elemental Damage", "Lv": "70", "Weight": "100", "Library": "Basic Affix"},
    ],
}


def test_craft_suffix_affixes_gives_full_tiers():
    r = import_crawler_craft_base_type(_SWORD_WITH_SUFFIX_TIERS)
    suffix = [a for a in r["affixes"] if a["affix_type"] == "Basic Suffix"]
    # Three tiers from craft_suffix_affixes — NOT the single all_affixes fallback.
    assert sorted(a["tier"] for a in suffix) == ["0", "1", "2"]
    assert all(a["source"] == "One-Handed Sword" for a in suffix)


def test_craft_suffix_library_maps_to_suffix_type():
    r = import_crawler_craft_base_type(_SWORD_WITH_SUFFIX_TIERS)
    # "Basic Affix" library in the suffix table → "Basic Suffix" type (not "Basic Pre-fix").
    assert all(a["affix_type"] == "Basic Suffix" for a in r["affixes"] if a["affix_type"].endswith("Suffix"))
    assert not any(a["affix_type"].endswith("Pre-fix") for a in r["affixes"])


def test_all_affixes_suffix_fallback_when_no_craft_suffix():
    # Older crawler output without craft_suffix_affixes → fall back to the single tier-0 all_affixes entry.
    legacy = {"name": "Old Base", "all_affixes": [
        {"Affix Effect": "+(77–108) % Elemental Damage", "Source": "Old Base", "Type": "Basic Suffix"}]}
    r = import_crawler_craft_base_type(legacy)
    suffix = [a for a in r["affixes"] if a["affix_type"] == "Basic Suffix"]
    assert len(suffix) == 1 and suffix[0]["tier"] == "0"


def test_import_crawler_craft_base_types_filters_nameless():
    items = [_BELT, {"all_affixes": []}]
    result = import_crawler_craft_base_types(items)
    assert len(result) == 1
    assert result[0]["item_id"] == "belt"
