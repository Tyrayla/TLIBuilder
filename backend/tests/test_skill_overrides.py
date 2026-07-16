"""Regression tests for the refined season-warning logic in engine/skill_overrides.py.

apply_skill_overrides() used to warn "authored for SS12 but active is SS13 — re-validate" purely on
a season-name mismatch. It now only warns when the active season's RAW skill data actually diverges
numerically (at the overlapping detailed_description / simple_description / raw_text lines) from the
authored season's data — a season bump with unchanged underlying values shouldn't cry wolf. Cosmetic
text drift (a stray '+' prefix etc.) is ignored via numeric-token comparison. See
engine/skill_overrides.py:76-94 (_authored_season_diverges) and :97-100 (_load_authored_season_skills).

Covers the three branches: (1) suppressed when active-season data numerically matches the authored
data, incl. a cosmetic '+'-only diff, (2) fires when a numeric value actually diverges, (3) fires
conservatively when there's no authored-season skill / no overlapping lines to compare. Also pins the
concrete owner-facing case: the REAL mana_boil under the REAL active season (SS13) is suppressed
because SS13's raw data is numerically identical to SS12's for the compared fields (only a cosmetic
'+10%' vs '10%' text difference in simple_description).
"""
import pytest

from engine.skill_overrides import apply_skill_overrides, _authored_season_diverges
from persistence import season_manager

_CORRUPT_DETAILED = [
    "Gains Euphoria upon casting the skill:",
    "16.65 % additional Spell Damage while the skill lasts",
    "Consumes 16.65 % additional Spell Damage while the skill lasts Mana every second.",
    "Loses the Euphoria effect when Mana drops to 0.",
]
_CORRUPT_RAW = (
    "Gains Euphoria upon casting the skill: 16.65 % additional Spell Damage while the skill lasts "
    "Consumes 16.65 % additional Spell Damage while the skill lasts Mana every second. "
    "Loses the Euphoria effect when Mana drops to 0."
)


def _mk_active_sk(simple_line: str) -> dict:
    return {
        "item_id": "mana_boil",
        "detailed_description": list(_CORRUPT_DETAILED),
        "simple_description": [simple_line],
        "raw_text": _CORRUPT_RAW,
    }


def _fake_load_skills(authored_sk: dict | None):
    """Build a season_manager.load_skills-shaped stand-in for monkeypatching."""
    def _load(season: str, raw: bool = False):
        if authored_sk is None:
            return {"skills": []}
        return {"skills": [authored_sk]}
    return _load


# ── Branch 1: suppressed when numerically matching (incl. cosmetic '+' drift) ──────────────────

def test_suppressed_when_active_matches_authored_numerically(monkeypatch):
    # Active season data is byte-for-byte identical to the authored season EXCEPT a cosmetic '+'
    # prefix on the simple_description percentage — must NOT count as a divergence.
    active_sk = _mk_active_sk(
        "Gains Euphoria upon casting the skill: Consumes Mana over time and permanently grants "
        "+10% additional Spell Damage. Loses the Euphoria effect when Mana drops to 0."
    )
    authored_sk = _mk_active_sk(
        "Gains Euphoria upon casting the skill: Consumes Mana over time and permanently grants "
        "10% additional Spell Damage. Loses the Euphoria effect when Mana drops to 0."
    )
    monkeypatch.setattr(season_manager, "load_skills", _fake_load_skills(authored_sk))

    skills_by_id = {"mana_boil": active_sk}
    reviews = apply_skill_overrides(skills_by_id, "SS13")
    assert not any("re-validate" in r for r in reviews)
    # Override still applied (corrected values patched in), independent of the warning suppression.
    assert "Consumes 3 % of Max Mana every second" in skills_by_id["mana_boil"]["detailed_description"]


def test_authored_season_diverges_direct_unit_matching():
    # Direct unit coverage of the comparator: identical numeric tokens across a cosmetic '+' diff.
    active = {"simple_description": ["+10% additional Spell Damage"]}
    authored = {"simple_description": ["10% additional Spell Damage"]}
    assert _authored_season_diverges(active, authored) is False


# ── Branch 2: fires when a numeric value actually diverges ─────────────────────────────────────

