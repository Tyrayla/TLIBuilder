"""Channeled skills framework — Icebound Beam as the baseline.

A channeled skill gains 1 stack per skill USE; a RESET skill ramps 0→Max over `rounds_per_cycle` uses then
dumps ALL stacks and fires its burst form once per cycle. Min Channeled Stacks shortens the ramp (the first
round from 0 gains 1 + Min). Validated in-game (Tyra): for Icebound Beam (Max 5) Min 3→4 doubles the
detonation rate; Min 4→5 does nothing.

Icebound Beam has two damage FORMS at different cadences, both Cold Spell:
  • Cold Beam (continuous): fires every use (sps), base 171-257 at L20, added-dmg effectiveness 40%.
  • Icy Blade (reset burst): once per cycle (sps / rounds_per_cycle), base 513-770, effectiveness 119%,
    2 blades on one target (1st full + 2nd ×(1-0.65)=35% shotgun → ×1.35).

Base damage is per-level and UNSCALED by effectiveness (no double-dip); effectiveness scales added flat only.
"""
import pytest

from tests.mock_build import make_request, DUAL_WEAPONS
from server import engine_stats, EngineStatsRequest
from engine import uptime
from persistence import season_manager

_SKILL = "icebound_beam"
_APS = 1.0 / 0.333          # cast_speed "0.333 s" → ~3.003 casts/sec (uncapped well under 30 Hz)

_SS12_ONLY = pytest.mark.skipif(
    season_manager.get_active_season() != "SS12",
    reason="SS12-specific ground truth: Icebound Beam's base damage was rebalanced in SS13 "
           "(Cold Beam 171-257 -> 206-309, Icy Blade 513-770 -> 618-928 at L20). Pending SS13 "
           "re-verification post-flip, not a deletion.",
)


def _gear_with(**stats):
    """DUAL_WEAPONS plus one ring item carrying the given engine stats (gear contribution format)."""
    return DUAL_WEAPONS + [{"item_name": "ChItem", "contributions": [
        {"stat": k, "display_value": v, "unit": "", "slot": "ring", "item_name": "ChItem",
         "text": f"+{v} {k}"} for k, v in stats.items()]}]


def _offense(level=20, gear=None, conds=None, **extra):
    req = make_request(_SKILL, level, gear=gear, extra_conditions=conds, **extra)
    r = engine_stats(EngineStatsRequest(**req))
    d = r.model_dump() if hasattr(r, "model_dump") else r
    return d["offense"]


def _form(o, name):
    return next(f for f in o["hit_forms"] if f["name"] == name)


# ── uptime helpers (Min-aware cadence + reset-cycle average) ─────────────────────
class TestChanneledHelpers:
    @pytest.mark.parametrize("mx,mn,rounds", [
        (5, 0, 5), (5, 1, 4), (5, 2, 3), (5, 3, 2), (5, 4, 1), (5, 5, 1),  # min≥max-1 saturates at 1
        (5, 9, 1), (2, 0, 2), (1, 0, 1),
    ])
    def test_rounds_per_cycle(self, mx, mn, rounds):
        assert uptime.channeled_rounds_per_cycle(mx, mn) == rounds

    def test_min_3_to_4_halves_cycle_min_4_to_5_no_change(self):
        # The validated in-game behaviour: 3→4 halves rounds (doubles detonation), 4→5 does nothing.
        assert uptime.channeled_rounds_per_cycle(5, 3) == 2
        assert uptime.channeled_rounds_per_cycle(5, 4) == 1
        assert uptime.channeled_rounds_per_cycle(5, 5) == 1

    @pytest.mark.parametrize("mx,mn,avg", [
        (5, 0, 3.0), (5, 1, 3.5), (5, 4, 5.0), (5, 5, 5.0),
    ])
    def test_cycle_average_stacks(self, mx, mn, avg):
        assert uptime.channeled_cycle_average_stacks(mx, mn) == pytest.approx(avg)


