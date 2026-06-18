"""Spell Burst — an eligible Spell cast at full charge consumes all M (Max Spell Burst) stacks and auto-recasts
the spell M times; the triggering cast also counts (casts_per_burst = M + 1, no damage cap). The charge is a
server-timed whole-tick countdown (hard-rounded breakpoints, 30 Hz — engine/tick.py), so charge speed only helps
at integer-tick crossings; the player's cast rate stays smooth (and 30-capped). See the approved plan.

Model (owner-confirmed): tickrate 30 cap on everything; no damage cap (every stack is a full cast); recasts are
instant on trigger (only the burst RATE is tick-limited); auto-trigger fires the tick it's charged, manual waits
for the next player cast at/after the charge tick. Spell-burst-only damage pools (spell_burst_hit_dmg_additional)
apply to burst casts via the "spell_burst" tag; per-stack-consumed (Heart of Flame) and per-activation (Prairie
Fire) bonuses feed that pool.
"""
import math
import pytest

from tests.mock_build import make_request, DUAL_WEAPONS
from server import engine_stats, EngineStatsRequest
from engine import mod_parser as mp
from engine import tick

_SPELL = "chain_lightning"   # an eligible Spell (no cooldown, not channeled) → bursts inherently when M ≥ 1


def _gear_with(**stats):
    """DUAL_WEAPONS plus one item carrying the given engine stats (gear contribution format)."""
    return DUAL_WEAPONS + [{"item_name": "SBItem", "contributions": [
        {"stat": k, "display_value": v, "unit": "", "slot": "ring", "item_name": "SBItem",
         "text": f"+{v} {k}"} for k, v in stats.items()]}]


def _offense(max_burst=0, supports=None, conds=None, extra_gear=None):
    gear = DUAL_WEAPONS
    if max_burst or extra_gear:
        stats = dict(extra_gear or {})
        if max_burst:
            stats["max_spell_burst_flat"] = max_burst
        gear = _gear_with(**stats)
    r = engine_stats(EngineStatsRequest(**make_request(
        _SPELL, 20, attached_supports=supports, gear=gear, extra_conditions=conds)))
    d = r.model_dump() if hasattr(r, "model_dump") else r
    return d["offense"]


def _hit(o):
    return o["hit_forms"][0]["avg_hit_with_crit"]


# ── Tick helper ────────────────────────────────────────────────────────────────
class TestTickHelper:
    def test_cap_rate_clamps_at_30(self):
        assert tick.cap_rate(45.0) == 30.0
        assert tick.cap_rate(12.0) == 12.0
        assert tick.cap_rate(0.0) == 0.0

    def test_period_ticks_ceils(self):
        assert tick.period_ticks(2.0) == 60        # exactly 60 ticks
        assert tick.period_ticks(1.97) == 60       # 59.1 → ceil 60 (dead zone)
        assert tick.period_ticks(1.96) == 59       # 58.8 → ceil 59
        assert tick.period_ticks(0.0) == 1         # min one tick

    def test_rate_from_ticks(self):
        assert tick.rate_from_ticks(60) == 0.5
        assert tick.rate_from_ticks(30) == 1.0


# ── Detection / eligibility ──────────────────────────────────────────────────────
class TestDetection:
    def test_no_max_spell_burst_no_burst(self):
        o = _offense(max_burst=0)
        assert o["spell_burst_count"] == 0 and o["spell_burst_mult"] == 1.0

    def test_eligible_spell_bursts_at_max(self):
        o = _offense(max_burst=3)
        assert o["spell_burst_count"] == 3
        assert o["spell_burst_casts_per_burst"] == 4      # M + 1 (the triggering cast counts)

    def test_active_toggle_off_reverts_to_normal_cast(self):
        burst = _offense(max_burst=3)
        normal = _offense(max_burst=3, conds={"spell_burst_active": False})
        assert normal["spell_burst_count"] == 0 and normal["spell_burst_mult"] == 1.0
        # normal-cast DPS is the plain single-cast DPS (no burst multiplier)
        base = _offense(max_burst=0)
        assert normal["total_dps_vs_target"] == pytest.approx(base["total_dps_vs_target"])
        assert burst["total_dps_vs_target"] != pytest.approx(base["total_dps_vs_target"])


# ── Damage scaling ───────────────────────────────────────────────────────────────
class TestDamageScaling:
    def test_dps_equals_per_cast_times_casts_per_burst_times_rate(self):
        base = _offense(max_burst=0)
        o = _offense(max_burst=3, conds={"spell_burst_auto_trigger": True})
        per_cast_dps = base["total_dps_vs_target"]      # = per_cast × aps
        aps = base["attacks_per_second"]
        expected = per_cast_dps / aps * o["spell_burst_casts_per_burst"] * o["spell_burst_rate"]
        assert o["total_dps_vs_target"] == pytest.approx(expected)

    def test_max_spell_burst_scales_linearly_no_cap(self):
        # Auto-trigger: charge_ticks is independent of M, so bursts/sec is fixed → DPS ∝ (M + 1). No cap, even high.
        a = _offense(max_burst=3, conds={"spell_burst_auto_trigger": True})
        b = _offense(max_burst=7, conds={"spell_burst_auto_trigger": True})
        c = _offense(max_burst=20, conds={"spell_burst_auto_trigger": True})
        assert b["total_dps_vs_target"] == pytest.approx(a["total_dps_vs_target"] * 8 / 4)
        assert c["total_dps_vs_target"] == pytest.approx(a["total_dps_vs_target"] * 21 / 4)


