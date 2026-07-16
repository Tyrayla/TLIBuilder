"""Regression guards for the two upstream defects behind the 2026-07-12 DPS-coverage overclaims
(reconciled 2026-07-12, see docs/BACKLOG.md and the `.wolf/buglog.json` entries for both fixes):

Defect 1 — `support_mapper.map_conditional_line`'s "cursed enem"/"numbed enem" branches used to fire on
ANY line mentioning "Numbed"/"Cursed enemies", including a pure TARGETING/gate clause with no damage
payload at all (Thunder Core: Lightning Lasso's bolt-count mechanic). The fix requires the line to also
contain "additional damage" wording before treating a cursed/numbed mention as one of Grudge's/Electric
Punishment's own damage bonuses.

Defect 2 — `engine.tooltip._is_dup`'s significant-token overlap fallback didn't strip a trailing SCOPE/
GATE qualifier ("for Minions summoned by the supported skill", "when the supported skill consumes
Demolisher Charge") before comparing token sets, so two clauses that only agreed on shared boilerplate —
not the actual effect — were falsely deduped and silently dropped from `_lines_tiered`'s output (and
therefore from `skill_coverage`'s per-line reduction, which read the surviving `fixed` list as
"everything else is modeled").

Both fixes flip specific items from an overclaimed `skill_coverage` status; those flips are pinned in
test_coverage.py. This file pins the LOW-LEVEL mechanics of each fix directly, so a future edit to either
function can't silently regress without a WHY-scoped failure here (rather than only a downstream coverage
diff)."""
import pytest

from persistence import season_manager
from engine.support_lines import parse_support
from engine.support_mapper import map_conditional_line
from engine.tooltip import build_tooltip, _is_dup

_SEASON = season_manager.get_active_season()

pytestmark = pytest.mark.skipif(
    _SEASON != "SS12",
    reason="SS12-specific ground-truth; SS13 values pending re-verification post-flip (see data/seasons/.active)",
)

_SKILLS = season_manager.load_skills("SS12")
_BY_ID = {s["item_id"]: s for s in _SKILLS["skills"] if "item_id" in s}


def _line(item_id: str, index: int):
    return parse_support(_BY_ID[item_id]).lines[index]


# ── Defect 1: map_conditional_line's "additional damage" scope guard ─────────────────────────────
class TestConditionalLineScopeGuard:
    def test_thunder_core_lightning_lasso_bolt_line_no_spurious_damage(self):
        """The bolt-count mechanic line ("...launches 1 additional bolt of lightning at Numbed enemies
        within 10m nearby...") mentions Numbed enemies purely as a targeting clause — no "additional
        damage" wording — so it must NOT resolve to a damage contribution, even with conditions that
        would have triggered Electric Punishment's per-stack branch (numbed_stacks set, enemy_numbed
        True) under the pre-fix bare-substring check."""
        bolt_line = _line("thunder_core_lightning_lasso_noble", 2)
        assert "numbed" in bolt_line.template
        assert "additional damage" not in bolt_line.template
        conds = {"numbed_stacks": 10, "enemy_numbed": True}
        assert map_conditional_line(bolt_line, 1, conds) == []

    def test_electric_punishment_numbed_damage_still_resolves(self):
        """Guard-isn't-over-tight check: a genuine "+X% additional damage to Numbed enemies" / per-stack
        line (Electric Punishment) still resolves to dmg_additional when the condition holds, and still
        resolves to nothing when it doesn't."""
        line = _line("electric_punishment", 0)
        assert "additional damage" in line.template
        on = map_conditional_line(line, 1, {"numbed_stacks": 10, "enemy_numbed": True})
        assert len(on) == 1 and on[0].stat_key == "dmg_additional" and on[0].amount > 0
        off = map_conditional_line(line, 1, {"numbed_stacks": 0, "enemy_numbed": False})
        assert off == []

    def test_grudge_cursed_damage_still_resolves(self):
        """Sibling branch (Cursed, not Numbed) — same guard shape, same must-still-work check."""
        line = _line("grudge", 0)
        assert "additional damage" in line.template
        on = map_conditional_line(line, 1, {"enemy_cursed": True})
        assert len(on) == 1 and on[0].stat_key == "dmg_additional" and on[0].amount > 0
        assert map_conditional_line(line, 1, {"enemy_cursed": False}) == []

    def test_thunder_core_live_dps_path_only_universal_rank_line(self):
        """The LIVE DPS path (engine.support_resolver, via test_support_gating.py's frozen baseline)
        already pins Thunder Core: Lightning Lasso's ungated contribution as ONLY the universal +20%
        rank line (0.2) — confirming here that the fix doesn't add a second, spurious contribution even
        under conditions that would have tripped the pre-fix bug."""
        from engine.support_mapper import map_line
        bolt_line = _line("thunder_core_lightning_lasso_noble", 2)
        conds = {"numbed_stacks": 10, "enemy_numbed": True}
        assert map_line(bolt_line, 1, conds=conds) == []


