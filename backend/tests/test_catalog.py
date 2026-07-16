"""Unit tests for `engine.hero_traits._catalog` — the shared season-catalog per-tier-value reader added
2026-07-16 (licorice_note / unsullied_blade / high_court_chariot SS12->SS13 drift fix). Flagged by the review
council as the highest-risk new logic in that change (a mis-aligned marker/index/shape silently produces wrong
DPS) and previously had zero dedicated tests — every `hero_traits` module test exercised it only indirectly,
through `apply()`/`engine_stats`, with real catalog text.

Covers `advanced_trait_text()`, `tier_values()`, `pick_tier_values()` in isolation, including the catalog's
real inconsistent number formatting (mixed +/-/decimal/no-sign), the scalar-vs-per-tier shape-detection path
(`allow_scalar=True`), every raise path, and the `text is None` fallback branch that a full `apply()` call
can't isolate (it's only reachable there via `build_input=None`, which conflates "no season" with "season
doesn't have this pick").
"""
import pytest

from engine.hero_traits import _catalog


# ── tier_values: correct parse + real catalog formatting ──────────────────────────────
def test_tier_values_basic_five_value_parse():
    text = "Something ( +18 / +21 / +24 / +27 / +30 )% more text"
    assert _catalog.tier_values(text) == [18.0, 21.0, 24.0, 27.0, 30.0]


def test_tier_values_handles_negative_decimals():
    # Real catalog text shape: all-negative, some whole, some fractional.
    text = "prefix ( -0.67 / -0.8 / -1 / -1 / -1.2 )%"
    assert _catalog.tier_values(text) == [-0.67, -0.8, -1.0, -1.0, -1.2]


def test_tier_values_handles_unsigned_fractional():
    # Real catalog text shape: no leading sign at all, all fractional.
    text = "prefix ( 0.3 / 0.37 / 0.44 / 0.51 / 0.58 )%"
    assert _catalog.tier_values(text) == [0.3, 0.37, 0.44, 0.51, 0.58]


def test_tier_values_handles_mixed_sign_and_precision():
    # Real catalog text shape: some tiers carry '+', some don't; some whole, some fractional — same group.
    text = "prefix ( +1 / 1.5 / +2 / 2.5 / +3 )%"
    assert _catalog.tier_values(text) == [1.0, 1.5, 2.0, 2.5, 3.0]


def test_pick_tier_values_converts_percent_to_fraction(monkeypatch):
    text = "For every enemy , ( +5 / +6 / +7 / +8 / +9 )% additional Elemental Damage"
    monkeypatch.setattr(_catalog.season_manager, "load_hero_traits_indexed", lambda season: {
        "some_trait": {"advanced_traits": [{"name": "Some Pick", "effects": [text]}]}
    })
    vals = _catalog.pick_tier_values("SS13", "some_trait", "Some Pick", marker="For every enemy , ",
                                      fallback=[0, 0, 0, 0, 0])
    assert vals == pytest.approx([0.05, 0.06, 0.07, 0.08, 0.09])


# ── Scalar-vs-per-tier shape detection (allow_scalar=True) ────────────────────────────
def test_tier_values_allow_scalar_resolves_flat_cap():
    # SS12 shape: High Court Chariot's Unbreakable Stand cap was a flat scalar for every tier.
    text = "additional damage for each enemy in the Holy Domain , up to +100% additional damage"
    assert _catalog.tier_values(text, marker="up to ", allow_scalar=True) == [100.0] * 5


def test_tier_values_allow_scalar_resolves_per_tier_cap():
    # SS13 shape: the SAME marker/allow_scalar call now finds a real 5-value group instead — one code
    # path resolving both catalog shapes with no `season ==` branch.
    text = "additional damage for each enemy in the Holy Domain , up to ( +50 / +60 / +70 / +80 / +90 )% additional damage"
    assert _catalog.tier_values(text, marker="up to ", allow_scalar=True) == [50.0, 60.0, 70.0, 80.0, 90.0]


def test_tier_values_allow_scalar_false_does_not_fall_back():
    # Without allow_scalar, a scalar-only match must still raise rather than silently broadcasting.
    text = "up to +100% additional damage"
    with pytest.raises(ValueError):
        _catalog.tier_values(text, marker="up to ", allow_scalar=False)