# ── Charge-speed breakpoints (hard-rounded; dead zones) ──────────────────────────
class TestChargeBreakpoints:
    def test_dead_zone_then_jump(self):
        # Auto-trigger so bursts/sec = 30 / charge_ticks exactly. Base charge T = 2s → 60 ticks.
        t0 = _offense(max_burst=3, conds={"spell_burst_auto_trigger": True})
        # +1% charge speed → T = 1.980s → 59.4 ticks → ceil 60: NO change (dead zone).
        t1 = _offense(max_burst=3, conds={"spell_burst_auto_trigger": True},
                      extra_gear={"spell_burst_charge_speed_inc": 0.01})
        # +5% charge speed → T = 1.905s → 57.1 ticks → ceil 58: faster.
        t5 = _offense(max_burst=3, conds={"spell_burst_auto_trigger": True},
                      extra_gear={"spell_burst_charge_speed_inc": 0.05})
        assert t0["spell_burst_charge_ticks"] == 60
        assert t1["spell_burst_charge_ticks"] == 60                 # dead zone — no gain
        assert t1["spell_burst_rate"] == pytest.approx(t0["spell_burst_rate"])
        assert t5["spell_burst_charge_ticks"] == 58                 # crossed a breakpoint
        assert t5["spell_burst_rate"] > t0["spell_burst_rate"]

    def test_charge_speed_halves_at_full_tick(self):
        # +100% charge speed → factor 2 → T = 1.0s → 30 ticks → rate 1.0 (double base 0.5).
        o = _offense(max_burst=3, conds={"spell_burst_auto_trigger": True},
                     extra_gear={"spell_burst_charge_speed_inc": 1.0})
        assert o["spell_burst_charge_ticks"] == 30
        assert o["spell_burst_rate"] == pytest.approx(1.0)


# ── Surging Inspiration (alternative fill) ───────────────────────────────────────
class TestSurging:
    def test_surging_shortens_charge(self):
        base = _offense(max_burst=3, conds={"spell_burst_auto_trigger": True})
        # Big surging rate fills to max faster than the 2s base charge → fewer charge ticks.
        surge = _offense(max_burst=3, conds={"spell_burst_auto_trigger": True},
                         extra_gear={"spell_burst_chance_gain_stacks_flat": 5.0})
        assert surge["spell_burst_charge_ticks"] < base["spell_burst_charge_ticks"]


# ── Manual cast-rate gate ────────────────────────────────────────────────────────
class TestManualCastGate:
    def test_manual_never_faster_than_auto(self):
        auto = _offense(max_burst=3, conds={"spell_burst_auto_trigger": True})
        manual = _offense(max_burst=3)   # default auto off
        assert manual["spell_burst_rate"] <= auto["spell_burst_rate"] + 1e-9


# ── Combined manual model (burst + non-burst) vs burst-only auto ──────────────────
class TestCombinedModel:
    def test_manual_splits_burst_and_non_burst(self):
        # Manual: total = burst casts + the normal casts between them; both parts surfaced and sum to total.
        o = _offense(max_burst=3)
        assert not o["spell_burst_auto"]
        assert o["spell_burst_dps_vs_target"] > 0
        assert o["non_spell_burst_dps_vs_target"] > 0
        assert o["total_dps_vs_target"] == pytest.approx(
            o["spell_burst_dps_vs_target"] + o["non_spell_burst_dps_vs_target"])

    def test_auto_has_no_non_burst(self):
        # Auto-trigger: you do not cast manually → no between-burst casts.
        o = _offense(max_burst=3, conds={"spell_burst_auto_trigger": True})
        assert o["spell_burst_auto"]
        assert o["non_spell_burst_dps_vs_target"] == pytest.approx(0.0)
        assert o["total_dps_vs_target"] == pytest.approx(o["spell_burst_dps_vs_target"])

    def test_manual_beats_auto_via_between_casts(self):
        # Same M/charge: manual adds the between-burst casts on top of the same burst component → higher total.
        manual = _offense(max_burst=3)
        auto = _offense(max_burst=3, conds={"spell_burst_auto_trigger": True})
        assert manual["spell_burst_dps_vs_target"] == pytest.approx(auto["spell_burst_dps_vs_target"])
        assert manual["total_dps_vs_target"] > auto["total_dps_vs_target"]

    def test_burst_pool_lifts_only_burst_part(self):
        # +50% Spell Burst Hit Damage boosts the burst component ×1.5; the non-burst part is unchanged.
        plain = _offense(max_burst=3)
        boosted = _offense(max_burst=3, extra_gear={"spell_burst_hit_dmg_additional": 0.5})
        assert boosted["spell_burst_dps_vs_target"] == pytest.approx(1.5 * plain["spell_burst_dps_vs_target"])
        assert boosted["non_spell_burst_dps_vs_target"] == pytest.approx(plain["non_spell_burst_dps_vs_target"])


