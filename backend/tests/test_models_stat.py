"""
Tests: models/stat.py — Stat enum integrity.
Scope: enum structure only; no meta or pool lookups.
"""
import pytest
from models.stat import Stat


def _all_values():
    return [s.value for s in Stat]


def test_all_values_are_strings():
    for s in Stat:
        assert isinstance(s.value, str), f"{s.name} value is not a str"


def test_no_duplicate_values():
    values = _all_values()
    seen = set()
    for v in values:
        assert v not in seen, f"Duplicate Stat value: '{v}'"
        seen.add(v)


def test_values_are_snake_case():
    """All enum values follow lower_snake_case convention."""
    import re
    pattern = re.compile(r"^[a-z][a-z0-9_]*$")
    for s in Stat:
        assert pattern.match(s.value), (
            f"Stat.{s.name} value '{s.value}' is not snake_case"
        )


def test_enum_lookup_by_value():
    """Stat('strength') should resolve back to Stat.STRENGTH."""
    assert Stat("strength") is Stat.STRENGTH
    assert Stat("dmg_inc") is Stat.DMG_INC