# ── Raise paths ─────────────────────────────────────────────────────────────────────
def test_tier_values_raises_when_marker_not_found():
    with pytest.raises(ValueError, match="marker"):
        _catalog.tier_values("no marker here at all", marker="NOPE NOT PRESENT")


def test_tier_values_raises_on_malformed_group_without_allow_scalar():
    # A group is found but doesn't have exactly 5 numbers, and allow_scalar is off → loud failure, not a
    # silently wrong/short array.
    text = "prefix ( +18 / +21 / +24 )% only three values"
    with pytest.raises(ValueError):
        _catalog.tier_values(text, allow_scalar=False)


def test_tier_values_raises_when_nothing_found_at_all():
    text = "prefix with no parens and no trailing number"
    with pytest.raises(ValueError):
        _catalog.tier_values(text, allow_scalar=True)


# ── pick_tier_values: text-is-None fallback (season/trait/pick absent) ────────────────
def test_pick_tier_values_falls_back_when_season_falsy():
    fallback = [0.06, 0.07, 0.08, 0.09, 0.10]
    assert _catalog.pick_tier_values(None, "some_trait", "Some Pick", fallback=fallback) == fallback
    assert _catalog.pick_tier_values("", "some_trait", "Some Pick", fallback=fallback) == fallback


def test_pick_tier_values_falls_back_when_trait_absent_from_catalog(monkeypatch):
    monkeypatch.setattr(_catalog.season_manager, "load_hero_traits_indexed", lambda season: {})
    fallback = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert _catalog.pick_tier_values("SS13", "missing_trait", "Some Pick", fallback=fallback) == fallback


def test_pick_tier_values_falls_back_when_pick_name_absent(monkeypatch):
    monkeypatch.setattr(_catalog.season_manager, "load_hero_traits_indexed", lambda season: {
        "some_trait": {"advanced_traits": [{"name": "A Different Pick", "effects": ["( 1 / 2 / 3 / 4 / 5 )%"]}]}
    })
    fallback = [9.0, 9.0, 9.0, 9.0, 9.0]
    assert _catalog.pick_tier_values("SS13", "some_trait", "Some Pick", fallback=fallback) == fallback


def test_advanced_trait_text_none_paths(monkeypatch):
    assert _catalog.advanced_trait_text(None, "t", "p") is None
    assert _catalog.advanced_trait_text("", "t", "p") is None
    monkeypatch.setattr(_catalog.season_manager, "load_hero_traits_indexed", lambda season: {})
    assert _catalog.advanced_trait_text("SS13", "missing_trait", "p") is None
    monkeypatch.setattr(_catalog.season_manager, "load_hero_traits_indexed", lambda season: {
        "t": {"advanced_traits": [{"name": "other pick", "effects": ["x"]}]}
    })
    assert _catalog.advanced_trait_text("SS13", "t", "not there") is None


# ── Group indexing (Licorice Note's repeated-shape-group case) ────────────────────────
def test_tier_values_index_selects_the_nth_group_not_the_first():
    # Same-shaped groups repeated in one string (e.g. Empower clause then Curse clause) — `index` must select
    # the intended occurrence, not always the first.
    text = "Empower grants ( +1 / +2 / +3 / +4 / +5 )% and Curse grants ( +10 / +20 / +30 / +40 / +50 )%"
    assert _catalog.tier_values(text, index=0) == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert _catalog.tier_values(text, index=1) == [10.0, 20.0, 30.0, 40.0, 50.0]


def test_pick_tier_values_off_by_one_tier_indexing(monkeypatch):
    # Tier N (1-5) must read array index N-1 — a classic off-by-one target. Verify each of the 5 tiers reads
    # its own distinct value, not a neighbor's.
    text = "prefix ( +10 / +20 / +30 / +40 / +50 )%"
    monkeypatch.setattr(_catalog.season_manager, "load_hero_traits_indexed", lambda season: {
        "t": {"advanced_traits": [{"name": "p", "effects": [text]}]}
    })
    vals = _catalog.pick_tier_values("SS13", "t", "p", marker="prefix ", pct=False, fallback=[0, 0, 0, 0, 0])
    for tier_1_based, expected in zip(range(1, 6), [10.0, 20.0, 30.0, 40.0, 50.0]):
        assert vals[tier_1_based - 1] == expected