# ── Spell-burst-only damage pool ─────────────────────────────────────────────────
class TestBurstDamagePool:
    def test_pool_applies_only_in_burst(self):
        # +50% Spell Burst Hit Damage → burst casts deal ×1.5; inert when not bursting.
        plain = _offense(max_burst=3)
        boosted = _offense(max_burst=3, extra_gear={"spell_burst_hit_dmg_additional": 0.5})
        assert _hit(boosted) == pytest.approx(1.5 * _hit(plain))
        # toggle burst off → the spell_burst pool is inert (tagged spell_burst, not applied)
        off_plain = _offense(max_burst=3, conds={"spell_burst_active": False})
        off_boost = _offense(max_burst=3, conds={"spell_burst_active": False},
                             extra_gear={"spell_burst_hit_dmg_additional": 0.5})
        assert _hit(off_boost) == pytest.approx(_hit(off_plain))


# ── Per-support ramped bonuses (owner §7) ────────────────────────────────────────
class TestRampedBonuses:
    _HOF = [{"slot": 1, "item_id": "fire_burst_heart_of_flame_magnificent", "level": 20, "enabled": True}]
    _PF = [{"slot": 1, "item_id": "fire_burst_prairie_fire_noble", "level": 20, "enabled": True}]

    def test_heart_of_flame_scales_per_stack_consumed(self):
        # +10.5% per stack consumed (stacks consumed = M), up to 6. Per-cast hit damage isolates the pool:
        # ratio (1 + 0.105·3)/(1 + 0.105·1) = 1.315/1.105.
        m1 = _offense(max_burst=1, supports=self._HOF)
        m3 = _offense(max_burst=3, supports=self._HOF)
        assert _hit(m3) / _hit(m1) == pytest.approx(1.315 / 1.105, rel=1e-4)

    def test_heart_of_flame_caps_at_six(self):
        m6 = _offense(max_burst=6, supports=self._HOF)
        m9 = _offense(max_burst=9, supports=self._HOF)   # min(9, 6) = 6 → same per-cast bonus
        assert _hit(m9) == pytest.approx(_hit(m6))

    def test_prairie_fire_is_at_cap_regardless_of_m(self):
        # Per-activation ramp assumed at cap (×6) for sustained DPS → independent of M.
        assert _hit(_offense(max_burst=3, supports=self._PF)) == pytest.approx(_hit(_offense(max_burst=1, supports=self._PF)))


# ── Global 30/s cap ──────────────────────────────────────────────────────────────
class TestGlobalCap:
    def test_aps_capped_at_30(self):
        # A huge cast-speed bonus would push aps far past 30; the per-caster cap holds it at 30.
        o = _offense(max_burst=0, extra_gear={"cast_speed_inc": 50.0})
        assert o["attacks_per_second"] == pytest.approx(30.0)


# ── Parser regression ────────────────────────────────────────────────────────────
class TestParser:
    def test_burst_pools_map(self):
        m = lambda t: mp._parse_custom_mod_text(t)[0]["stat_key"]
        assert m("+2 Max Spell Burst") == "max_spell_burst_flat"
        assert m("+30 % Spell Burst Charge Speed") == "spell_burst_charge_speed_inc"
        assert m("-25 % additional Spell Burst Charge Speed") == "spell_burst_charge_speed_additional"

    def test_flat_burst_damage_line_with_trailing_clause(self):
        r = mp._parse_custom_mod_text(
            "+26 % additional Hit Damage for skills cast by Spell Burst when Spell Burst is activated by the supported skill")
        assert r[0]["stat_key"] == "spell_burst_hit_dmg_additional"
        assert r[0]["amount"] == pytest.approx(0.26)

    def test_ramped_burst_lines_do_not_map_flat(self):
        # The per-stack / per-activation variants must NOT map via the flat matcher (they're hand-modeled).
        assert mp._parse_custom_mod_text(
            "+10.5 % additional Hit Damage for skills cast by Spell Burst for every 1 stack(s) of Spell Burst Charge consumed. Stacks up to 6 time(s)") == []

    def test_surging_maps_to_expected_stacks(self):
        r = mp._parse_custom_mod_text(
            "+30 % chance to immediately gain 2 stack(s) of Spell Burst Charge when using a skill")
        assert r[0]["stat_key"] == "spell_burst_chance_gain_stacks_flat"
        assert r[0]["amount"] == pytest.approx(0.6)   # chance × stacks
