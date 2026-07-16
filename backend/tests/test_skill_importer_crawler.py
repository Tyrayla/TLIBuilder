import pytest
from engine.modifier_lines import line_texts
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
            "cooldown": "6 s",
            "icon_url": "https://cdn.tlidb.com/icon.webp",
            "effectiveness_of_added_damage": "100%",
            "simple_description": "Casts the skill and gains a defensive effect.",
            "detailed_description": ["Casts the skill and gains defensive effect: 27.5 % Attack Block Chance.",
                                     "Lasts 5 s."],
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
    # Stored as slim modifier-line dicts; text is the display/parse surface.
    r = import_crawler_skill(_ACTIVE)
    assert line_texts(r["description_lines"]) == ["Casts the skill and gains a defensive effect."]


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


def test_cooldown_stored():
    r = import_crawler_skill(_ACTIVE)
    assert r["cooldown"] == "6 s"


def test_charges_one_when_cooldown():
    r = import_crawler_skill(_ACTIVE)
    assert r["charges"] == 1


def test_charges_none_without_cooldown():
    no_cd = {**_ACTIVE, "variants": [{**_ACTIVE["variants"][0], "cooldown": None}]}
    assert import_crawler_skill(no_cd)["charges"] is None


def test_duration_parsed_from_lasts_line():
    r = import_crawler_skill(_ACTIVE)
    assert r["duration"] == 5.0


def test_duration_ignores_embedded_lasts():
    # An embedded sub-entity "lasts" must not be the skill SCALAR duration — but it IS captured as an entity entry.
    embedded = {**_ACTIVE, "variants": [{**_ACTIVE["variants"][0],
                "detailed_description": ["Remnant lasts 0.65s.", "You can have up to 2 Remnant(s)."]}]}
    r = import_crawler_skill(embedded)
    assert r["duration"] is None
    ent = [d for d in r["durations"] if d["kind"] == "entity"]
    assert ent and ent[0]["seconds"] == 0.65 and ent[0]["subject"] == "Remnant"


def test_durations_skill_entry():
    r = import_crawler_skill(_ACTIVE)
    sk = [d for d in r["durations"] if d["kind"] == "skill"]
    assert sk and sk[0]["seconds"] == 5.0


def test_durations_per_stack_with_max_stacks():
    ps = {**_ACTIVE, "variants": [{**_ACTIVE["variants"][0],
          "detailed_description": ["2.5 % additional Spell Damage, up to 8 stacks, lasting for 1.2 s"]}]}
    r = import_crawler_skill(ps)
    entry = [d for d in r["durations"] if d["kind"] == "per_stack"]
    assert entry and entry[0]["seconds"] == 1.2 and entry[0]["max_stacks"] == 8


def test_durations_interval():
    iv = {**_ACTIVE, "variants": [{**_ACTIVE["variants"][0],
          "detailed_description": ["The Black Hole knocks back enemies inside of it every 0.5 s."]}]}
    r = import_crawler_skill(iv)
    entry = [d for d in r["durations"] if d["kind"] == "interval"]
    assert entry and entry[0]["seconds"] == 0.5


def test_icon_url_stored():
    r = import_crawler_skill(_ACTIVE)
    assert r["icon_url"] == "https://cdn.tlidb.com/icon.webp"


def test_merge_deduplicates_by_item_id():
    old = import_crawler_skills([_ACTIVE])
    updated = {**_ACTIVE, "variants": [{**_ACTIVE["variants"][0], "mana_cost": "20"}]}
    new = import_crawler_skills([updated])
    merged = merge_skills(old, new)
    assert len(merged) == 1
    assert merged[0]["mana_cost"] == "20"
