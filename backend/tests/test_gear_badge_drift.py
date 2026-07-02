"""Drift guard: the gear BADGE path must not diverge from what the ENGINE actually applies.

Background: the engine resolves a raw gear affix text via _resolve_gear_affix_clauses (named-buff expansion +
clause/condition split + _parse_custom_mod_text). The /api/map-modifiers badge endpoint historically used a
SEPARATE fuzzy catalog resolver (_resolve_affix/_resolve_gear_stat), so consume / per-N-consumed / gated lines
(Awakening Skull armour-pen, Blade-dancer's Fingers, Glacier, etc.) badged red NYI while the engine applied them.

Both now share _resolve_gear_affix_clauses, with the badge endpoint falling back to it. These tests lock that in:
any catalog gear line the engine resolves to stat keys must ALSO produce badge keys (never NYI).
"""
import json
import os
import pytest
from server import (engine_stats, EngineStatsRequest, map_modifiers, MapModifiersRequest,
                    _resolve_gear_affix_clauses, _resolve_affix)

_SEASON_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "seasons", "SS12")


def _badge_keys(text: str) -> list[str]:
    """Stat keys the badge endpoint reports for a raw gear line (what drives Consumed/Unconsumed vs NYI)."""
    r = map_modifiers(MapModifiersRequest(items=[{"key": "k", "text": text, "source": "gear"}]))
    return r["results"]["k"]["stat_keys"]


def _engine_keys(text: str) -> list[str]:
    return [e["stat_key"] for cl in _resolve_gear_affix_clauses(text) for e in cl["parsed"]]


# The three lines Tyra reported badging NYI despite working (regression cases).
@pytest.mark.parametrize("text", [
    "+(20-25) % Armor DMG Mitigation Penetration for Attack Skills if you have consumed more than 120 % of Max Life recently",
    "Adds (18-21) - (24-27) Physical Damage to Attacks for every 3300 Life consumed recently. Stacks up to 170 time(s)",
    "Consumes (5-10) % of current Life on skill use",
    "Adds (13-15) - (23-26) Physical Damage to Attacks and Spells for every (1000-1050) Mana consumed recently. Stacks up to 200 time(s)",
])
def test_reported_lines_badge_not_nyi(text):
    assert _engine_keys(text), f"engine should resolve: {text!r}"
    assert _badge_keys(text), f"engine resolves but badge is NYI (drift): {text!r}"


# Dual-pool combos ("X and Y") must fan a single value out to BOTH pools. Regression: Heart of the Storm's
# "+% Max Life and Max Energy Shield" resolved to only max_energy_shield_inc, silently dropping the Max Life half.
@pytest.mark.parametrize("raw_text,expected", [
    ("+(20-24) % Max Life and Max Energy Shield", {"max_life_inc", "max_energy_shield_inc"}),
    ("+(20-24) Max Life and Max Energy Shield", {"max_life_flat", "max_energy_shield_flat"}),
    ("+(25-30) % Max Life and Max Mana", {"max_life_inc", "max_mana_inc"}),
])
def test_dual_pool_combo_resolves_to_both(raw_text, expected):
    r = _resolve_affix({"raw_text": raw_text, "affix_kind": "numeric"})
    assert r.get("stat_key") is None, f"combo must NOT collapse to a single stat_key: {raw_text!r}"
    assert set(r.get("stat_keys") or []) == expected, f"{raw_text!r} -> {r.get('stat_keys')}"


def _all_legendary_affix_texts() -> set[str]:
    path = os.path.join(_SEASON_DIR, "_legendary_gear.json")
    d = json.load(open(path, encoding="utf-8"))
    texts: set[str] = set()
    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ("raw_text", "modifier_text", "text") and isinstance(v, str):
                    texts.add(v.strip())
                else:
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(d.get("items", d))
    return texts


def test_no_catalog_gear_line_engine_resolves_but_badges_nyi():
    """Catalog-wide invariant: for EVERY legendary affix line the engine resolves to stat keys, the badge path
    must also report keys. Curse-only lines (no stat keys, recognized separately) are excluded."""
    drift = []
    for text in sorted(_all_legendary_affix_texts()):
        eng = _engine_keys(text)
        if not eng:
            continue                      # engine doesn't resolve it → genuinely NYI, not drift
        if not _badge_keys(text):
            drift.append(text)
    assert not drift, "Gear lines the engine resolves but that badge NYI (badge↔engine drift):\n  " + "\n  ".join(drift[:40])
