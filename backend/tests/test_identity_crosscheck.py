"""One-season dev cross-check: every stored minted identity recomputes from its stored text.

For every modifier line in the SS12 season data that carries a `pooling_uuid`, assert
`uuid5(NAMESPACE, affix_identity(text)) == pooling_uuid`. This mechanically enforces the
uuid-carry rule from the importers (engine/modifier_lines.slim_checked): ids ride along only
through value-only text transforms; any wording-changing transform must store null ids. A failure
here means an importer stored a LYING identity — fix the importer to null the ids, never relax
this test.

The walk is schema-agnostic: any dict carrying a non-null `pooling_uuid` plus one of the known
text keys (effect_raw / raw_text / text / modifier — first present wins) is checked, so new
identity-carrying surfaces are covered automatically.

DELETE AT SS13 (per the migration plan): once the uuid switch has soaked for a season, the freeze
store scraper-side becomes the source of truth and recomputation is no longer guaranteed to hold
across joint template refinements.
"""
from __future__ import annotations
import json
import os
import uuid

import pytest

from engine.affix_identity import affix_identity
from engine.modifier_lines import NAMESPACE

_SEASON = "SS12"
_SEASON_DIR = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "seasons", _SEASON))

# First present wins: effect_raw (belt blends — effect_text is a derived wording), raw_text
# (parse_affix_text output), text (slim lines), modifier (hero-memory rows).
_TEXT_KEYS = ("effect_raw", "raw_text", "text", "modifier")


def _iter_identity_lines(obj, path=""):
    if isinstance(obj, dict):
        pu = obj.get("pooling_uuid")
        if pu:
            for k in _TEXT_KEYS:
                if isinstance(obj.get(k), str):
                    yield path, obj[k], pu
                    break
        for key, val in obj.items():
            yield from _iter_identity_lines(val, f"{path}/{key}")
    elif isinstance(obj, list):
        for i, val in enumerate(obj):
            yield from _iter_identity_lines(val, f"{path}[{i}]")


def test_every_stored_pooling_uuid_recomputes_from_its_text():
    if not os.path.isdir(_SEASON_DIR):
        pytest.skip(f"season data not found: {_SEASON_DIR}")
    checked = 0
    bad: list[str] = []
    for fname in sorted(os.listdir(_SEASON_DIR)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(_SEASON_DIR, fname), encoding="utf-8") as f:
            data = json.load(f)
        for path, text, pu in _iter_identity_lines(data, fname):
            checked += 1
            if str(uuid.uuid5(NAMESPACE, affix_identity(text))) != pu:
                bad.append(f"{path}: {text!r} -> stored {pu}")
    assert not bad, (
        f"{len(bad)} stored identities do not recompute from their text (importer stored a lying "
        "identity — that surface must store null ids instead):\n" + "\n".join(bad[:40])
    )
    # The walk must actually cover the catalogs — a refactor that hides identities from it would
    # otherwise pass vacuously.
    assert checked > 5000, f"only {checked} identity-carrying lines found — walk broken?"
