"""Howling Gale (howling_gale) — channeled REFRESH spell with a persistent Gale.

The Gale strikes at its own Base Attack Frequency 1.5/s (× cast speed), separate from the 3/s channel build rate
(both surfaced). Spell base (548-913 physical @ L20) is unscaled by effectiveness. "+21.5% additional damage per
ADDITIONAL Max Channeled Stack" (beyond base 5) scales off max_channeled_stacks_flat (Tyra read — verify in-game).
"""
import pytest
from server import engine_stats, EngineStatsRequest
from tests.mock_build import make_request, DUAL_WEAPONS

_SKILL = "howling_gale"


def _gear_with(**stats):
    return DUAL_WEAPONS + [{"item_name": "HGItem", "contributions": [
        {"stat": k, "display_value": v, "unit": "", "slot": "ring", "item_name": "HGItem", "text": f"+{v} {k}"}
        for k, v in stats.items()]}]


def _offense(level=20, gear=None, conds=None, **extra):
    r = engine_stats(EngineStatsRequest(**make_request(_SKILL, level, gear=gear, extra_conditions=conds, **extra)))
    d = r.model_dump() if hasattr(r, "model_dump") else r
    return d["offense"]


def test_supported_refresh_channeled():
    o = _offense()
    assert o["supported"] is True
    assert o["channeled_behavior"] == "refresh"
    assert o["channeled_max_stacks"] == 5


def test_gale_rate_separate_from_channel_rate():
    o = _offense()
    sps = o["skills_per_second"]                 # channel build rate (1/0.333 ≈ 3/s)
    assert sps == pytest.approx(1.0 / 0.333, rel=1e-3)
    # Gale strikes at 1.5 × cast-speed mult; at no cast speed = 1.5/s. cs_mult = sps × base_cast_time ≈ 1.0.
    assert o["channeled_attack_frequency"] == pytest.approx(1.5, rel=1e-3)
    # The damage form fires at the Gale rate, NOT the channel rate.
    form = o["hit_forms"][0]
    assert form["fires_per_sec"] == pytest.approx(1.5, rel=1e-3)
    assert form["dps_contribution"] == pytest.approx(form["avg_hit_with_crit"] * 1.5, rel=1e-3)


def test_base_damage_unscaled_by_effectiveness():
    # No added flat → the form's pre-crit average is the L20 base midpoint (548-913), unscaled by the 125% eff.
    o = _offense()
    assert o["hit_forms"][0]["avg_hit_pre_crit"] == pytest.approx((548 + 913) / 2.0)


def test_per_additional_max_stack_additional_damage():
    base = _offense()                                              # base Max 5 → +0% from this line
    plus2 = _offense(gear=_gear_with(max_channeled_stacks_flat=2))  # Max 7 → +2×21.5% = +43% additional
    b = base["hit_forms"][0]["avg_hit_with_crit"]
    p = plus2["hit_forms"][0]["avg_hit_with_crit"]
    assert p == pytest.approx(b * 1.43, rel=1e-3)
    # higher max stacks also widens the channeled panel value
    assert plus2["channeled_max_stacks"] == 7


def test_cast_speed_scales_gale_rate():
    base = _offense()
    fast = _offense(gear=_gear_with(cast_speed_inc=0.50))   # +50% cast speed → ×1.5 on BOTH channel + Gale rate
    assert fast["channeled_attack_frequency"] == pytest.approx(base["channeled_attack_frequency"] * 1.5, rel=1e-3)
    assert fast["skills_per_second"] == pytest.approx(base["skills_per_second"] * 1.5, rel=1e-3)


# ── Phase 2: noble / magnificent canvas supports ──────────────────────────────
EYE      = "howling_gale_eye_of_the_gale_noble"
FURIOUS  = "howling_gale_furious_sweep_noble"
HEADWIND = "howling_gale_headwind_magnificent"
RAPID    = "howling_gale_rapid_sweep_magnificent"


def _sup(item_id, *, tier=1, rank=1, slot=1):
    # level == the support's Tier control (default 1 = headline roll); rank drives the universal +20% line.
    return {"item_id": item_id, "slot": slot, "level": tier, "rank": rank, "enabled": True}


def test_eye_global_cast_speed_scales_rates():
    base = _offense()
    # Eye tier 1 = +(20-22)% additional Attack & Cast Speed (mid 21%). Cast Speed feeds BOTH the channel build
    # rate and the Gale strike rate (an additional pool → ×1.21).
    eye = _offense(attached_supports=[_sup(EYE)])
    assert eye["skills_per_second"] == pytest.approx(base["skills_per_second"] * 1.21, rel=1e-3)
    assert eye["channeled_attack_frequency"] == pytest.approx(base["channeled_attack_frequency"] * 1.21, rel=1e-3)


def test_eye_gated_on_within_gale():
    base = _offense()
    off = _offense(attached_supports=[_sup(EYE)], conds={"within_gale": False})
    assert off["skills_per_second"] == pytest.approx(base["skills_per_second"], rel=1e-3)


