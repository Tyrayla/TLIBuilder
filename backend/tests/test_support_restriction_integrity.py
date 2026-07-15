"""Drift detector for the 2026-07-15 activation-medium restriction-line recovery
(season_manager._inject_am_restrictions / data/activation_medium_restrictions.json).

Runs against the REAL active-season data via season_manager.load_skills (module-level load, same
convention as test_support_gating.py / test_support_mapper.py's _by_name() helpers) -- NOT a fixture --
so a future SS13/SS14 catalog change fails loudly here instead of only surfacing as a silent
gating/tooltip defect:
  - a re-drop of the native support/noble/magnificent gate line (the class of regression that hit
    activation mediums in SS12 could in principle hit these too), or
  - a season that restores the activation-medium gate lines natively (present_in_ss12: true for a given
    item_id going forward) and needs the recovery map's own-data inertness check to keep working, or
  - a new activation_medium_skill item_id that ships without a data/activation_medium_restrictions.json
    entry and without native restriction lines (falls through injection silently otherwise).

See .wolf/buglog.json id activation-medium-restriction-lines-dropped-ss12 and
data/activation_medium_restrictions.json (_meta block) for the full 2026-07-15 audit writeup.

Known limitation (flagged, not fixed here): these are cheap prefix/`startswith` smoke checks, not a
full-content match against data/activation_medium_restrictions.json's exact restriction_lines text --
a mangled family list (e.g. a family name dropped mid-string, or "Support " without the "s") that still
begins with "Support"/"Supports" would NOT be caught here. That's an intentional, narrow scope: this
suite exists to catch the *class* of failure actually observed (whole lines silently missing from the
crawl), which a startswith check catches cheaply and reliably. The exact-text case is already covered by
the byte-for-byte golden fixture backend/tests/fixtures/tooltip_golden/Activation_Medium_Boss.json.
"""
from persistence import season_manager

_SEASON = season_manager.get_active_season()
_DATA = season_manager.load_skills(_SEASON) if _SEASON else None
_SKILLS = (_DATA or {}).get("skills") or []

_SUPPORT_TYPES = ("support_skill", "noble_support_skill", "magnificent_support_skill")


def _by_type(*types):
    return [s for s in _SKILLS if s.get("skill_type") in types]


def test_season_data_loads_non_empty():
    assert _SEASON, "no active season configured (data/seasons/.active) -- cannot run the restriction-integrity check"
    assert _SKILLS, f"season_manager.load_skills({_SEASON!r}) returned no skills"


class TestSupportGateLineIntegrity:
    """Every native support_skill/noble_support_skill/magnificent_support_skill must carry its own
    'Supports <family> Skills.' gate line. These are OUTSIDE the activation-medium recovery map
    (data/activation_medium_restrictions.json only covers skill_type == 'activation_medium_skill') and
    were unaffected by the SS12 crawl regression -- they're the negative control. If one of these starts
    failing, either the crawl regressed for this class too (needs its own recovery map, not an extension
    of the AM one), or a raw_text/description_lines normalization change broke the gate line."""

    def test_raw_text_starts_with_support(self):
        bad = [s.get("item_id") for s in _by_type(*_SUPPORT_TYPES)
               if not (s.get("raw_text") or "").startswith("Support")]
        assert not bad, (
            f"{len(bad)} support/noble/magnificent support_skill entries lost their native 'Supports ...' "
            f"gate line from raw_text: {bad[:10]}. Cross-check data/activation_medium_restrictions.json and "
            f"the 2026-07-15 audit (.wolf/buglog.json id activation-medium-restriction-lines-dropped-ss12)."
        )

    def test_description_lines_first_line_starts_with_support(self):
        bad = [s.get("item_id") for s in _by_type(*_SUPPORT_TYPES)
               if not ((s.get("description_lines") or [""])[0] or "").startswith("Support")]
        assert not bad, (
            f"{len(bad)} support/noble/magnificent support_skill entries lost their native 'Supports ...' "
            f"gate line from description_lines[0] (the field isSupportCompatible/engine.support_lines."
            f"parse_support anchor on): {bad[:10]}. See data/activation_medium_restrictions.json + the "
            f"2026-07-15 audit."
        )


class TestActivationMediumGateInjection:
    """Every activation_medium_skill must end up with a 'Supports <family> Skills.' gate line as
    description_lines[0] after season_manager._inject_am_restrictions runs (native for
    activation_medium_tangle; injected from data/activation_medium_restrictions.json for the other 27
    per the 2026-07-15 SS12 audit)."""

    def test_every_medium_has_a_supports_gate_line(self):
        mediums = _by_type("activation_medium_skill")
        assert mediums, "no activation_medium_skill entries loaded -- season data or skill_type changed"
        bad = [s.get("item_id") for s in mediums
               if not ((s.get("description_lines") or [""])[0] or "").startswith("Supports")]
        assert not bad, (
            f"{len(bad)} activation_medium_skill entries have no 'Supports ...' gate line at "
            f"description_lines[0] after injection: {bad}. Check data/activation_medium_restrictions.json "
            f"for a missing/mismatched item_id entry, or that season_manager._inject_am_restrictions is "
            f"still wired into load_skills(). See .wolf/buglog.json id "
            f"activation-medium-restriction-lines-dropped-ss12."
        )

    def test_no_medium_has_a_duplicated_gate_line(self):
        """A regression here would mean _inject_am_restrictions's own-data inertness check (normalized-text
        match against the item's OWN existing description_lines) stopped working -- e.g. a future season
        that restores the gate line natively (present_in_ss12 flips true) would double it in the rendered
        tooltip instead of the injector staying inert."""
        dup = []
        for s in _by_type("activation_medium_skill"):
            lines = s.get("description_lines") or []
            if not lines:
                continue
            gate_norm = " ".join((lines[0] or "").split()).strip().lower()
            occurrences = sum(1 for ln in lines if " ".join((ln or "").split()).strip().lower() == gate_norm)
            if occurrences > 1:
                dup.append((s.get("item_id"), occurrences))
        assert not dup, (
            f"activation_medium_skill entries with a duplicated gate line in description_lines "
            f"(item_id, occurrence_count): {dup}. Check the normalized-text match in "
            f"season_manager._inject_am_restrictions against this season's native crawl -- "
            f"activation_medium_tangle (natively 1 occurrence) is the reference case that must never dup, "
            f"and any newly-restored entry must behave the same way. See "
            f"data/activation_medium_restrictions.json + .wolf/buglog.json id "
            f"activation-medium-restriction-lines-dropped-ss12."
        )
