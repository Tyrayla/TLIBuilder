import pytest
from tools.skill_importer import import_crawler_skill, import_crawler_skills, merge_skills

_ACTIVE = {
    "name": "Aegis of Fire",
    "internal_id": 12345,
    "skill_type": "active_skill",
    "variants": [
        {
            "season": "SS12Season",
            "max_level": 20,
            "tags": ["Spell", "Persistent", "Fire", "Defensive"],
            "weapon_restriction": None,
            "main_stat": None,
            "mana_cost": "15",
            "cast_speed": "1 s",
            "effectiveness_of_added_damage": "100%",
            "simple_description": "Casts the skill and gains a defensive effect.",
            "detailed_description": "Casts the skill and gains defensive effect: 27.5 % Attack Block Chance.",
        }
    ],
    "progression": [{"level": 1, "values": {"dmg": "100%"}}],
    "glossary": [
        {"term_id": "42", "name": "Block", "description": "Prevents damage."}
    ],
}


def test_item_id_slug():
    r = import_crawler_skill(_ACTIVE)
    assert r["item_id"] == "aegis_of_fire"


def test_name_preserved():
    r = import_crawler_skill(_ACTIVE)
    assert r["name"] == "Aegis of Fire"


def test_skill_tags_from_variant():
    r = import_crawler_skill(_ACTIVE)
    assert r["skill_tags"] == ["Spell", "Persistent", "Fire", "Defensive"]


def test_description_lines_from_simple_description():
    r = import_crawler_skill(_ACTIVE)
    assert r["description_lines"] == ["Casts the skill and gains a defensive effect."]


def test_raw_text_from_detailed_description():
    r = import_crawler_skill(_ACTIVE)
    assert "27.5 % Attack Block Chance" in r["raw_text"]


def test_skill_type_stored():
    r = import_crawler_skill(_ACTIVE)
    assert r["skill_type"] == "active_skill"


def test_progression_stored():
    r = import_crawler_skill(_ACTIVE)
    assert len(r["progression"]) == 1
    assert r["progression"][0]["level"] == 1


def test_glossary_list_to_dict():
    r = import_crawler_skill(_ACTIVE)
    assert "42" in r["glossary"]
    assert r["glossary"]["42"]["name"] == "Block"


def test_import_crawler_skills_filters_nameless():
    items = [_ACTIVE, {"internal_id": 0, "skill_type": "active_skill"}]
    result = import_crawler_skills(items)
    assert len(result) == 1
    assert result[0]["name"] == "Aegis of Fire"


def test_merge_deduplicates_by_item_id():
    old = import_crawler_skills([_ACTIVE])
    updated = {**_ACTIVE, "variants": [{**_ACTIVE["variants"][0], "mana_cost": "20"}]}
    new = import_crawler_skills([updated])
    merged = merge_skills(old, new)
    assert len(merged) == 1
    assert merged[0]["mana_cost"] == "20"
