"""Modeled active skills: intrinsic tooltip lines split cleanly (from detailed_description) and the genuinely-
modeled mechanics carry coverage=='modeled' (green), while unimplemented mechanics stay honest NYI (coverage None
and no stat keys). Damage/DPS is unaffected — proven separately by the support_skill / scope goldens."""
import pytest
from engine.tooltip import build_tooltip
from server import _get_skills_data, season_manager, _resolve_skill_line_keys

_data = _get_skills_data(season_manager.get_active_season())


def _lines(sid):
    return build_tooltip(_data[sid])["lines"]


def _find(sid, needle):
    """The line whose badge_text OR text contains needle (case-insensitive)."""
    for ln in _lines(sid):
        hay = (ln.get("badge_text") or "") + " " + (ln.get("text") or "")
        if needle.lower() in hay.lower():
            return ln
    return None


def _is_modeled(sid, needle):
    ln = _find(sid, needle)
    assert ln is not None, f"{sid}: no line matching {needle!r}"
    return ln.get("coverage") == "modeled"


def _is_nyi(sid, needle):
    """A line that's neither modeled nor resolvable to a stat → would render red NYI (honest)."""
    ln = _find(sid, needle)
    assert ln is not None, f"{sid}: no line matching {needle!r}"
    bt = ln.get("badge_text") or ""
    return ln.get("coverage") != "modeled" and bool(bt) and not _resolve_skill_line_keys(bt)


# ── clean line splitting (no run-on) ──────────────────────────────────────────
def test_clauses_split_one_per_line():
    # "Base Attack Frequency: 1.5" and "Max Channeled Stacks: 5" are SEPARATE lines (label/value joined), not a
    # single run-on — and the per-stack effects are their own lines too.
    freq = _find("howling_gale", "Base Attack Frequency")
    assert freq and freq["text"].strip() == "Base Attack Frequency: 1.5"
    stacks = _find("howling_gale", "Max Channeled Stacks")
    assert stacks and stacks["text"].strip() == "Max Channeled Stacks: 5"
    # not glued together
    assert "Max Channeled Stacks" not in freq["text"]


def test_straggler_uses_simple_description():
    # endless_vendetta has no detailed_description → falls back to simple_description (still split, not blank).
    lines = _lines("endless_vendetta")
    assert any("repeat" in (ln.get("text") or "").lower() for ln in lines)


# ── green 'modeled' on genuinely-modeled mechanics ────────────────────────────
def test_howling_gale_coverage():
    assert _is_modeled("howling_gale", "Max Channeled Stacks")
    assert _is_modeled("howling_gale", "Base Attack Frequency")
    assert _is_modeled("howling_gale", "21.5 % additional damage")
    # informational per-stack effects are NOT modeled (stay as-is, not falsely green)
    assert not _is_modeled("howling_gale", "Skill Area for Gale")
    assert not _is_modeled("howling_gale", "Movement Speed for Gale")


def test_focused_slash_coverage():
    assert _is_modeled("focused_slash", "for every 1 Fervor Rating")
    assert _is_modeled("focused_slash", "Steep Strike chance")
    assert _is_modeled("focused_slash", "affected by Fervor Effect")   # Fervor Effect scales the bonus
    assert not _is_modeled("focused_slash", "Gains Fervor when this skill hits")


def test_moon_strike_coverage():
    assert _is_modeled("moon_strike", "for every 100 Max Mana")
    assert _is_modeled("moon_strike", "Steep Strike chance")


def test_icebound_beam_coverage():
    assert _is_modeled("icebound_beam", "Shotgun Effect falloff")
    assert _is_modeled("icebound_beam", "Projectile Quantity of this skill")


def test_berserking_blade_coverage():
    assert _is_modeled("berserking_blade", "Skill Area for each stack of buff")
    assert _is_modeled("berserking_blade", "Stacks up to")
    assert _is_modeled("berserking_blade", "Steep Strike chance")
    # the on-defeat/Elite buff-grant condition is assumed-max, not modeled → not green
    assert not _is_modeled("berserking_blade", "defeats an enemy or hits an Elite")


# ── modeled lines never render red ────────────────────────────────────────────
@pytest.mark.parametrize("sid,needle", [
    ("howling_gale", "Max Channeled Stacks"),
    ("howling_gale", "21.5 % additional damage"),
    ("focused_slash", "for every 1 Fervor Rating"),
    ("moon_strike", "for every 100 Max Mana"),
    ("icebound_beam", "Shotgun Effect falloff"),
])
def test_modeled_lines_not_nyi(sid, needle):
    ln = _find(sid, needle)
    assert ln and ln.get("coverage") == "modeled" and not ln.get("badge_text")
