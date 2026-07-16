"""Tangles — a Spell turned into a Tangle (via the Spell Tangle activator) is cast by N attached tangles, not
the player. Tangle DPS = single-cast offense × attached_count × (1 + Σ Tangle Damage Enhancement), with the
tangle damage / additional / crit pools applying via the "tangle" tag. See the approved plan.

Model (Tyra-confirmed): each tangle is a full caster; attached_count = min(1 + extra_tangle_applied_flat,
2 + max_tangle_quantity_flat) (default 1); active_tangles condition can lower it (never raise); Tangle Damage
Enhancement is its OWN multiplier that stacks additively with itself; Dormant Entanglement = +40% additional
Tangle Damage per inactivated tangle (placeable − active), gated on has_dormant_entanglement.
"""
import pytest

from tests.mock_build import make_request, DUAL_WEAPONS
from server import engine_stats, EngineStatsRequest
from engine import mod_parser as mp

_SPELL = "chain_lightning"   # a Spell skill → eligible for Tangle
_ACTIVATOR = [{"slot": 1, "item_id": "spell_tangle", "level": 20, "enabled": True}]


def _offense(supports=None, gear=None, conds=None):
    r = engine_stats(EngineStatsRequest(**make_request(
        _SPELL, 20, attached_supports=supports, gear=gear, extra_conditions=conds)))
    d = r.model_dump() if hasattr(r, "model_dump") else r
    return d["offense"]


def _gear_with(**stats):
    """DUAL_WEAPONS plus one item carrying the given engine stats (gear contribution format)."""
    return DUAL_WEAPONS + [{"item_name": "TangleItem", "contributions": [
        {"stat": k, "display_value": v, "unit": "", "slot": "ring", "item_name": "TangleItem",
         "text": f"+{v} {k}"} for k, v in stats.items()]}]


class TestActivation:
    def test_no_activator_not_tangled(self):
        assert _offense()["tangle_count"] == 0

    def test_spell_tangle_activates(self):
        assert _offense(supports=_ACTIVATOR)["tangle_count"] == 1

    def test_manifold_is_not_an_activator(self):
        # Manifold Entanglement is a normal damage support, NOT a tangle activator.
        o = _offense(supports=[{"slot": 1, "item_id": "manifold_entanglement", "level": 20, "enabled": True}])
        assert o["tangle_count"] == 0


class TestCountScaling:
    def test_count_doubles_dps(self):
        c1 = _offense(supports=_ACTIVATOR)
        c2 = _offense(supports=_ACTIVATOR, gear=_gear_with(extra_tangle_applied_flat=1))
        assert c2["tangle_count"] == 2
        assert c2["total_dps_vs_target"] == pytest.approx(2 * c1["total_dps_vs_target"])

    def test_attached_capped_by_placeable(self):
        # +5 apply but only base 2 placeable → attached capped at 2.
        o = _offense(supports=_ACTIVATOR, gear=_gear_with(extra_tangle_applied_flat=5))
        assert o["tangle_count"] == 2

    def test_active_tangles_condition_lowers_only(self):
        cap2 = _gear_with(extra_tangle_applied_flat=1)
        c1 = _offense(supports=_ACTIVATOR)                              # count 1
        lowered = _offense(supports=_ACTIVATOR, gear=cap2, conds={"active_tangles": 1})
        assert lowered["tangle_count"] == 1
        assert lowered["total_dps_vs_target"] == pytest.approx(c1["total_dps_vs_target"])
        # cannot raise above the cap (cap here is 2)
        raised = _offense(supports=_ACTIVATOR, gear=cap2, conds={"active_tangles": 9})
        assert raised["tangle_count"] == 2


class TestEnhancement:
    def test_enhancement_separate_multiplier(self):
        base = _offense(supports=_ACTIVATOR)
        enh = _offense(supports=_ACTIVATOR, gear=_gear_with(tangle_dmg_enhancement_additional=0.50))
        assert enh["tangle_enhancement"] == pytest.approx(1.50)
        assert enh["total_dps_vs_target"] == pytest.approx(1.5 * base["total_dps_vs_target"])

    def test_enhancement_additive_within_itself(self):
        # Two 0.56 enhancement sources sum to 1.12 → ×2.12 (additive within itself, NOT multiplicative).
        enh = _offense(supports=_ACTIVATOR, gear=DUAL_WEAPONS + [
            {"item_name": "A", "contributions": [{"stat": "tangle_dmg_enhancement_additional", "display_value": 0.56,
                                                  "unit": "", "slot": "ring", "item_name": "A", "text": "+0.56 a"}]},
            {"item_name": "B", "contributions": [{"stat": "tangle_dmg_enhancement_additional", "display_value": 0.56,
                                                  "unit": "", "slot": "amulet", "item_name": "B", "text": "+0.56 b"}]},
        ])
        assert enh["tangle_enhancement"] == pytest.approx(2.12)


