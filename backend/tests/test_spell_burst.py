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


def _offense_spirit(spirit_effects, max_burst=3):
    """Offense with pact-spirit effect lines (for Squiddle / Squidnova)."""
    req = make_request(_SPELL, 20, gear=_gear_with(max_spell_burst_flat=max_burst))
    req["spirit_effects"] = spirit_effects
    r = engine_stats(EngineStatsRequest(**req))
    d = r.model_dump() if hasattr(r, "model_dump") else r
    return d["offense"]


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

    def test_auto_trigger_lines_map(self):
        m = lambda t: mp._parse_custom_mod_text(t)
        assert m("When Spell Burst is fully charged, triggers the supported skill on the nearest enemy within 25m "
                 "and attempts to trigger the supported skill's Spell Burst")[0]["stat_key"] == "spell_burst_auto_trigger_flag"
        sr = m("When Burst Charge Recovery Speed is at least 240 % of the base value, reaching the Max Spell Burst "
               "Charge triggers the Main Skill on the nearest enemy within 25m and attempts to activate the Main Spell Skill's Spell Burst")
        assert sr[0]["stat_key"] == "spell_burst_auto_charge_threshold" and sr[0]["amount"] == pytest.approx(2.4)

    def test_insatiable_greed_and_squidnova_lines_map(self):
        m = lambda t: mp._parse_custom_mod_text(t)[0]
        assert m("150% of the bonuses to Attack Speed is also applied to Spell Burst Charge Speed")["stat_key"] == "attack_speed_to_spell_burst_charge"
        assert m("+1 to Max Spell Burst")["stat_key"] == "max_spell_burst_flat"
        assert m("+25 % Squidnova Effect")["stat_key"] == "squidnova_effect_inc"
        assert m("Activating Spell Burst with at least 6 stack(s) of Max Spell Burst grants 1 stack of Squidnova")["stat_key"] == "has_squidnova_flag"

    def test_solid_river_charge_to_burst_dmg_line_maps(self):
        r = {e["stat_key"]: e["amount"] for e in mp._parse_custom_mod_text(
            "For every +(40-50) % Spell Burst Charge Speed, +(15-20) % additional Hit Damage for skills cast by Spell Burst , up to +80 %")}
        assert r["charge_speed_to_spell_burst_hit_dmg"] == pytest.approx(0.175)
        assert r["charge_speed_to_spell_burst_hit_dmg_per"] == pytest.approx(0.45)
        assert r["charge_speed_to_spell_burst_hit_dmg_cap"] == pytest.approx(0.80)


# ── Auto-trigger from gear/graft (stat-driven) ──────────────────────────────────────
class TestAutoTriggerSources:
    def test_flag_enables_auto(self):
        o = _offense(max_burst=3, extra_gear={"spell_burst_auto_trigger_flag": 1})
        assert o["spell_burst_auto"] and o["spell_burst_auto_source"] == "Burst Activation"
        assert o["non_spell_burst_dps_vs_target"] == pytest.approx(0.0)   # auto → burst-only

    def test_solid_river_threshold_is_conditional_on_charge(self):
        # Threshold 2.4 → auto only when charge_factor ≥ 2.4.
        below = _offense(max_burst=3, extra_gear={"spell_burst_auto_charge_threshold": 2.4, "spell_burst_charge_speed_inc": 0.5})
        above = _offense(max_burst=3, extra_gear={"spell_burst_auto_charge_threshold": 2.4, "spell_burst_charge_speed_inc": 1.5})
        assert not below["spell_burst_auto"]                       # cf 1.5 < 2.4 → manual
        assert above["spell_burst_auto"] and above["spell_burst_auto_source"] == "Solid River / Vorax"

    def test_solid_river_threshold_ignores_additional(self):
        # The gate checks the INCREASED total only (before additional). High additional + low increased must NOT
        # trip it (1 + 0.5 inc = 1.5 < 2.4), even though additional makes the full charge factor large.
        o = _offense(max_burst=3, extra_gear={"spell_burst_auto_charge_threshold": 2.4,
                                              "spell_burst_charge_speed_inc": 0.5,
                                              "spell_burst_charge_speed_additional": 2.0})
        assert not o["spell_burst_auto"]
        # And the exposed increased-only field matches (1 + inc), not the post-additional factor.
        assert o["spell_burst_charge_inc"] == pytest.approx(0.5)

    def test_solid_river_auto_line_from_gear_unresolved_text(self):
        # End-to-end via the real gear path: Solid River's line is a self-contained special affix that the
        # full-clause parse must resolve (not lose to _split_condition). Auto only above the charge threshold.
        line = ("When Burst Charge Recovery Speed is at least 240 % of the base value, reaching the Max Spell "
                "Burst Charge triggers the Main Skill on the nearest enemy within 25m and attempts to activate "
                "the Main Spell Skill's Spell Burst")
        def off(csi):
            req = make_request(_SPELL, 20)
            gi = {"item_name": "Solid River", "contributions": [
                {"stat": "max_spell_burst_flat", "display_value": 14, "unit": "", "slot": "helmet", "item_name": "Solid River", "text": "+14"},
                {"stat": "spell_burst_charge_speed_inc", "display_value": csi, "unit": "", "slot": "helmet", "item_name": "Solid River", "text": "csi"}],
                "unresolved_texts": [line]}
            req["gear"] = DUAL_WEAPONS + [gi]
            r = engine_stats(EngineStatsRequest(**req))
            d = r.model_dump() if hasattr(r, "model_dump") else r
            return d["offense"]
        assert not off(0.5)["spell_burst_auto"]                    # cf 1.5 < 2.4
        assert off(1.5)["spell_burst_auto"]                        # cf 2.5 ≥ 2.4


