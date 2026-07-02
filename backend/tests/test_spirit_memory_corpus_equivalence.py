"""Corpus-equivalence guard for the spirit/memory resolver unification.

For EVERY real SS12 pact-spirit / hero-memory effect string, the unified server._resolve_effect_modifiers
must resolve to the SAME stat_key(s) the old _MEMORY_STAT_LOOKUP resolver did — except a small, explicit
allowlist of Tyra-approved improvements (the derived→_flat attribute/defense scaling fix). No old-resolved
effect may silently change category or become NYI. Category is derived from the resolved stat_key's
StatMeta, so identical stat_keys ⇒ identical category.

The baseline fixture (tests/fixtures/spirit_memory_baseline.json) was captured from the OLD resolver before
the refactor; it is the frozen "old" side of the comparison.
"""
import json
import os

import pytest

from server import _resolve_effect_modifiers

_BASELINE = os.path.join(os.path.dirname(__file__), "fixtures", "spirit_memory_baseline.json")

# Tyra-approved intentional shifts: the old resolver mapped flat attributes/defense to the DERIVED stat
# (bypassing % increased scaling — a bug); the unified path routes them to the _flat stat that scales
# correctly, matching how gear/custom already resolve the same text. Same category, corrected scaling.
APPROVED_SHIFTS = {
    ("dexterity",):    ("dexterity_flat",),
    ("intelligence",): ("intelligence_flat",),
    ("strength",):     ("strength_flat",),
    ("armor",):        ("armor_flat",),
    ("evasion",):      ("evasion_flat",),
    # "Mana Regeneration Speed" stat renamed mana_regen_inc → mana_regen_speed_inc (now a true rate multiplier in
    # recovery, mirroring life_regen_speed_inc — not a flat %-of-max/sec addition).
    ("mana_regen_inc",): ("mana_regen_speed_inc",),
}


def _new(effect: str, is_memory: bool) -> tuple[str, ...]:
    return tuple(sorted(d["stat_key"] for d in _resolve_effect_modifiers(effect, is_memory=is_memory)))


def _cases():
    base = json.load(open(_BASELINE, encoding="utf-8"))
    out = []
    for kind, is_mem in (("spirit", False), ("memory", True)):
        for effect, old in base[kind].items():
            out.append((kind, is_mem, effect, tuple(sorted(old["stat_keys"]))))
    return out


@pytest.mark.parametrize("kind,is_mem,effect,old_keys", _cases())
def test_no_regression(kind, is_mem, effect, old_keys):
    """Every old-RESOLVED effect resolves identically (or via an approved derived→flat shift). Old-NYI
    effects are free to improve (gaining coverage is the goal)."""
    if not old_keys:
        return  # old was NYI → new may resolve (improvement); not a regression
    new_keys = _new(effect, is_mem)
    if new_keys == old_keys:
        return
    assert APPROVED_SHIFTS.get(old_keys) == new_keys, (
        f"[{kind}] {effect!r}: old={old_keys} new={new_keys} — unapproved change "
        f"(silent regression or category shift)")


def test_no_old_resolved_became_nyi():
    base = json.load(open(_BASELINE, encoding="utf-8"))
    lost = [(kind, effect)
            for kind, is_mem in (("spirit", False), ("memory", True))
            for effect, old in base[kind].items()
            if old["stat_keys"] and not _resolve_effect_modifiers(effect, is_memory=is_mem)]
    assert not lost, f"{len(lost)} old-resolved effects became NYI (regression): {lost[:10]}"
