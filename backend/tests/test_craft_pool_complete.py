"""Completeness of the active season's craft base pools.

SS14 shipped with most craft pool rows missing and nothing noticed. These tests
read the hydrated dataset through the endpoint the renderer uses
(`server.get_craft_base_types`), so a short craft import fails here.

Expected counts come from the corrected SS14 import (Two-Handed Sword: 136
prefix / 140 suffix rows; every base 86-180 prefix and 98-156 suffix rows).
The floors below sit well under those minimums so ordinary re-imports pass.
"""
import pytest

import server

EXPECTED_BASE_COUNT = 38
PREFIX_FLOOR = 60   # fixed data minimum: 86
SUFFIX_FLOOR = 70   # fixed data minimum: 98
GROUPS = ("Basic", "Advanced", "Ultimate")
PREFIX_TYPES = tuple(f"{g} Pre-fix" for g in GROUPS)
SUFFIX_TYPES = tuple(f"{g} Suffix" for g in GROUPS)


@pytest.fixture(scope="module")
def bases():
    result = server.get_craft_base_types()
    assert result["season"], "no active season hydrated; run `npm run fetch:data`"
    return {b["name"]: b for b in result["base_types"]}


def _rows(base, affix_type):
    return [a for a in base["affixes"] if a.get("affix_type") == affix_type]


def test_all_craft_bases_present(bases):
    assert len(bases) == EXPECTED_BASE_COUNT
    for name in ("Two-Handed Sword", "Bow", "Belt", "Ring", "Spirit Ring", "Wand",
                 "STR Helmet", "DEX Shield", "INT Boots"):
        assert name in bases


def test_every_base_has_all_prefix_and_suffix_groups(bases):
    missing = {
        name: [t for t in PREFIX_TYPES + SUFFIX_TYPES if not _rows(base, t)]
        for name, base in bases.items()
    }
    assert {n: m for n, m in missing.items() if m} == {}


def test_every_base_meets_prefix_and_suffix_floor(bases):
    short = {}
    for name, base in bases.items():
        prefixes = sum(len(_rows(base, t)) for t in PREFIX_TYPES)
        suffixes = sum(len(_rows(base, t)) for t in SUFFIX_TYPES)
        if prefixes < PREFIX_FLOOR or suffixes < SUFFIX_FLOOR:
            short[name] = (prefixes, suffixes)
    assert short == {}


def test_two_handed_sword_row_counts(bases):
    base = bases["Two-Handed Sword"]
    assert sum(len(_rows(base, t)) for t in PREFIX_TYPES) == 136
    assert sum(len(_rows(base, t)) for t in SUFFIX_TYPES) == 140


def test_basic_prefix_pool_has_physical_damage_mod(bases):
    expressions = {a["expression"] for a in _rows(bases["Two-Handed Sword"], "Basic Pre-fix")}
    assert "Adds # - # Physical Damage to the gear" in expressions


def test_tiers_are_not_all_zero(bases):
    flat = {
        name: sorted({str(a.get("tier")) for a in base["affixes"]
                      if a.get("affix_type") in PREFIX_TYPES + SUFFIX_TYPES})
        for name, base in bases.items()
    }
    assert {n: t for n, t in flat.items() if set(t) <= {"0"}} == {}