# ── Spell crit must not include weapon Critical Strike Rating ────────────────────────
class TestSpellCritNoWeaponCSR:
    def test_spell_crit_ignores_weapon_csr(self):
        # A spell uses its innate base 500 CSR only; the worn weapon's Critical Strike Rating must not leak in.
        from tests.mock_build import make_request as _mr
        # chain_lightning (spell) with DUAL_WEAPONS (which carry weapon_crit_rating_flat) → base 5% crit, no leak.
        r = engine_stats(EngineStatsRequest(**_mr(_SPELL, 20, gear=DUAL_WEAPONS)))
        d = r.model_dump() if hasattr(r, "model_dump") else r
        assert d["offense"]["crit_chance"] == pytest.approx(0.05, abs=2e-3)


# ── Insatiable Greed (Attack Speed → Charge Speed) ──────────────────────────────────
class TestInsatiableGreed:
    def test_attack_speed_propagates_to_charge_speed(self):
        base = _offense(max_burst=3)
        ig = _offense(max_burst=3, extra_gear={"attack_speed_to_spell_burst_charge": 1.5, "attack_speed_inc": 0.4})
        # chargeFactor = 1 + 0.4×1.5 = 1.6 → T = 2/1.6 = 1.25s (down from 2.0s base).
        assert ig["spell_burst_charge_time"] == pytest.approx(1.25, rel=1e-3)
        assert ig["spell_burst_charge_time"] < base["spell_burst_charge_time"]

    def test_named_buff_expansion_resolves_gains_insatiable_greed(self):
        # "Gains Insatiable Greed" is a named-buff affix dropped to unresolved_texts; the backend expands it
        # via the glossary so its "150% Attack Speed → Charge Speed" line applies (and the seal clause too).
        from server import _expand_named_buffs
        clauses = _expand_named_buffs("Seals 10 % Max Mana. Gains Insatiable Greed")
        assert any("Attack Speed" in c and "Spell Burst Charge Speed" in c for c in clauses)

    def test_insatiable_greed_works_from_gear_unresolved_text(self):
        def off(unresolved=None):
            req = make_request(_SPELL, 20)
            gi = {"item_name": "IG", "contributions": [
                {"stat": "max_spell_burst_flat", "display_value": 3, "unit": "", "slot": "ring", "item_name": "IG", "text": "+3"},
                {"stat": "attack_speed_inc", "display_value": 0.4, "unit": "", "slot": "ring", "item_name": "IG", "text": "+40%"}]}
            if unresolved:
                gi["unresolved_texts"] = unresolved
            req["gear"] = DUAL_WEAPONS + [gi]
            r = engine_stats(EngineStatsRequest(**req))
            d = r.model_dump() if hasattr(r, "model_dump") else r
            return d["offense"]
        base = off()
        ig = off(["Seals 10 % Max Mana. Gains Insatiable Greed"])
        assert ig["spell_burst_charge_time"] == pytest.approx(1.25, rel=1e-3)   # 40% atk × 1.5 = +60% charge
        assert ig["spell_burst_charge_time"] < base["spell_burst_charge_time"]


