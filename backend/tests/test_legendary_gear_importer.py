import pytest
from tools.legendary_gear_importer import parse_affix_text, import_crawler_item


# ── parse_affix_text ────────────────────────────────────────────────────────

def test_placeholder():
    r = parse_affix_text("<A Random Attack Sentry or Spell Sentry Affix>", None)
    assert r["affix_kind"] == "placeholder"
    assert r["numeric_values"] == []
    assert r["condition"] is None
    assert r["expression"] == "<A Random Attack Sentry or Spell Sentry Affix>"


def test_signed_range():
    r = parse_affix_text("+(10–16) % Max Life and Max Energy Shield", "53421621")
    assert r["affix_kind"] == "numeric"
    assert len(r["numeric_values"]) == 1
    nv = r["numeric_values"][0]
    assert nv["kind"] == "range"
    assert nv["sign"] == "+"
    assert nv["min"] == 10.0
    assert nv["max"] == 16.0
    assert r["expression"] == "+(#) % Max Life and Max Energy Shield"
    assert r["modifier_id"] == "53421621"


def test_unsigned_range():
    r = parse_affix_text("Restores (0.5–3) % Life when a Sentry lands a Critical Strike", None)
    assert r["affix_kind"] == "numeric"
    nv = r["numeric_values"][0]
    assert nv["kind"] == "range"
    assert nv["sign"] == ""
    assert nv["min"] == 0.5
    assert nv["max"] == 3.0


def test_signed_fixed():
    r = parse_affix_text("+20 % Movement Speed", None)
    assert r["affix_kind"] == "numeric"
    nv = r["numeric_values"][0]
    assert nv["kind"] == "fixed"
    assert nv["sign"] == "+"
    assert nv["value"] == 20.0
    assert r["expression"] == "+# % Movement Speed"


def test_negative_fixed():
    r = parse_affix_text("-20 % Terra Skill Duration", None)
    assert r["affix_kind"] == "numeric"
    nv = r["numeric_values"][0]
    assert nv["kind"] == "fixed"
    assert nv["sign"] == "-"
    assert nv["value"] == 20.0


def test_special_no_numerics():
    r = parse_affix_text("Enemies within 8m receive Timid Curse", None)
    assert r["affix_kind"] == "special"
    assert r["numeric_values"] == []


def test_condition_split():
    r = parse_affix_text("Restores (0.5–3) % Life when a Sentry lands a Critical Strike", None)
    assert r["condition"] is not None
    assert "when" in r["condition"].lower()


def test_bare_number_not_extracted():
    r = parse_affix_text("Summons a Lv. 20 Flame Sentry", None)
    assert r["numeric_values"] == []
    assert r["affix_kind"] == "special"


# ── import_crawler_item ─────────────────────────────────────────────────────

_SAMPLE_ITEM = {
    "name": "Imperial Iron Sentry",
    "internal_id": 112216,
    "base_type": "Long Night Sorcerer's Mask",
    "required_level": 58,
    "drop_level": 58,
    "flavor_text": None,
    "drop_sources": ["Drops everywhere in Netherrealm"],
    "variants": [
        {
            "season": "SS12Season",
            "rarity_state": "base",
            "implicits": ["+146 gear Energy Shield"],
            "explicits": [
                {"modifier_id": "53421621", "text": "+(10–16) % Max Life and Max Energy Shield"},
                {"modifier_id": None, "text": "<A Random Attack Sentry or Spell Sentry Affix>"},
            ],
        },
        {
            "season": "corroded",
            "rarity_state": "corroded",
            "implicits": [],
            "explicits": [
                {"modifier_id": "53421621", "text": "+(8–14) % Max Life and Max Energy Shield"},
            ],
        },
    ],
    "random_affixes": [
        {
            "placeholder": "<A Random Attack Sentry or Spell Sentry Affix>",
            "rarity_state": "base",
            "options": [
                {"modifier_id": "53421681", "text": "Sentries can perform Multistrike +(60–70) % additional damage"},
            ],
        }
    ],
    "glossary": [{"term_id": "102", "name": "Nearby", "description": "Within 6m"}],
}


def test_both_variants_stored():
    result = import_crawler_item(_SAMPLE_ITEM)
    assert "base" in result["variants"]
    assert "corroded" in result["variants"]
    base = result["variants"]["base"]
    assert len(base["implicits"]) == 1
    assert len(base["explicits"]) == 2


def test_random_affixes_parsed():
    result = import_crawler_item(_SAMPLE_ITEM)
    ra = result["random_affixes"]
    assert "base" in ra
    pool = ra["base"]
    assert len(pool) == 1
    assert pool[0]["placeholder"] == "<A Random Attack Sentry or Spell Sentry Affix>"
    opts = pool[0]["options"]
    assert len(opts) == 1
    assert opts[0]["affix_kind"] == "numeric"
    assert opts[0]["modifier_id"] == "53421681"
