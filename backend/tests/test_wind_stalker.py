"""Erika — Wind Stalker (trait_id "wind_stalker"). Base + advanced picks layered on the Phase-1 Multistrike system.

Unit-tests the module's contributions directly (exact amounts) and integration-tests Have Fun's free Lv10 Multistrike
support + gating through the full engine. Tyra-confirmed model (2026-06-22): "max count" = the chain's final attack;
Cat's Vision damage is a flat bonus; Stalker stacks default to the effective max (3 base / 6 w/ Cat's Vision).
"""
import pytest
from engine.hero_traits import wind_stalker as ws
from server import engine_stats, EngineStatsRequest
from tests.mock_build import make_request, weapon

WEAPON = [weapon("weapon1", "Blade", 350, 350, 1.5, 500)]


# ── Module unit tests (contribution amounts) ────────────────────────────────────────
def _apply(levels, picks=None, ls=None, conds=None):
    return ws.apply(build_input=None, condition_state=conds or {}, ls_state=ls or {},
                    uptime_mode="max", slot_levels=levels, advanced_picks=picks or [])["contributions"]


def _amt(contribs, stat):
    return sum(c["amount"] for c in contribs if c["stat_key"] == stat)


def test_base_movement_attack_dmg_and_stalker():
    c = _apply([5, 1, 1, 1])                                   # base L5, no picks, defaults
    assert _amt(c, "movement_speed_inc") == pytest.approx(0.26)
    assert _amt(c, "attack_dmg_additional") == pytest.approx(0.20)        # +20% at L5
    assert _amt(c, "dmg_additional") == pytest.approx(0.39)               # Stalker 0.13 × max 3 stacks


def test_base_level_scales_attack_dmg():
    assert _amt(_apply([1, 1, 1, 1]), "attack_dmg_additional") == pytest.approx(0.0)   # L1 = 0
    assert _amt(_apply([3, 1, 1, 1]), "attack_dmg_additional") == pytest.approx(0.10)  # L3 = +10%


def test_stalker_gated_on_performing_and_user_stacks():
    assert _amt(_apply([5, 1, 1, 1], conds={"performing_multistrike": False}), "dmg_additional") == 0.0
    assert _amt(_apply([5, 1, 1, 1], conds={"stalker_stacks": 2}), "dmg_additional") == pytest.approx(0.26)


def test_disabled_base_node_emits_nothing():
    assert _apply([-5, 1, 1, 1]) == []                         # negative level = disabled


def test_interest_converts_movement_speed_capped():
    # base L1 (0 attack dmg) isolates Interest. rate .20 × MS; capped at .30.
    assert _amt(_apply([1, 1, 1, 1], picks=["Interest"], ls={"movement_speed_inc": 1.0}),
                "attack_dmg_additional") == pytest.approx(0.20)
    assert _amt(_apply([1, 1, 1, 1], picks=["Interest"], ls={"movement_speed_inc": 2.0}),
                "attack_dmg_additional") == pytest.approx(0.30)           # hits cap


def test_have_fun_general_attack_speed():
    assert _amt(_apply([1, 2, 1, 1], picks=["Have Fun"]), "attack_speed_additional") == pytest.approx(0.06)  # lv45 tier2


def test_cats_vision_flat_dmg_and_raises_stalker_cap():
    # Cat's Vision raises Stalker cap to 6 → default stacks 6 → 0.78; plus its flat signed dmg (tier0 = −0.04).
    c = _apply([5, 1, 1, 1], picks=["Cat's Vision"])
    assert _amt(c, "dmg_additional") == pytest.approx(0.78 - 0.04)
    # positive tier (lv60 node level 3 → +0.08), stacks dialed to 0 to isolate the flat bonus
    c2 = _apply([5, 1, 3, 1], picks=["Cat's Vision"], conds={"stalker_stacks": 0})
    assert _amt(c2, "dmg_additional") == pytest.approx(0.08)


def test_cats_scratch_additional_increment():
    assert _amt(_apply([5, 1, 1, 1], picks=["Cat's Scratch"]),
                "multistrike_increasing_dmg_additional") == pytest.approx(0.27)


def test_cat_dive_proc_scales_with_movement_speed():
    # tier0 rate 0.0024 per 1% MS; MS 100% → q = 0.24.
    assert _amt(_apply([5, 1, 1, 1], picks=["Cat Dive"], ls={"movement_speed_inc": 1.0}),
                "multistrike_max_count_proc_chance") == pytest.approx(0.24)
    assert _amt(_apply([5, 1, 1, 1], picks=[], ls={"movement_speed_inc": 1.0}),
                "multistrike_max_count_proc_chance") == 0.0              # not picked → nothing


