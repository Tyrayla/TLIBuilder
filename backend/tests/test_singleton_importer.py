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
    "fixed_affixes": [
        {"Tier": "1", "Modifier": "+2 to Hero Trait Level", "Level": "86", "Weight": "103", "Source": "Memory of Origin"},
    ],
    "random_affixes": [
        {"Tier": "0", "Modifier": "+(39–45) % Skill Area", "Level": "86", "Weight": "1000", "Source": "Memory of Origin"},
        {"Tier": "1", "Modifier": "+32 % Skill Area", "Level": "86", "Weight": "2000", "Source": "Memory of Origin"},
    ],
    "base_stats": [
        {"Tier": "1", "Modifier": "+90 Strength", "Level": "1", "Weight": "0", "Source": "Memory of Origin"},
        {"Tier": "2", "Modifier": "+88 Strength", "Level": "1", "Weight": "0", "Source": "Memory of Origin"},
    ],
    "memory_types": [
        {"name": "Memory of Origin", "url_path": "/en/Memory_of_Origin", "internal_id": 71001, "icon_url": "https://cdn.tlidb.com/icon.webp"},
    ],
    "glossary": [],
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


def test_hero_memories_new_format():
    r = import_hero_memories(_HERO_MEM_DATA, "SS12")
    assert r["season"] == "SS12"
    assert r["affix_count"] == 5  # 1 fixed + 2 random + 2 base_stats
    assert len(r["fixed_affixes"]) == 1
    assert len(r["random_affixes"]) == 2
    assert len(r["base_stats"]) == 2
    assert r["fixed_affixes"][0]["modifier"] == "+2 to Hero Trait Level"
    assert r["fixed_affixes"][0]["tier"] == 1
    assert r["fixed_affixes"][0]["source"] == "Memory of Origin"
    assert r["random_affixes"][0]["tier"] == 0
    assert r["base_stats"][0]["modifier"] == "+90 Strength"
    assert r["memory_types"][0]["name"] == "Memory of Origin"
    assert r["memory_types"][0]["internal_id"] == 71001


def test_hero_memories_normalizes_modifiers():
    """Reimport safety: modifiers missing '+' or starting lowercase must be normalized."""
    data = {
        "fixed_affixes": [
            # lowercase first letter — common crawler output issue
            {"Tier": "1", "Modifier": "attack Critical Strike Damage", "Level": "86", "Weight": "615", "Source": "Memory of Progress"},
        ],
        "random_affixes": [],
        "base_stats": [
            # digit-start without '+' — the Memory of Progress base stat bug
            {"Tier": "1",  "Modifier": "90 Strength",      "Level": "1", "Weight": "0", "Source": "Memory of Progress"},
            {"Tier": "20", "Modifier": "35.2 % Attack Speed", "Level": "1", "Weight": "0", "Source": "Memory of Progress"},
        ],
        "memory_types": [],
    }
    r = import_hero_memories(data, "SS12")
    assert r["fixed_affixes"][0]["modifier"] == "Attack Critical Strike Damage"
    assert r["base_stats"][0]["modifier"] == "+90 Strength"
    assert r["base_stats"][1]["modifier"] == "+35.2 % Attack Speed"


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