# ── Solid River: Charge Speed → Spell Burst Hit Damage ──────────────────────────────
class TestChargeToBurstDamage:
    _SR = {"charge_speed_to_spell_burst_hit_dmg": 0.175, "charge_speed_to_spell_burst_hit_dmg_per": 0.45,
           "charge_speed_to_spell_burst_hit_dmg_cap": 0.80}

    def test_stepwise_scaling(self):
        plain = _offense(max_burst=3, extra_gear={"spell_burst_charge_speed_inc": 1.0})
        sr = _offense(max_burst=3, extra_gear={**self._SR, "spell_burst_charge_speed_inc": 1.0})
        # floor(1.0 / 0.45) = 2 steps × 0.175 = +0.35 burst hit damage.
        assert _hit(sr) / _hit(plain) == pytest.approx(1.35, rel=1e-3)

    def test_capped(self):
        sr = _offense(max_burst=3, extra_gear={**self._SR, "spell_burst_charge_speed_inc": 5.0})
        plain = _offense(max_burst=3, extra_gear={"spell_burst_charge_speed_inc": 5.0})
        # floor(5.0/0.45)=11 steps × 0.175 = 1.925, capped at 0.80 → ×1.80.
        assert _hit(sr) / _hit(plain) == pytest.approx(1.80, rel=1e-3)


# ── Squiddle / Squidnova (auto-enabled when equipped) ───────────────────────────────
class TestSquidnova:
    _R6 = [
        "Activating Spell Burst with at least 6 stack(s) of Max Spell Burst grants 1 stack of Squidnova",
        "+50 % Squidnova Effect",
        "+8 % additional Spell Damage when having Squidnova",
        "+1 to Max Spell Burst when having Squidnova",
    ]

    def test_squidnova_auto_enables_and_grants_buffs(self):
        none = _offense(max_burst=3)
        sq = _offense_spirit(self._R6, max_burst=3)
        assert sq["spell_burst_count"] == 4               # +1 Max Spell Burst from Squidnova (auto-enabled)
        # Squidnova buff base = +16% additional Spell Burst Hit Damage, scaled by +50% Squidnova Effect → +24%;
        # PLUS the SEPARATE +8% additional Spell Damage (Effect does NOT scale it). Both multiply.
        assert _hit(sq) == pytest.approx((1 + 0.16 * 1.5) * 1.08 * _hit(none), rel=1e-3)


# ── Loose ends: Squidnova base buff scaling, skill-area-per-burst, sustain, Destiny kismets ──────────
def _full(max_burst=0, conds=None, extra_gear=None, spirit=None, skill=_SPELL, level=20):
    gear = DUAL_WEAPONS
    stats = dict(extra_gear or {})
    if max_burst:
        stats["max_spell_burst_flat"] = max_burst
    if stats:
        gear = _gear_with(**stats)
    req = make_request(skill, level, gear=gear, extra_conditions=conds)
    if spirit:
        req["spirit_effects"] = spirit
    r = engine_stats(EngineStatsRequest(**req))
    return r.model_dump() if hasattr(r, "model_dump") else r


class TestSquidnovaBaseBuff:
    _GRANT = "Activating Spell Burst with at least 6 stack(s) of Max Spell Burst grants 1 stack of Squidnova"

    def test_base_buff_is_16pct_burst_hit_damage(self):
        none = _offense(max_burst=6)
        sq = _offense_spirit([self._GRANT], max_burst=6)          # grant only → +16% base buff, 0 Effect
        assert _hit(sq) == pytest.approx(1.16 * _hit(none), rel=1e-3)

    def test_effect_scales_base_buff(self):
        none = _offense(max_burst=6)
        sq = _offense_spirit([self._GRANT, "+50 % Squidnova Effect"], max_burst=6)   # +16% × 1.5 = +24%
        assert _hit(sq) == pytest.approx((1 + 0.16 * 1.5) * _hit(none), rel=1e-3)

    def test_effect_does_not_scale_spell_damage_line(self):
        # +8% additional Spell Damage is unaffected by Effect (Effect scales ONLY the +16% burst buff): the ratio of
        # (with Effect) to (without) is purely the burst-buff move 1.24/1.16 — the ×1.08 spell-damage factor cancels.
        base = _offense_spirit([self._GRANT, "+8 % additional Spell Damage when having Squidnova"], max_burst=6)
        eff = _offense_spirit([self._GRANT, "+50 % Squidnova Effect",
                               "+8 % additional Spell Damage when having Squidnova"], max_burst=6)
        assert _hit(eff) / _hit(base) == pytest.approx(1.24 / 1.16, rel=1e-3)


