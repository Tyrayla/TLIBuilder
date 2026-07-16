"""Regression test for `GET /api/skills` (server.get_skills()) bypassing skill overrides.

BUG (fixed in server.py::get_skills, 2026-07-16): the endpoint used to call
`season_manager.load_skills(active)` DIRECTLY, skipping `_get_skills_data()` /
`engine.skill_overrides.apply_skill_overrides`. Every other consumer of skill data (e.g. the
compute path at server.py:804) went through `_get_skills_data()`, so overrides were applied there
— but the Skill panel / tooltip, which reads straight off `GET /api/skills`, showed the raw
crawler-mangled text. Most visibly: Mana Boil's consume line should read "Consumes 3 % of Max Mana
every second" (the corrected override), but the raw crawled SS13 data has a duplication artifact —
"Consumes 16.65 % additional Spell Damage while the skill lasts Mana every second." — carried over
from the preceding line. This was a display-only bug (stat computation was already correct via the
compute path's `_get_skills_data()` call); the fix routes `get_skills()` through the same
`_get_skills_data()` helper.

The fix: server.py::get_skills now calls `skills_by_id_raw = _get_skills_data(active)` instead of
`season_manager.load_skills(active)` directly. See the fix comment at server.py:1682-1687 and
.wolf/buglog.json "mana-boil-tooltip-bypasses-override".
"""
import pytest

from server import get_skills
from persistence import season_manager

_SEASON = season_manager.get_active_season()


def test_active_season_is_ss13():
    # Pin the concrete owner-facing case this test targets. If the active season legitimately
    # changed, re-verify the raw crawler text still exhibits the bug before updating this pin.
    assert _SEASON == "SS13", (
        f".wolf/data/seasons/.active is not SS13 (got {_SEASON!r}) — this test targets the SS13 "
        "mana_boil owner-facing regression; update the pin only after re-confirming against the "
        "new active season's raw data."
    )


class TestGetSkillsAppliesOverrides:
    """Primary: server.get_skills()'s mana_boil carries the corrected consume text."""

    def test_mana_boil_detailed_description_has_corrected_consume_line(self):
        result = get_skills()
        assert result["season"] == "SS13"
        by_id = {s["item_id"]: s for s in result["skills"]}
        assert "mana_boil" in by_id, "mana_boil missing from GET /api/skills output"
        mb = by_id["mana_boil"]

        consume_lines = [l for l in mb["detailed_description"] if l.strip().startswith("Consumes")]
        assert consume_lines, "mana_boil detailed_description has no 'Consumes' line at all"
        joined = " ".join(consume_lines)

        assert "Consumes 3 % of Max Mana" in joined, (
            f"expected the corrected override text, got consume line(s): {consume_lines!r}"
        )
        assert "16.65" not in joined, (
            f"raw crawler-mangled '16.65' text leaked into the consume line: {consume_lines!r}"
        )
        assert "additional Spell Damage" not in joined, (
            f"raw crawler duplication artifact leaked into the consume line: {consume_lines!r}"
        )

    def test_mana_boil_tooltip_has_corrected_consume_line(self):
        # The renderer's tooltip (built from the SAME dict get_skills() enriches) must also carry
        # the correction — this is the field the Skill panel/tooltip actually renders from.
        result = get_skills()
        by_id = {s["item_id"]: s for s in result["skills"]}
        mb = by_id["mana_boil"]
        tooltip_lines = mb.get("tooltip", {}).get("lines", [])
        assert tooltip_lines, "mana_boil tooltip has no lines"

        consume_texts = [ln.get("text", "") for ln in tooltip_lines if (ln.get("text") or "").strip().startswith("Consumes")]
        assert consume_texts, "no tooltip line starts with 'Consumes'"
        joined = " ".join(consume_texts)
        assert "Consumes 3 % of Max Mana" in joined
        assert "16.65" not in joined


class TestGetSkillsGoesThroughOverridePath:
    """General guard: get_skills() output must diverge from a bare, un-overridden
    season_manager.load_skills() call for mana_boil — pinning that get_skills() routes through
    apply_skill_overrides (via _get_skills_data), not the raw loader. If a future refactor
    re-introduces a direct season_manager.load_skills(active) bypass in get_skills(), this test
    catches it because the two outputs would become identical again (both showing '16.65').
    """

    def test_get_skills_output_differs_from_raw_unoverridden_load(self):
        raw = season_manager.load_skills(_SEASON)
        assert raw, "no raw SS13 skill data on disk — cannot validate the override-bypass guard"
        raw_by_id = {s["item_id"]: s for s in raw.get("skills", []) if "item_id" in s}
        assert "mana_boil" in raw_by_id

        raw_consume_lines = [
            l for l in raw_by_id["mana_boil"]["detailed_description"] if l.strip().startswith("Consumes")
        ]
        # Fixture assumption: the on-disk raw crawler data for SS13 still has the mangled text.
        # If this ever stops being true (a future crawler re-import corrects it upstream), the
        # override system's mana_boil patch becomes moot and this guard should be revisited.
        assert any("16.65" in l for l in raw_consume_lines), (
            "raw on-disk mana_boil data no longer contains the crawler-mangled '16.65' consume "
            "text — the fixture this guard relies on has changed; re-validate the override guard"
        )

        result = get_skills()
        overridden_by_id = {s["item_id"]: s for s in result["skills"]}
        overridden_consume_lines = [
            l for l in overridden_by_id["mana_boil"]["detailed_description"] if l.strip().startswith("Consumes")
        ]

        # The whole point of the fix: get_skills()'s consume line(s) must NOT equal the raw ones —
        # apply_skill_overrides must have patched them in between load and serve.
        assert overridden_consume_lines != raw_consume_lines, (
            "get_skills() detailed_description matches the raw, un-overridden loader output — "
            "overrides are not being applied (get_skills() may be bypassing _get_skills_data again)"
        )
        assert not any("16.65" in l for l in overridden_consume_lines)