def test_fires_when_numeric_value_diverges(monkeypatch):
    active_sk = _mk_active_sk(
        "Gains Euphoria upon casting the skill: Consumes Mana over time and permanently grants "
        "12% additional Spell Damage. Loses the Euphoria effect when Mana drops to 0."
    )
    authored_sk = _mk_active_sk(
        "Gains Euphoria upon casting the skill: Consumes Mana over time and permanently grants "
        "10% additional Spell Damage. Loses the Euphoria effect when Mana drops to 0."
    )
    monkeypatch.setattr(season_manager, "load_skills", _fake_load_skills(authored_sk))

    reviews = apply_skill_overrides({"mana_boil": active_sk}, "SS13")
    assert any("re-validate" in r for r in reviews)


def test_authored_season_diverges_direct_unit_value_change():
    active = {"simple_description": ["12% additional Spell Damage"]}
    authored = {"simple_description": ["10% additional Spell Damage"]}
    assert _authored_season_diverges(active, authored) is True


# ── Branch 3: conservative fallback — no authored skill / no overlap ───────────────────────────

def test_fires_when_authored_season_skill_absent(monkeypatch):
    active_sk = _mk_active_sk("10% additional Spell Damage")
    monkeypatch.setattr(season_manager, "load_skills", _fake_load_skills(None))   # no mana_boil entry

    reviews = apply_skill_overrides({"mana_boil": active_sk}, "SS13")
    assert any("re-validate" in r for r in reviews)


def test_fires_when_zero_overlapping_lines(monkeypatch):
    # Authored skill exists but has empty compared fields — nothing overlaps to compare, so the
    # conservative fallback still warns rather than silently assuming the override is fine.
    active_sk = _mk_active_sk("10% additional Spell Damage")
    authored_sk = {"item_id": "mana_boil", "detailed_description": [], "simple_description": [], "raw_text": ""}
    monkeypatch.setattr(season_manager, "load_skills", _fake_load_skills(authored_sk))

    reviews = apply_skill_overrides({"mana_boil": active_sk}, "SS13")
    assert any("re-validate" in r for r in reviews)


def test_authored_season_diverges_direct_unit_no_authored_skill():
    assert _authored_season_diverges({"simple_description": ["10%"]}, None) is True


def test_authored_season_diverges_direct_unit_no_overlap():
    active = {"simple_description": ["10%"], "detailed_description": ["a line"]}
    authored = {"simple_description": [], "detailed_description": []}
    assert _authored_season_diverges(active, authored) is True


# ── Concrete owner-facing case: the REAL mana_boil under the REAL active season (SS13) ─────────

def test_real_mana_boil_suppressed_under_active_ss13():
    # Owner-facing regression: SS13's raw mana_boil data (loaded from the actual season data on disk,
    # no mocking) is numerically identical to SS12's for the compared fields — only a cosmetic '+10%'
    # vs '10%' text difference in simple_description — so the season-mismatch warning must be
    # SUPPRESSED, not fired, for the real build.
    active_season = season_manager.get_active_season()
    assert active_season == "SS13", (
        "This test pins the SS13 concrete case; .wolf/data/seasons/.active is not SS13 — "
        f"got {active_season!r}. If the active season legitimately changed, update this test."
    )
    ss13_skills = season_manager.load_skills("SS13")
    assert ss13_skills, "SS13 skill data not found on disk — cannot validate the real mana_boil case"
    skills_by_id = {s["item_id"]: s for s in ss13_skills["skills"] if "item_id" in s}
    assert "mana_boil" in skills_by_id, "mana_boil missing from SS13 skill data"

    reviews = apply_skill_overrides(skills_by_id, "SS13")
    mana_boil_reviews = [r for r in reviews if "mana_boil" in r]
    assert not any("re-validate" in r for r in mana_boil_reviews), (
        f"expected mana_boil's season warning to be suppressed (SS13 numerically matches SS12); got: {mana_boil_reviews}"
    )
    # The override itself must still have applied (corrected values patched in) regardless of the warning.
    assert "Consumes 3 % of Max Mana every second" in skills_by_id["mana_boil"]["detailed_description"]