class TestSkillAreaPerBurst:
    def test_area_folds_into_display_not_dps(self):
        # chromatic_shot is a Spell + Area skill that bursts → it has a skill_area_inc display.
        base = _full(max_burst=6, skill="chromatic_shot")
        area = _full(max_burst=6, skill="chromatic_shot", extra_gear={"spell_burst_area_additional_per": 0.10})
        bo, ao = base["offense"], area["offense"]
        assert bo["spell_burst_count"] == 6                                        # confirm it's bursting
        assert ao["skill_area_inc"] == pytest.approx(bo["skill_area_inc"] + 6 * 0.10, rel=1e-3)   # +M×per (display)
        assert ao["total_dps_vs_target"] == pytest.approx(bo["total_dps_vs_target"], rel=1e-3)     # DPS untouched


class TestBurstSustain:
    def test_mana_lost_lowers_net_mana(self):
        base = _full(max_burst=6)
        drain = _full(max_burst=6, extra_gear={"mana_lost_pct_current_per_burst": 0.50})
        assert drain["recovery"]["net_mana_per_sec"] < base["recovery"]["net_mana_per_sec"] - 1e-6

    def test_life_restore_raises_net_life_at_sub_full(self):
        base = _full(max_burst=6, conds={"current_life_pct": 50})
        rest = _full(max_burst=6, conds={"current_life_pct": 50},
                     extra_gear={"life_restored_pct_lost_per_burst": 0.10})
        assert rest["recovery"]["net_life_per_sec"] > base["recovery"]["net_life_per_sec"] + 1e-6

    def test_no_burst_no_sustain(self):
        # No Max Spell Burst → not bursting → burst rate 0 → the drain is inert (keys off the burst TRIGGER).
        base = _full()
        drain = _full(extra_gear={"mana_lost_pct_current_per_burst": 0.50})
        assert drain["recovery"]["net_mana_per_sec"] == pytest.approx(base["recovery"]["net_mana_per_sec"], rel=1e-3)


class TestDestinyKismets:
    def test_upper_limit_line_raises_max_burst(self):
        base = _offense(max_burst=3)
        up = _offense_spirit(["+2 to Spell Burst Upper Limit"], max_burst=3)   # Upper Limit == Max Spell Burst cap
        assert base["spell_burst_count"] == 3 and up["spell_burst_count"] == 5

    def test_halve_upper_limit_floors(self):
        base = _offense(max_burst=6)
        halved = _offense(max_burst=6, extra_gear={"max_spell_burst_halve_flag": 1})
        assert base["spell_burst_count"] == 6 and halved["spell_burst_count"] == 3   # floor(6/2)

    def test_flash_flood_runon_splits_and_feeds_back(self):
        ff = ("Halves Spell Burst Upper Limit +8% additional Attack and Cast Speed for every "
              "Spell Burst triggered recently, up to 40%")
        d = _full(max_burst=6, spirit=[ff])
        assert d["offense"]["spell_burst_count"] == 3           # halved (6 → 3) — the run-on's first clause resolved
        # the AS/CS-per-burst-recently clause derives a stack count from the burst rate (feedback), surfaced as auto
        auto = d.get("auto_conditions") or {}
        assert auto.get("spell_burst_stacks_recently", {}).get("value", 0) > 0


class TestLooseEndsParser:
    def test_new_matchers(self):
        m = lambda t: {r["stat_key"]: round(r["amount"], 4) for r in (mp._parse_custom_mod_text(t) or [])}
        assert m("Loses 50 % current Mana when Spell Burst is activated") == {"mana_lost_pct_current_per_burst": 0.5}
        assert m("Restores 10 % of Lost Life and Energy Shield when activating Spell Burst") == {
            "life_restored_pct_lost_per_burst": 0.1, "energy_shield_restored_pct_lost_per_burst": 0.1}
        assert m("+2 to Spell Burst Upper Limit") == {"max_spell_burst_flat": 2.0}
        assert m("Halves Spell Burst Upper Limit") == {"max_spell_burst_halve_flag": 1.0}

    def test_runon_split_drops_nothing_mappable(self):
        from server import _resolve_effect_modifiers as R
        # Mouth of the Spring: charge speed resolves; the "-5% damage taken" clause is recognized-NYI (no key).
        mos = R("+13.5 % Spell Burst Charge Speed -5 % additional damage taken when Spell Burst Charge is activated",
                is_memory=False)
        assert [d["stat_key"] for d in mos] == ["spell_burst_charge_speed_inc"]
        # normal dual-stat line is untouched by the run-on pre-split.
        both = R("+10 % Fire Damage +5 % Cold Damage", is_memory=False)
        assert {d["stat_key"] for d in both} == {"fire_dmg_inc", "cold_dmg_inc"}