# ── Icebound Beam: forms, cadence, DPS composition ───────────────────────────────
class TestIceboundBeam:
    def test_two_forms_and_reset_metadata(self):
        o = _offense()
        assert o["supported"] is True
        names = [f["name"] for f in o["hit_forms"]]
        assert names == ["Cold Beam", "Icy Blade"]
        assert o["channeled_max_stacks"] == 5
        assert o["channeled_min_stacks"] == 0
        assert o["channeled_behavior"] == "reset"
        assert o["channeled_rounds_per_cycle"] == 5
        assert o["channeled_burst_rate"] == pytest.approx(o["skills_per_second"] / 5.0)

    @_SS12_ONLY
    def test_base_damage_unscaled_by_effectiveness(self):
        # At 0 projectiles the beam is unsuppressed → each form's pre-crit average is exactly the level-20 base
        # midpoint (no eff on base, no inc/add since the build has no Cold/Intelligence mods). The Icy Blade's
        # per-hit is still computed even though it fires 0 times.
        o = _offense(gear=_gear_with(projectile_quantity_flat=-2))
        assert _form(o, "Cold Beam")["avg_hit_pre_crit"] == pytest.approx((171 + 257) / 2.0)
        assert _form(o, "Icy Blade")["avg_hit_pre_crit"] == pytest.approx((513 + 770) / 2.0)

    @_SS12_ONLY
    def test_added_flat_uses_per_form_effectiveness(self):
        # +100 cold spell flat (min=max): Cold Beam gains 100×0.40=40, Icy Blade gains 100×1.19=119. The base
        # is unchanged → the delta isolates the per-form added-damage effectiveness (and proves no base dip).
        # Run at 0 projectiles so the beam is unsuppressed (the delta would otherwise be ×1/3 on the beam).
        base = _offense(gear=_gear_with(projectile_quantity_flat=-2))
        flat = _offense(gear=_gear_with(projectile_quantity_flat=-2, cold_spell_dmg_flat_min=100, cold_spell_dmg_flat_max=100))
        d_beam = _form(flat, "Cold Beam")["avg_hit_pre_crit"] - _form(base, "Cold Beam")["avg_hit_pre_crit"]
        d_blade = _form(flat, "Icy Blade")["avg_hit_pre_crit"] - _form(base, "Icy Blade")["avg_hit_pre_crit"]
        assert d_beam == pytest.approx(40.0)
        assert d_blade == pytest.approx(119.0)

    def test_beam_suppressed_to_third_when_blades_fire(self):
        # The validated mechanic: when ANY Icy Blade fires (projectiles ≥ 1), the Cold Beam drops to 1/3 of its
        # full (0-projectile) damage — the channel redistributes beam → blades. Matches the in-game recounts
        # (beam 113 solo → ~38 once blades fire; 0/1/2/4/6-projectile totals fit beam×1/3 + additive blades).
        solo = _offense(gear=_gear_with(projectile_quantity_flat=-2))   # 0 projectiles → beam full, no blade
        base = _offense()                                               # 2 projectiles → beam suppressed
        beam_full = _form(solo, "Cold Beam")["dps_contribution"]
        beam_supp = _form(base, "Cold Beam")["dps_contribution"]
        assert beam_supp == pytest.approx(beam_full / 3.0)
        assert solo["total_dps"] == pytest.approx(beam_full)   # 0 projectiles isolates the beam

    def test_continuous_fires_every_use_burst_once_per_cycle(self):
        o = _offense()
        sps = o["skills_per_second"]
        beam, blade = _form(o, "Cold Beam"), _form(o, "Icy Blade")
        assert beam["fires_per_sec"] == pytest.approx(sps)
        assert blade["fires_per_sec"] == pytest.approx(sps / 5.0)
        assert blade["hits_per_fire"] == 2

    def test_per_form_dps_and_total(self):
        o = _offense()
        beam, blade = _form(o, "Cold Beam"), _form(o, "Icy Blade")
        # Cold Beam: avg × sps (single hit). Icy Blade: avg × (sps/5) × 1.35 (2-blade shotgun, 1+0.35).
        assert beam["dps_contribution"] == pytest.approx(beam["avg_hit_with_crit"] * beam["fires_per_sec"])
        assert blade["dps_contribution"] == pytest.approx(
            blade["avg_hit_with_crit"] * blade["fires_per_sec"] * 1.35)
        assert o["total_dps"] == pytest.approx(beam["dps_contribution"] + blade["dps_contribution"])

    def test_min_stack_raises_burst_cadence(self):
        base = _offense()
        m1 = _offense(gear=_gear_with(min_channeled_stacks_flat=1))
        assert m1["channeled_rounds_per_cycle"] == 4
        assert m1["channeled_burst_rate"] == pytest.approx(base["skills_per_second"] / 4.0)
        # Beam (continuous) is unchanged; Blade (burst) and total rise with the faster cadence.
        assert _form(m1, "Cold Beam")["dps_contribution"] == pytest.approx(
            _form(base, "Cold Beam")["dps_contribution"])
        assert _form(m1, "Icy Blade")["dps_contribution"] > _form(base, "Icy Blade")["dps_contribution"]
        assert m1["total_dps"] > base["total_dps"]

    def test_min_3_to_4_doubles_blade_min_4_to_5_no_change(self):
        m3 = _offense(gear=_gear_with(min_channeled_stacks_flat=3))
        m4 = _offense(gear=_gear_with(min_channeled_stacks_flat=4))
        m5 = _offense(gear=_gear_with(min_channeled_stacks_flat=5))
        b3 = _form(m3, "Icy Blade")["dps_contribution"]
        b4 = _form(m4, "Icy Blade")["dps_contribution"]
        b5 = _form(m5, "Icy Blade")["dps_contribution"]
        assert b4 == pytest.approx(2.0 * b3)   # rounds 2→1 → detonation rate doubles
        assert b5 == pytest.approx(b4)         # min clamps to max → no further change

    def test_projectile_quantity_scales_icy_blade_shotgun(self):
        # +Projectile Quantity adds blades to the Icy Blade; all home onto one target and shotgun linearly
        # (1st full + each subsequent ×0.35). Base 2 → ×1.35; +2 quantity → 4 blades → ×(1+3×0.35)=2.05.
        base = _offense()
        blade0 = _form(base, "Icy Blade")
        assert blade0["hits_per_fire"] == 2
        assert blade0["shotgun_mult"] == pytest.approx(1.35)
        assert base["projectile_count"] == 2

        q2 = _offense(gear=_gear_with(projectile_quantity_flat=2))
        blade2 = _form(q2, "Icy Blade")
        assert blade2["hits_per_fire"] == 4
        assert q2["projectile_count"] == 4
        assert blade2["shotgun_mult"] == pytest.approx(1.0 + 3 * 0.35)
        # Blade DPS scales by the shotgun ratio; the Cold Beam (not a projectile) is unchanged.
        assert blade2["dps_contribution"] == pytest.approx(
            blade0["dps_contribution"] * (1.0 + 3 * 0.35) / 1.35)
        assert _form(q2, "Cold Beam")["dps_contribution"] == pytest.approx(
            _form(base, "Cold Beam")["dps_contribution"])

    def test_zero_projectiles_isolates_the_beam(self):
        # Reducing Projectile Quantity below the base (−2) drops the Icy Blade to 0 projectiles → it does NOT
        # fire, so total = Cold Beam only (and the beam is UNsuppressed = 3× the suppressed base-skill beam).
        base = _offense()
        z = _offense(gear=_gear_with(projectile_quantity_flat=-2))
        assert z["projectile_count"] == 0
        blade = _form(z, "Icy Blade")
        assert blade["hits_per_fire"] == 0
        assert blade["dps_contribution"] == pytest.approx(0.0)
        # Beam is full here (no blade firing) → 3× the suppressed beam when the base skill's blades fire.
        assert _form(z, "Cold Beam")["dps_contribution"] == pytest.approx(
            _form(base, "Cold Beam")["dps_contribution"] * 3.0)
        assert z["total_dps"] == pytest.approx(_form(z, "Cold Beam")["dps_contribution"])

    def test_channeled_spell_does_not_spell_burst(self):
        # A channeled spell ramps stacks; it must never enter Spell Burst even with Max Spell Burst on gear.
        o = _offense(gear=_gear_with(max_spell_burst_flat=5))
        assert o["spell_burst_count"] == 0
        assert o["channeled_max_stacks"] == 5