class TestDormantEntanglement:
    def test_dormant_adds_per_inactivated(self):
        # placeable 2, active 1 → 1 inactivated → +40% additional Tangle Damage when Dormant is enabled.
        cap2 = _gear_with(extra_tangle_applied_flat=1)
        base = _offense(supports=_ACTIVATOR, gear=cap2, conds={"active_tangles": 1})           # count 1, no dormant
        dorm = _offense(supports=_ACTIVATOR, gear=cap2,
                        conds={"active_tangles": 1, "has_dormant_entanglement": True})          # 1 inactivated
        assert base["tangle_count"] == 1 and dorm["tangle_count"] == 1
        assert dorm["total_dps_vs_target"] == pytest.approx(1.40 * base["total_dps_vs_target"])

    def test_dormant_inert_without_flag(self):
        cap2 = _gear_with(extra_tangle_applied_flat=1)
        no = _offense(supports=_ACTIVATOR, gear=cap2, conds={"active_tangles": 1})
        # no flag → no inactivated bonus even though 1 tangle is inactivated
        assert no["tangle_enhancement"] == pytest.approx(1.0)


class TestCastSpeedBreakpoints:
    """Tangle cast rate hard-rounds to whole server ticks: ticks = ceil(cast_time × 30), rate = 30 / ticks.
    Tyra in-game validation: 6.04 and 7.44 casts/s gave IDENTICAL DPS — both fall in the 5-tick bucket
    (effective 6.0/s); the next breakpoint is exactly 7.5/s (4 ticks). This locks that formula in."""
    def test_owner_validated_6_04_and_7_44_same_bucket(self):
        from engine.tick import period_ticks, rate_from_ticks, TICK_RATE
        assert TICK_RATE == 30
        # Both raw rates round UP to 5 whole ticks → identical 6.0/s effective (the observed equal-DPS pair).
        assert period_ticks(1.0 / 6.04) == 5
        assert period_ticks(1.0 / 7.44) == 5
        assert rate_from_ticks(5) == pytest.approx(6.0)

    def test_next_breakpoint_is_7_5(self):
        from engine.tick import period_ticks, rate_from_ticks
        assert period_ticks(1.0 / 7.49) == 5          # just below → still 5 ticks
        assert period_ticks(1.0 / 7.5) == 4           # exactly 7.5/s crosses to 4 ticks
        assert rate_from_ticks(4) == pytest.approx(7.5)

    def test_within_bucket_identical_dps_across_breakpoint_increases(self):
        # End-to-end: two different (small) cast-speed boosts that stay inside the same tick bucket give the
        # SAME tangle DPS + cast ticks; a large boost that crosses a breakpoint raises DPS.
        base = _offense(supports=_ACTIVATOR)
        small_a = _offense(supports=_ACTIVATOR, gear=_gear_with(cast_speed_inc=0.01))
        small_b = _offense(supports=_ACTIVATOR, gear=_gear_with(cast_speed_inc=0.02))
        assert small_a["tangle_cast_ticks"] == base["tangle_cast_ticks"]
        assert small_b["tangle_cast_ticks"] == base["tangle_cast_ticks"]
        assert small_a["total_dps_vs_target"] == pytest.approx(small_b["total_dps_vs_target"])
        big = _offense(supports=_ACTIVATOR, gear=_gear_with(cast_speed_inc=5.0))
        assert big["tangle_cast_ticks"] < base["tangle_cast_ticks"]
        assert big["total_dps_vs_target"] > base["total_dps_vs_target"]


def _resp(supports=None, gear=None, conds=None):
    r = engine_stats(EngineStatsRequest(**make_request(
        _SPELL, 20, attached_supports=supports, gear=gear, extra_conditions=conds)))
    return r.model_dump() if hasattr(r, "model_dump") else r


def _gear_per_activated(stat, value, extra=0):
    """DUAL_WEAPONS + an item whose `stat` contribution is gated 'for each activated Tangle' (scales by the
    derived active-tangle count), optionally with +extra to the attach cap."""
    contribs = [{"stat": stat, "display_value": value, "unit": "%", "slot": "ring", "item_name": "PerTangle",
                 "text": f"+{value}% {stat} for each activated Tangle",
                 "condition": {"key": "active_tangle_count", "op": "per", "divisor": 1}}]
    if extra:
        contribs.append({"stat": "extra_tangle_applied_flat", "display_value": extra, "unit": "", "slot": "ring",
                         "item_name": "PerTangle", "text": f"+{extra} tangle"})
    return DUAL_WEAPONS + [{"item_name": "PerTangle", "contributions": contribs}]


