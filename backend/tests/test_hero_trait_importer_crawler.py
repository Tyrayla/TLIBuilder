import pytest
from engine.modifier_lines import line_text
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
    # Effects are stored as slim modifier-line dicts ({text, uuid, pooling_uuid, modifier_id}).
    r = import_crawler_hero_trait(_ANGER)
    assert [line_text(e) for e in r["levels"][0]["effects"]] == ["0.22 % additional damage per 1 Rage"]
    assert r["levels"][0]["unlock_level"] == 1


def test_artificial_moon_extracted():
    r = import_crawler_hero_trait(_ANGER)
    am = r["artificial_moon"]
    assert len(am["effects"]) == 1
    assert "Artificial Moon" in line_text(am["effects"][0])
    assert "+1.5 % Burst Speed" in line_text(am["effects"][0])


def test_artificial_moon_removed_from_level():
    r = import_crawler_hero_trait(_ANGER)
    # Level 5 description should have AM stripped
    assert "Artificial Moon" not in line_text(r["levels"][4]["effects"][0])


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


# Regression: an ADVANCED node can also carry a per-level `levels` array (its tier scaling, with description=None).
# The old importer detected the base by "has levels" and dropped these. They must survive and take effects from
# levels[*].description. (Matches real data: Wind Stalker / Cat's Punches, Zealot of War / Ceasefire, etc.)
_LEVELED_ADV = {
    "name": "Wind Stalker",
    "max_level": 8,
    "traits": [
        {"name": "Wind Stalker", "required_level": 1,
         "levels": [{"level": 1, "description": "+26 % Movement Speed"}], "description": None,
         "icon_url": "https://cdn.tlidb.com/UI/Textures/Common/Icon/Skill/HeroTraits/Erika/x.webp"},
        {"name": "Cat Dive", "required_level": 75, "levels": [],
         "description": "Proc chance to deal max Multistrike", "icon_url": ""},
        {"name": "Cat's Punches", "required_level": 75, "description": None,
         "levels": [{"level": 1, "description": "punch L1"}, {"level": 2, "description": "punch L2"}],
         "icon_url": ""},
    ],
    "glossary": [],
}


def test_leveled_advanced_node_not_dropped():
    r = import_crawler_hero_trait(_LEVELED_ADV)
    names = [t["name"] for t in r["advanced_traits"]]
    assert "Cat's Punches" in names and "Cat Dive" in names
    assert len(r["advanced_traits"]) == 2


def test_leveled_advanced_node_effects_collapsed_to_tier_syntax():
    # Per-level descriptions collapse to ONE line with (a/b/...) tier syntax (the differing token only).
    r = import_crawler_hero_trait(_LEVELED_ADV)
    punches = next(t for t in r["advanced_traits"] if t["name"] == "Cat's Punches")
    assert [line_text(e) for e in punches["effects"]] == ["punch (L1/L2)"]
    assert punches["unlock_level"] == 75


def test_leveled_advanced_base_and_hero_still_correct():
    r = import_crawler_hero_trait(_LEVELED_ADV)
    assert r["hero"] == "Erika"
    assert len(r["levels"]) == 1  # the required_level==1 base, not the advanced nodes


# Regression: `icon_url` can be JSON `null` (key present, value None) — not just absent — for
# entities tlidb hasn't backfilled yet at season launch (matches the real crawled Dance of the
# Deep shape). Pre-fix, the importer read the icon with `base.get("icon_url", "")`: the default
# only substitutes when the KEY is missing, not when it's present with value None, so this
# returned None. That None was then fed straight into `_HERO_RE.search(None)`, which raises
# `TypeError: expected string or bytes-like object` — the whole import of the trait would blow up
# before this test's assertions were ever reached. The fix null-coalesces with `... or ""` at both
# the base-trait site and the advanced-node loop, so a null icon degrades to "" (no hero-from-icon)
# instead of crashing the import.
_NULL_ICON_TRAIT = {
    "name": "Dance of the Deep",
    "max_level": 8,
    "traits": [
        {
            "name": "Dance of the Deep",
            "required_level": 1,
            "levels": [{"level": 1, "description": "some base effect"}],
            "description": None,
            "icon_url": None,
        },
        {
            "name": "Undertow",
            "required_level": 45,
            "levels": [],
            "description": "some advanced effect",
            "icon_url": None,
        },
    ],
    "glossary": [],
}


def test_null_icon_url_on_base_and_advanced_node_does_not_raise():
    # Would have raised TypeError pre-fix (see comment above) — reaching these asserts at all is
    # part of the regression coverage.
    r = import_crawler_hero_trait(_NULL_ICON_TRAIT)
    assert r["trait_id"] == "dance_of_the_deep"
    assert r["hero"] == ""
    assert r["icon_url"] == ""


def test_null_icon_url_advanced_node_degrades_gracefully():
    r = import_crawler_hero_trait(_NULL_ICON_TRAIT)
    assert len(r["advanced_traits"]) == 1
    adv = r["advanced_traits"][0]
    assert adv["name"] == "Undertow"
    assert adv["icon_url"] == ""


def test_null_icon_url_trait_still_produced_not_dropped():
    result = import_crawler_hero_traits([_NULL_ICON_TRAIT])
    assert len(result) == 1
    assert result[0]["trait_id"] == "dance_of_the_deep"