# ── non-regression: a normal spell is unaffected by the channeled additions ───────
class TestNonChanneledUnaffected:
    def test_chain_lightning_not_channeled(self):
        req = make_request("chain_lightning", 20)
        r = engine_stats(EngineStatsRequest(**req))
        d = r.model_dump() if hasattr(r, "model_dump") else r
        o = d["offense"]
        assert o["channeled_max_stacks"] == 0
        assert o["channeled_behavior"] == ""
        assert o["projectile_count"] == -1   # no projectile-scaling form → N/A
        # single form fires at sps with no shotgun (hits_per_fire defaults to 1)
        f = o["hit_forms"][0]
        assert f["hits_per_fire"] == 1
        assert f["dps_contribution"] == pytest.approx(f["avg_hit_with_crit"] * o["skills_per_second"])


def test_ring_blade_ss13_negative_roll_parses():
    """SS13 retuned Ring Blade's specific roll to a NEGATIVE range — "(-5–-4) % additional damage for the
    supported skill". The old positive-only _RING_RE silently dropped it (the contribution vanished while the
    line still badged modeled — caught by review-accuracy 2026-08-10, and the first icebound SS13 golden
    recapture baked the miss in). Pin: the tier line parses to the signed midpoint −4.5%."""
    from engine.skill_effects.icebound_beam import ring_blade_contribution, RING_BLADE
    from persistence import season_manager
    d = season_manager.load_skills("SS13")
    data = next(s for s in d["skills"] if s.get("item_id") == RING_BLADE)
    contrib = ring_blade_contribution({"item_id": RING_BLADE, "slot": 1, "level": 1}, data)
    assert contrib is not None, "SS13 Ring Blade roll must parse (negative range)"
    assert contrib["stat_key"] == "dmg_additional"
    assert contrib["amount"] == pytest.approx(-0.045)
    assert "ring_blade" in contrib["text"]
