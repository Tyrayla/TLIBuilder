"""Skill/support tooltip badge resolution (source='skill', via _resolve_skill_line_keys).

Regression guard for false "Unrecognized (NYI)" badges: a line whose stat the engine DOES model must resolve
to that stat key (→ a working/inactive/unconsumed badge), not the empty list (→ red NYI). The two phrasing gaps
fixed here: a skill's own "for this skill" wording, and a "(the) (supported) skill's <X>" possessive sitting
between a parser keyword and its operand (conversion / added-flat lines)."""
import json
import os

from engine.tooltip import build_tooltip
from server import _resolve_skill_line_keys

from persistence import season_manager
_BY_ID = {s["item_id"]: s for s in season_manager.load_skills("SS12")["skills"]}


def _badge_keys(sid, needle):
    """Resolved stat keys for the first tooltip line of skill `sid` whose text contains `needle`."""
    for ln in build_tooltip(_BY_ID[sid])["lines"]:
        if needle.lower() in (ln["text"] or "").lower() and ln["badge_text"]:
            return _resolve_skill_line_keys(ln["badge_text"])
    raise AssertionError(f"no badged line containing {needle!r} in {sid}")


# ── the skill's OWN "for this skill" wording ──────────────────────────────────
def test_jumps_for_this_skill_resolves():
    # Chain Lightning "+2 Jumps for this skill" — was NYI because only "for the supported skill" was normalized.
    assert _badge_keys("chain_lightning", "Jumps") == ["extra_jumps_flat"]


def test_for_this_skill_normalized():
    assert _resolve_skill_line_keys("+2 Jumps for this skill") == ["extra_jumps_flat"]


# ── "(the) (supported) skill's <operand>" possessive ──────────────────────────
def test_conversion_with_supported_possessive_resolves():
    # "Converts 50% of the supported skill's Lightning Damage to Cold Damage" — was NYI; the possessive broke
    # the conversion parser. Conversion stats exist, so this must map (→ non-red badge), not read NYI.
    assert _badge_keys("lightning_to_cold", "Converts") == ["lightning_convert_to_cold"]


def test_conversion_possessive_variants():
    for txt in ("Converts 50% of the supported skill's Lightning Damage to Cold Damage",
                "Converts 50% of the skill's Lightning Damage to Cold Damage",
                "Converts 50% of Lightning Damage to Cold Damage"):
        assert _resolve_skill_line_keys(txt) == ["lightning_convert_to_cold"], txt


# ── guard: the normalization didn't break the plain "supported skill" path ────
def test_plain_supported_skill_still_resolves():
    assert _resolve_skill_line_keys("15 % additional Lightning Damage for the supported skill") \
        == ["lightning_dmg_additional"]
    assert _resolve_skill_line_keys("+2 Jumps for the supported skill") == ["extra_jumps_flat"]