# ── Defect 2: _is_dup's scope-qualifier strip ─────────────────────────────────────────────────────
class TestIsDupScopeQualifier:
    def test_modularization_compress_physique_not_deduped_against_damage_line(self):
        physique = "-25 % Physique for Minions summoned by the supported skill"
        dmg = "+34 % additional damage for Minions summoned by the supported skill"
        assert _is_dup(physique, dmg) is False

    def test_modularization_compress_aggressiveness_not_deduped_against_damage_line(self):
        aggro = "+50 % Aggressiveness for Minions summoned by the supported skill"
        dmg = "+34 % additional damage for Minions summoned by the supported skill"
        assert _is_dup(aggro, dmg) is False

    def test_groundshaker_skill_area_not_deduped_against_demolisher_gate_fragment(self):
        skill_area = "+30 % additional Skill Area when the supported skill consumes Demolisher Charge"
        gate_fragment = "When the cast of the Supported Skill consumes Demolisher Charge ,"
        assert _is_dup(skill_area, gate_fragment) is False

    def test_genuine_duplicate_still_detected(self):
        """Sanity: the scope-strip doesn't blanket-disable dedup — two IDENTICAL clauses are still a dup."""
        dmg = "+34 % additional damage for Minions summoned by the supported skill"
        assert _is_dup(dmg, dmg) is True

    def test_build_tooltip_emits_physique_and_aggressiveness_lines(self):
        """End-to-end: modularization_compress_noble's tooltip must carry BOTH previously-swallowed
        clauses now."""
        spec = build_tooltip(_BY_ID["modularization_compress_noble"])
        texts = " | ".join((ln.get("text") or ln.get("badge_text") or "") for ln in spec["lines"])
        assert "physique" in texts.lower()
        assert "aggressiveness" in texts.lower()

    def test_groundshaker_cripple_noble_emits_skill_area_line(self):
        """Companion end-to-end check (the OTHER item named in the same fix's docstring)."""
        spec = build_tooltip(_BY_ID["groundshaker_cripple_noble"])
        texts = " | ".join((ln.get("text") or ln.get("badge_text") or "") for ln in spec["lines"])
        assert "skill area" in texts.lower()


# ── Confident/strict coverage classifier ──────────────────────────────────────────────────────────
class TestConfidentStrictResolution:
    """`server._resolve_skill_line_keys(text, item_id, strict=True)` (engine.coverage's classifier)
    excludes a key whose ONLY resolution was a low-confidence fuzzy overlap match
    (`mod_parser._resolve_gear_stat`'s ranked fallback with leftover query words); `strict=False`
    (the default, used by badges / /api/map-modifiers) is unaffected."""

    _FUZZY_TEXT = "21% additional Damage Over Time and 30 Affliction Per Second."  # precise_deep_pain

    def test_strict_true_rejects_low_confidence_match(self):
        from server import _resolve_skill_line_keys
        assert _resolve_skill_line_keys(self._FUZZY_TEXT, strict=True) == []

    def test_strict_false_default_unchanged(self):
        from server import _resolve_skill_line_keys
        keys_default = _resolve_skill_line_keys(self._FUZZY_TEXT)
        keys_explicit_false = _resolve_skill_line_keys(self._FUZZY_TEXT, strict=False)
        assert keys_default == keys_explicit_false == ["dot_dmg_additional"]

    def test_the_underlying_parse_is_indeed_low_confidence(self):
        """Confirms the fixture text is actually exercising the fuzzy/low-confidence path (not a
        confident regex match) — otherwise this test would silently stop testing anything."""
        from engine.mod_parser import _parse_custom_mod_text
        parsed = _parse_custom_mod_text(self._FUZZY_TEXT)
        assert parsed and parsed[0]["stat_key"] == "dot_dmg_additional"
        assert parsed[0]["confident"] is False
