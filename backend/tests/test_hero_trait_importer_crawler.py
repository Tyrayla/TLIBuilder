import pytest
from tools.hero_trait_importer import import_crawler_hero_trait, import_crawler_hero_traits

_ANGER = {
    "name": "Anger",
    "max_level": 8,
    "traits": [
        {
            "name": "Anger",
            "required_level": 1,
            "levels": [
                {"level": 1, "description": "0.22 % additional damage per 1 Rage"},
                {"level": 2, "description": "0.24 % additional damage per 1 Rage"},
                {"level": 3, "description": "0.26 % additional damage per 1 Rage"},
                {"level": 4, "description": "0.28 % additional damage per 1 Rage"},
                {"level": 5, "description": "0.30 % additional damage per 1 Rage Artificial Moon: +1.5 % Burst Speed"},
            ],
            "description": None,
            "icon_url": "https://cdn.tlidb.com/UI/Textures/Common/Icon/Skill/HeroTraits/Rehan/YeManRen502.webp",
        },
        {
            "name": "Righteous Fury",
            "required_level": 45,
            "levels": [],
            "description": "Generates 18 Rage per second instead of consuming Rage while Berserk",
            "icon_url": "",
        },
        {
            "name": "Frenzy Furious",
            "required_level": 45,
            "levels": [],
            "description": "0.3 % Critical Strike Rating for every 1 Rage",
            "icon_url": "",
        },
        {
            "name": "Tunnel Vision",
            "required_level": 60,
            "levels": [],
            "description": "-80 % additional damage for non-Burst skills",
            "icon_url": "",
        },
        {
            "name": "Rampaging",
            "required_level": 75,
            "levels": [],
            "description": "70 % of Attack Speed bonus applied to Burst Cooldown",
            "icon_url": "",
        },
        {
            "name": "Uncontrolled Anger",
            "required_level": 75,
            "levels": [],
            "description": "+200 % additional Burst Area",
            "icon_url": "",
        },
    ],
    "glossary": [
        {"term_id": "614", "name": "Rage", "description": "Berserker exclusive energy."},
        {"term_id": "615", "name": "Berserk", "description": "Bonus state at max Rage."},
    ],
}


def test_trait_id_slug():
    r = import_crawler_hero_trait(_ANGER)
    assert r["trait_id"] == "anger"


def test_hero_extracted_from_icon_url():
    r = import_crawler_hero_trait(_ANGER)
    assert r["hero"] == "Rehan"


def test_variant_name():
    r = import_crawler_hero_trait(_ANGER)
    assert r["variant_name"] == "Anger"


def test_levels_count():
    r = import_crawler_hero_trait(_ANGER)
    assert len(r["levels"]) == 5


def test_level_effects_stored():
    r = import_crawler_hero_trait(_ANGER)
    assert r["levels"][0]["effects"] == ["0.22 % additional damage per 1 Rage"]
    assert r["levels"][0]["unlock_level"] == 1


def test_artificial_moon_extracted():
    r = import_crawler_hero_trait(_ANGER)
    am = r["artificial_moon"]
    assert len(am["effects"]) == 1
    assert "Artificial Moon" in am["effects"][0]
    assert "+1.5 % Burst Speed" in am["effects"][0]


def test_artificial_moon_removed_from_level():
    r = import_crawler_hero_trait(_ANGER)
    # Level 5 description should have AM stripped
    assert "Artificial Moon" not in r["levels"][4]["effects"][0]


def test_advanced_traits_count():
    r = import_crawler_hero_trait(_ANGER)
    assert len(r["advanced_traits"]) == 5


def test_is_pick_one_from_two_at_same_unlock_level():
    r = import_crawler_hero_trait(_ANGER)
    lv45 = [t for t in r["advanced_traits"] if t["unlock_level"] == 45]
    lv60 = [t for t in r["advanced_traits"] if t["unlock_level"] == 60]
    lv75 = [t for t in r["advanced_traits"] if t["unlock_level"] == 75]
    assert all(t["is_pick_one_from_two"] for t in lv45)
    assert not lv60[0]["is_pick_one_from_two"]
    assert all(t["is_pick_one_from_two"] for t in lv75)


def test_glossary_list_to_dict():
    r = import_crawler_hero_trait(_ANGER)
    assert "614" in r["glossary"]
    assert r["glossary"]["614"]["name"] == "Rage"


def test_max_level_stored():
    r = import_crawler_hero_trait(_ANGER)
    assert r["max_level"] == 8


def test_import_crawler_hero_traits_filters_nameless():
    items = [_ANGER, {"max_level": 5}]
    result = import_crawler_hero_traits(items)
    assert len(result) == 1
    assert result[0]["trait_id"] == "anger"
