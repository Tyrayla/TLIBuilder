import pytest
from tools.singleton_importer import (
    import_destiny,
    import_ethereal_prism,
    import_hero_memories,
    import_memory_revival,
    import_tower_sequence,
)

_DESTINY_DATA = {
    "entity_type": "destiny",
    "sections": [
        {
            "header": "Item /3",
            "items": [
                {"name": "Micro Fate: Fire Resistance", "text": "Micro Fate: Fire Resistance +(5–7) % Fire Resistance"},
                {"name": "Micro Fate: Cold Resistance", "text": "Micro Fate: Cold Resistance +(5–7) % Cold Resistance"},
                {"name": "", "text": "nameless item should be filtered"},
            ],
        }
    ],
}

_ETHEREAL_DATA = {
    "entity_type": "ethereal_prism",
    "sections": [{"header": "Base Affix /2", "columns": ["Modifier"], "items": [
        {"Modifier": "Adds an additional effect to the Core Talent: +12 % Attack Damage"},
        {"Modifier": "Adds an additional effect: +12 % Spell Damage"},
    ]}],
}

_HERO_MEM_DATA = {
    "entity_type": "hero_memories",
    "sections": [{"header": "Affix /2", "columns": ["Affix Effect", "Source", "Type"], "items": [
        {"Affix Effect": "+90 Strength", "Source": "Memory of Origin", "Type": "Base Stats"},
        {"Affix Effect": "+90 Dexterity", "Source": "Memory of Origin", "Type": "Base Stats"},
    ]}],
}

_REVIVAL_DATA = {
    "entity_type": "memory_revival",
    "sections": [{"header": "Revived Affix /2", "columns": ["Tier", "Modifier", "Level", "Weight"], "items": [
        {"Tier": "1", "Modifier": "+(75–80) % Elixir Skill Effect", "Level": "82", "Weight": "1000"},
        {"Tier": "2", "Modifier": "+(60–63) % Elixir Skill Effect", "Level": "82", "Weight": "1000"},
    ]}],
}

_TOWER_DATA = {
    "entity_type": "tower_sequence",
    "sections": [{"header": "TOWER Sequence /2", "columns": ["Affix", "Source"], "items": [
        {"Affix": "+8 % additional damage for Main-Hand Weapons", "Source": "Claw"},
        {"Affix": "+8 % additional damage for Main-Hand Weapons", "Source": "Cane"},
    ]}],
}


def test_destiny_flattens_items():
    r = import_destiny(_DESTINY_DATA, "SS12")
    assert r["item_count"] == 2  # nameless filtered
    assert r["items"][0]["name"] == "Micro Fate: Fire Resistance"


def test_destiny_season_stored():
    r = import_destiny(_DESTINY_DATA, "SS12")
    assert r["season"] == "SS12"


def test_ethereal_prism_flattens_modifiers():
    r = import_ethereal_prism(_ETHEREAL_DATA, "SS12")
    assert r["modifier_count"] == 2
    assert "Core Talent" in r["modifiers"][0]


def test_hero_memories_renames_columns():
    r = import_hero_memories(_HERO_MEM_DATA, "SS12")
    assert r["affix_count"] == 2
    affix = r["affixes"][0]
    assert affix["effect"] == "+90 Strength"
    assert affix["source"] == "Memory of Origin"
    assert affix["affix_type"] == "Base Stats"


def test_memory_revival_converts_ints():
    r = import_memory_revival(_REVIVAL_DATA, "SS12")
    assert r["affix_count"] == 2
    first = r["affixes"][0]
    assert first["tier"] == 1
    assert first["level"] == 82
    assert first["weight"] == 1000
    assert "Elixir" in first["modifier"]


def test_tower_sequence_flattens():
    r = import_tower_sequence(_TOWER_DATA, "SS12")
    assert r["entry_count"] == 2
    assert r["entries"][0]["source"] == "Claw"
    assert "damage" in r["entries"][0]["affix"]


def test_multi_section_flattened():
    data = {
        "entity_type": "destiny",
        "sections": [
            {"header": "Section A", "items": [{"name": "A", "text": "text A"}]},
            {"header": "Section B", "items": [{"name": "B", "text": "text B"}]},
        ],
    }
    r = import_destiny(data, "SS12")
    assert r["item_count"] == 2
    assert r["items"][1]["name"] == "B"