def test_cats_punches_initial_count_and_flat_dmg():
    # Default stalker stacks = cap 3 → floor(3/3) = +1 Initial Multistrike Count. Per-rank dmg: lv75 tier0 = -0.18.
    c = _apply([5, 1, 1, 1], picks=["Cat's Punches"])
    assert _amt(c, "initial_multistrike_count_flat") == pytest.approx(1.0)
    # additional damage line is ALWAYS active (not multistrike-gated) — Cat's Punches contributes -0.18 on top of Stalker.
    assert _amt(c, "dmg_additional") == pytest.approx(0.39 - 0.18)


def test_cats_punches_initial_count_steps_by_three():
    # +1 per 3 stacks (hard steps). Stalker is clamped to its cap (3 base, 6 with Cat's Vision), so:
    #   3 stacks → +1; 6 stacks (Cat's Vision raises the cap) → +2; below 3 → +0.
    assert _amt(_apply([5, 1, 1, 1], picks=["Cat's Punches"]),
                "initial_multistrike_count_flat") == pytest.approx(1.0)   # default cap 3
    assert _amt(_apply([5, 1, 1, 1], picks=["Cat's Vision", "Cat's Punches"]),
                "initial_multistrike_count_flat") == pytest.approx(2.0)   # cap 6 → 6 stacks
    assert _amt(_apply([5, 1, 1, 1], picks=["Cat's Punches"], conds={"stalker_stacks": 2}),
                "initial_multistrike_count_flat") == 0.0                  # 2 stacks → floor(2/3) = 0


def test_cats_punches_dmg_always_active_not_multistrike_gated():
    # Even with performing_multistrike off (Stalker contributes 0), Cat's Punches' additional damage still applies.
    c = _apply([5, 1, 1, 1], picks=["Cat's Punches"], conds={"performing_multistrike": False})
    assert _amt(c, "dmg_additional") == pytest.approx(-0.18)
    # rank 5 (lv75 level 5) = +0.06
    c5 = _apply([5, 1, 1, 5], picks=["Cat's Punches"], conds={"performing_multistrike": False})
    assert _amt(c5, "dmg_additional") == pytest.approx(0.06)


def test_virtual_support_only_with_have_fun():
    assert ws.virtual_supports(slot_levels=[1, 1, 1, 1], advanced_picks=[], main_slot=1) == []
    v = ws.virtual_supports(slot_levels=[1, 1, 1, 1], advanced_picks=["Have Fun"], main_slot=2)
    assert v == [{"item_id": "multistrike", "slot": 2, "level": 10, "rank": 1, "enabled": True}]


def test_status_lines_surface_every_line():
    s = ws.status_lines(slot_levels=[5, 1, 1, 1], advanced_picks=["Have Fun", "Cat Dive"])
    texts = " ".join(x["text"] for x in s)
    assert "Movement Speed" in texts and "Have Fun" in texts and "Cat Dive" in texts
    assert any(x["status"] == "nyi" and "Artificial Moon" in x["text"] for x in s)   # Mark debuff NYI at base L5


# ── Engine integration (Have Fun virtual support + gating) ──────────────────────────
def _off(picks=None, levels=None, conds=None):
    req = make_request("berserking_blade", 16, gear=WEAPON, trait_id="wind_stalker",
                       trait_slot_levels=levels or [5, 1, 1, 1], advanced_trait_selections=picks or [],
                       condition_state=conds or {})
    r = engine_stats(EngineStatsRequest(**req))
    return (r if isinstance(r, dict) else r.model_dump())["offense"]


def test_have_fun_injects_main_slot_multistrike():
    base = _off(picks=[])
    hf = _off(picks=["Have Fun"])
    assert base["multistrike_chance"] == 0.0                   # no real support, no Have Fun → no multistrike
    assert hf["multistrike_chance"] > 1.0                      # free Lv10 Multistrike on the main skill
    assert hf["multistrike_mult"] > 1.0
    assert hf["total_dps_vs_target"] > base["total_dps_vs_target"]


def test_cats_scratch_raises_increment_through_engine():
    hf = _off(picks=["Have Fun"])
    scratch = _off(picks=["Have Fun", "Cat's Scratch"])
    assert scratch["multistrike_increment"] == pytest.approx(hf["multistrike_increment"] * 1.27, rel=0.01)
    assert scratch["multistrike_mult"] > hf["multistrike_mult"]


def test_cats_punches_raises_dps_through_engine():
    # rank 5 (lv75 level 5): +6% additional damage + Initial Multistrike Count (pre-stacks the increment) → more DPS.
    hf = _off(picks=["Have Fun"])
    punches = _off(picks=["Have Fun", "Cat's Punches"], levels=[5, 1, 1, 5])
    assert punches["total_dps_vs_target"] > hf["total_dps_vs_target"]