def test_furious_sweep_scales_gale_rate_only():
    base = _offense()
    # Furious tier 1 = +(7.2-7.6)% (mid 7.4%) additional Gale Attack Frequency PER channeled stack × 5 = +37%.
    fs = _offense(attached_supports=[_sup(FURIOUS)])
    assert fs["channeled_attack_frequency"] == pytest.approx(base["channeled_attack_frequency"] * 1.37, rel=1e-3)
    # The channel BUILD rate (sps) is untouched — Furious scales only the Gale.
    assert fs["skills_per_second"] == pytest.approx(base["skills_per_second"], rel=1e-3)


def test_headwind_enemy_vulnerability():
    base = _offense()
    # Headwind socketed → preseed forces enemy_knocked_back ON → +(22-24)% (mid 23%) additional damage taken
    # (enemy-vuln, applies to vs-target DPS only, not the pre-mitigation avg_hit).
    hw = _offense(attached_supports=[_sup(HEADWIND, slot=1)])
    assert hw["total_dps_vs_target"] == pytest.approx(base["total_dps_vs_target"] * 1.23, rel=1e-3)
    # Rate / pre-mitigation hit are unchanged by an enemy debuff.
    assert hw["channeled_attack_frequency"] == pytest.approx(base["channeled_attack_frequency"], rel=1e-3)


def test_rapid_sweep_ramp_capped():
    base = _offense()
    # Rapid tier 1 = +(3.4-3.7)% (mid 3.55%) additional damage per 1 s the Gale lasts, cap 10 → +35.5% at cap
    # (rapid_sweep_stacks defaults to 10). Additional hit-damage pool → scales avg_hit.
    rs = _offense(attached_supports=[_sup(RAPID)])
    b = base["hit_forms"][0]["avg_hit_with_crit"]
    r = rs["hit_forms"][0]["avg_hit_with_crit"]
    assert r == pytest.approx(b * 1.355, rel=1e-3)


def test_rapid_sweep_stack_count_scales():
    base = _offense()
    half = _offense(attached_supports=[_sup(RAPID)], conds={"rapid_sweep_stacks": 5})  # 5 stacks → +17.75%
    b = base["hit_forms"][0]["avg_hit_with_crit"]
    h = half["hit_forms"][0]["avg_hit_with_crit"]
    assert h == pytest.approx(b * 1.1775, rel=1e-3)


# ── Coverage badges + roll metadata for the bespoke lines (engine.skill_effects registry) ─────
def test_resolve_line_keys_for_bespoke_lines():
    from engine import skill_effects as se
    # Stat clauses → their engine keys (so the badge shows Consumed, not NYI).
    assert se.resolve_line_keys("+3.55 % additional damage for every 1s the Gale lasts") == ["dmg_additional"]
    assert "channeled_attack_frequency_additional" in se.resolve_line_keys("+8 % additional Attack Frequency for each channeled stack")
    assert se.resolve_line_keys("enemies recently knocked back take +23 % additional damage taken") == ["knockback_dmg_taken"]
    assert se.resolve_line_keys("+21 % additional Attack and Cast Speed") == ["attack_speed_additional", "cast_speed_additional"]
    # Flavor clause → None (not a bespoke modifier line).
    assert se.resolve_line_keys("Stacks up to 10 time(s)") is None


def test_modeled_rolls_picks_correct_range():
    from server import _get_skills_data, season_manager
    from engine import skill_effects as se
    data = _get_skills_data(season_manager.get_active_season())
    # Headwind: the roll must be the (22-24)% damage-taken range, NOT the fixed 50% Knockback Chance.
    rolls = se.modeled_rolls("howling_gale_headwind_magnificent", data["howling_gale_headwind_magnificent"])
    assert len(rolls) == 1 and rolls[0]["stat_keys"] == ["knockback_dmg_taken"]
    t1 = rolls[0]["ranges_by_tier"][1]
    assert (round(t1["min"], 3), round(t1["max"], 3)) == (0.22, 0.24)


def test_tooltip_badges_consumed_and_suppresses_flavor():
    from engine.tooltip import build_tooltip
    from server import _get_skills_data, season_manager
    from engine.skill_effects import resolve_line_keys
    data = _get_skills_data(season_manager.get_active_season())
    spec = build_tooltip(data["howling_gale_rapid_sweep_magnificent"])
    badged = [ln["badge_text"] for ln in spec["lines"] if ln["badge_text"]]
    # The damage roll line keeps its (resolvable) badge; the 3 flavor clauses are suppressed (no badge).
    assert any("additional damage for every 1" in b for b in badged)
    assert not any("Stacks up to" in b for b in badged)
    assert spec["modeled_rolls"] and spec["modeled_rolls"][0]["stat_keys"] == ["dmg_additional"]


def test_universal_rank_line_applies():
    base = _offense()
    # A rank-5 support adds the universal +20% additional damage for the supported skill (rank table). Use Eye
    # (its specific effect is rate/projectile-speed, which doesn't touch hit damage) to isolate the +20% on avg_hit.
    ranked = _offense(attached_supports=[_sup(EYE, rank=5)])
    b = base["hit_forms"][0]["avg_hit_with_crit"]
    r = ranked["hit_forms"][0]["avg_hit_with_crit"]
    assert r == pytest.approx(b * 1.20, rel=1e-3)
