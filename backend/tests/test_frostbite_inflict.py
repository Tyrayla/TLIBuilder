"""Frostbite inflict detection (engine.ailment_inflict.scan_frostbite_inflict / _classify_frostbite) —
mirrors TestScan in test_ailment_inflict.py for the Numbed side. Unlike Numbed, Frostbite has no user stack
count — an inflict line only enables the enemy_frostbitten gate (gated on the build dealing Cold Damage).
"cannot inflict Frostbite" hard-overrides everything, and a handful of non-inflict Frostbite lines (effect /
rating / threshold wording) must never register as an inflict source.
"""
import pytest
from engine.ailment_inflict import scan_frostbite_inflict, _classify_frostbite
from server import engine_stats, EngineStatsRequest
from tests.mock_build import make_request, DUAL_WEAPONS

COLD_A = "Inflicts Frostbite when dealing Hit Cold Damage"
BLOCK = "The supported skill cannot inflict Ignite, Frostbite or Numbed"


class TestScan:
    def test_cold_inflict_detected(self):
        s = scan_frostbite_inflict([COLD_A])
        assert s.cold and not s.blocked and s.active

    def test_block(self):
        assert scan_frostbite_inflict([COLD_A, BLOCK]).blocked

    def test_block_overrides_cold(self):
        # Blocked still reports active (so the caller knows the line was recognized), but emits no effects —
        # the hard override wins over an otherwise-present Cold inflict source.
        s = scan_frostbite_inflict([COLD_A, BLOCK])
        assert s.active
        assert s.condition_effects() == []

    def test_block_alone(self):
        s = scan_frostbite_inflict([BLOCK])
        assert s.blocked and s.active and s.condition_effects() == []

    def test_no_lines_inactive(self):
        assert not scan_frostbite_inflict([]).active

    def test_excludes_frostbite_effect(self):
        assert _classify_frostbite("+20 % Frostbite Effect") is None
        assert not scan_frostbite_inflict(["+20 % Frostbite Effect"]).active

    def test_excludes_max_frostbite_rating(self):
        assert _classify_frostbite("+50 Max Frostbite Rating") is None
        assert not scan_frostbite_inflict(["+50 Max Frostbite Rating"]).active

    def test_excludes_frostbite_rating(self):
        assert _classify_frostbite("Frostbite Rating is doubled while Chilled") is None
        assert not scan_frostbite_inflict(["Frostbite Rating is doubled while Chilled"]).active

    def test_excludes_thresholds_for_inflicting(self):
        assert _classify_frostbite("-10 % to Cold thresholds for inflicting Frostbite") is None
        assert not scan_frostbite_inflict(["-10 % to Cold thresholds for inflicting Frostbite"]).active

    def test_matches_helper(self):
        s = scan_frostbite_inflict([])
        assert s.matches(COLD_A)
        assert s.matches(BLOCK)
        assert not s.matches("+20 % Frostbite Effect")
        assert not s.matches("+50 Max Frostbite Rating")


class TestEngine:
    """End-to-end through the real engine (server.engine_stats) — the block override must actually suppress
    the enemy_frostbitten gate the whole way through, not just at the scan/classify layer."""

    def _dps(self, custom=None, gear=None, conds=None):
        req = make_request("icebound_beam", 16, gear=gear, extra_conditions=conds)
        if custom:
            req["custom_mods"] = custom
        r = engine_stats(EngineStatsRequest(**req))
        d = r.model_dump() if hasattr(r, "model_dump") else r
        return d["offense"]["total_dps"]

    def _gear_with_rating(self, rating):
        return DUAL_WEAPONS + [{"item_name": "FB", "contributions": [
            {"stat": "max_frostbite_rating_flat", "display_value": rating, "unit": "", "slot": "ring",
             "item_name": "FB", "text": f"+{rating} Max Frostbite Rating"}]}]

    def test_block_line_suppresses_auto_apply(self):
        base = self._dps(gear=self._gear_with_rating(50))
        blocked = self._dps(custom=[COLD_A, BLOCK], gear=self._gear_with_rating(50))
        assert blocked == pytest.approx(base)   # cannot-inflict wins → no Frostbite bonus at all

    def test_block_does_not_override_manual_toggle(self):
        base = self._dps(gear=self._gear_with_rating(50))
        blocked = self._dps(custom=[BLOCK], gear=self._gear_with_rating(50), conds={"enemy_frostbitten": True})
        # "cannot inflict Frostbite" only withholds the engine's AUTO-apply condition_effects; it does not
        # clear a manually-toggled enemy_frostbitten value. Symmetric with Numbed's block (see
        # test_ailment_inflict.py::TestEngine::test_block_does_not_override_manual_value) — manual override
        # wins over the block for both ailments.
        assert blocked > base