class TestDerivedCounts:
    def test_active_tangle_count_injected(self):
        assert _resp(supports=_ACTIVATOR)["auto_conditions"]["active_tangle_count"]["value"] == pytest.approx(1)
        d2 = _resp(supports=_ACTIVATOR, gear=_gear_with(extra_tangle_applied_flat=1))
        assert d2["auto_conditions"]["active_tangle_count"]["value"] == pytest.approx(2)

    def test_inactivated_tangle_count_injected(self):
        # placeable 2, active pinned to 1 → 1 inactivated.
        d = _resp(supports=_ACTIVATOR, gear=_gear_with(extra_tangle_applied_flat=1), conds={"active_tangles": 1})
        assert d["auto_conditions"]["inactivated_tangle_count"]["value"] == pytest.approx(1)

    def test_no_counts_on_non_tangle_build(self):
        assert "active_tangle_count" not in _resp()["auto_conditions"]


class TestPerTangleScaling:
    def test_per_activated_line_scales_with_count(self):
        # spell_dmg_inc "for each activated Tangle". The base tangle count multiplies every build equally, so the
        # WITH/WITHOUT ratio isolates the per-tangle bonus — and that ratio must grow with the count.
        no = _gear_with(extra_tangle_applied_flat=1)                        # cap 2, no per-tangle bonus
        yes = _gear_per_activated("spell_dmg_inc", 50, extra=1)             # cap 2, +50% spell dmg / activated tangle
        base1 = _offense(supports=_ACTIVATOR, gear=no,  conds={"active_tangles": 1})
        base2 = _offense(supports=_ACTIVATOR, gear=no,  conds={"active_tangles": 2})
        with1 = _offense(supports=_ACTIVATOR, gear=yes, conds={"active_tangles": 1})
        with2 = _offense(supports=_ACTIVATOR, gear=yes, conds={"active_tangles": 2})
        r1 = with1["total_dps_vs_target"] / base1["total_dps_vs_target"]
        r2 = with2["total_dps_vs_target"] / base2["total_dps_vs_target"]
        assert r1 > 1.0            # bonus applied at 1 activated tangle
        assert r2 > r1 + 1e-6      # scales up — 2× the spell damage at 2 activated tangles

    def test_per_tangle_line_inert_without_activator(self):
        # No activator → active_tangle_count is 0/absent → floor(0)=0 → the conditional contribution is skipped.
        none = _offense(gear=DUAL_WEAPONS)
        withg = _offense(gear=_gear_per_activated("spell_dmg_inc", 50))
        assert withg["total_dps_vs_target"] == pytest.approx(none["total_dps_vs_target"])


class TestPerTangleTranslation:
    def test_translate_condition_texts(self):
        from server import _translate_condition_expr as T
        assert T("for each activated Tangle") == {"key": "active_tangle_count", "op": "per", "divisor": 1}
        assert T("per activated Tangle") == {"key": "active_tangle_count", "op": "per", "divisor": 1}
        assert T("for every Tangle") == {"key": "active_tangle_count", "op": "per", "divisor": 1}
        assert T("for each inactivated Tangle") == {"key": "inactivated_tangle_count", "op": "per", "divisor": 1}
        assert T("per dormant Tangle") == {"key": "inactivated_tangle_count", "op": "per", "divisor": 1}


class TestMagisterGenerateNodes:
    _FOCUS = "Gains 1 stack(s) of Focus Blessing when activating Spell Burst or generating Tangle (Max Divinity Effect: 1)"
    _ESCHG = "When activating Spell Burst or generating Tangle, immediately starts Charging Energy Shield. Interval: 2 s (Max Divinity Effect: 1)"

    def test_focus_blessing_node_parses_to_flag(self):
        assert mp._parse_custom_mod_text(self._FOCUS)[0]["stat_key"] == "focus_blessing_full_uptime_flag"

    def test_es_charge_node_recognized_not_dropped(self):
        # Recognized-but-NYI: emits a flag (surfaces) rather than silently dropping.
        assert mp._parse_custom_mod_text(self._ESCHG)[0]["stat_key"] == "es_charge_on_generate_flag"

    def test_focus_blessing_forced_to_max_when_generating_tangle(self):
        d = _resp(supports=_ACTIVATOR, gear=_gear_with(focus_blessing_full_uptime_flag=1))
        fb = d["auto_conditions"].get("focus_blessings")
        assert fb and fb["value"] > 0

    def test_focus_blessing_not_forced_without_generate(self):
        # Flag present but the build neither generates tangles nor bursts → the blessing is NOT pinned.
        d = _resp(gear=_gear_with(focus_blessing_full_uptime_flag=1))
        assert "focus_blessings" not in d["auto_conditions"]


class TestParserRegression:
    def test_enhancement_maps_to_enhancement_not_inc(self):
        assert mp._parse_custom_mod_text("140 % Tangle Damage Enhancement")[0]["stat_key"] == "tangle_dmg_enhancement_additional"

    def test_tangle_pools_map(self):
        m = lambda t: mp._parse_custom_mod_text(t)[0]["stat_key"]
        assert m("9 % Tangle Damage") == "tangle_dmg_inc"
        assert m("40 % additional Tangle Damage") == "tangle_dmg_additional"
        assert m("120 Tangle Critical Strike Rating") == "tangle_crit_rating_flat"
        assert m("91 % Tangle Attach Range") == "tangle_attach_range_inc"
