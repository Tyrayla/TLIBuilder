"""Rehan — Seething Silhouette (trait_id "seething_silhouette"). Base trait + Artificial Moon +
all 6 advanced picks, EXCLUDING Seething Spirit's own damage / the player-Disarm zero-out (deferred
to a separate post-offense engine pass — see the module docstring). Unit-tests the module directly,
matching wind_stalker's convention (exact contribution amounts, not a full engine_stats integration run).
"""
import pytest
from engine.hero_traits import seething_silhouette as ss


def _apply(levels, picks=None, conds=None):
    return ss.apply(build_input=None, condition_state=conds or {}, ls_state={},
                     uptime_mode="max", slot_levels=levels, advanced_picks=picks or [])["contributions"]


def _amt(contribs, stat):
    return sum(c["amount"] for c in contribs if c["stat_key"] == stat)


# ── Base trait ───────────────────────────────────────────────────────────────
def test_base_attack_speed_always_active_default_conditions():
    # Default rage_amount=100, berserk_active=True → effective_rage = 200 → +1%/5 × 200/5 = +40%
    c = _apply([1, 1, 1, 1])
    assert _amt(c, "attack_speed_inc") == pytest.approx(0.40)


def test_base_attack_speed_not_doubled_outside_berserk():
    c = _apply([1, 1, 1, 1], conds={"berserk_active": False})
    assert _amt(c, "attack_speed_inc") == pytest.approx(0.20)   # effective_rage = 100 → +20%


def test_base_berserk_gated_lines():
    c = _apply([5, 1, 1, 1])   # base L5, berserk default True
    assert _amt(c, "movement_speed_inc") == pytest.approx(0.20)
    assert _amt(c, "skill_area_inc") == pytest.approx(0.45)
    assert _amt(c, "dmg_additional") == pytest.approx(0.44)   # L5 tier


def test_base_level_scales_berserk_dmg():
    assert _amt(_apply([1, 1, 1, 1]), "dmg_additional") == pytest.approx(0.20)
    assert _amt(_apply([3, 1, 1, 1]), "dmg_additional") == pytest.approx(0.32)


def test_berserk_off_drops_berserk_gated_lines_but_keeps_attack_speed():
    c = _apply([5, 1, 1, 1], conds={"berserk_active": False})
    assert _amt(c, "movement_speed_inc") == 0.0
    assert _amt(c, "skill_area_inc") == 0.0
    assert _amt(c, "dmg_additional") == 0.0
    assert _amt(c, "attack_speed_inc") > 0.0


def test_disabled_base_node_emits_nothing():
    assert _apply([-5, 1, 1, 1]) == []


# ── Artificial Moon (base L5) ───────────────────────────────────────────────
def test_artificial_moon_gated_on_level_5():
    assert _amt(_apply([4, 1, 1, 1]), "double_dmg_chance") == 0.0
    c = _apply([5, 1, 1, 1])   # effective_rage 200 → +1%/5 × 200/5 = +40%
    assert _amt(c, "double_dmg_chance") == pytest.approx(0.40)


def test_artificial_moon_scales_with_rage_amount():
    c = _apply([5, 1, 1, 1], conds={"rage_amount": 50})   # effective_rage 100 → +20%
    assert _amt(c, "double_dmg_chance") == pytest.approx(0.20)


# ── Ritual of Offering (45) ─────────────────────────────────────────────────
def test_ritual_of_offering_movement_speed_gated_on_berserk():
    c = _apply([1, 1, 1, 1], picks=["Ritual of Offering"])
    assert _amt(c, "movement_speed_inc") == pytest.approx(0.20 - 0.30)   # base +20% (berserk) + RO -30%
    off = _apply([1, 1, 1, 1], picks=["Ritual of Offering"], conds={"berserk_active": False})
    assert _amt(off, "movement_speed_inc") == 0.0


# ── Fury's Onslaught (45) ────────────────────────────────────────────────────
def test_furys_onslaught_player_damage_tiered():
    c1 = _apply([1, 1, 1, 1], picks=["Fury's Onslaught"])
    assert _amt(c1, "dmg_additional") == pytest.approx(0.20 + 0.50)   # base L1 dmg + FO tier1
    c5 = _apply([1, 5, 1, 1], picks=["Fury's Onslaught"])
    assert _amt(c5, "dmg_additional") == pytest.approx(0.20 + 0.78)   # lv45 tier5


def test_furys_onslaught_gated_on_berserk():
    off = _apply([1, 1, 1, 1], picks=["Fury's Onslaught"], conds={"berserk_active": False})
    assert _amt(off, "dmg_additional") == 0.0


# ── Hysteria (60) ────────────────────────────────────────────────────────────
def test_hysteria_scales_with_missing_life_not_berserk_gated():
    c = _apply([1, 1, 1, 1], picks=["Hysteria"], conds={"life_lost_pct": 50, "berserk_active": False})
    assert _amt(c, "attack_dmg_additional") == pytest.approx(0.003 * 50)


def test_hysteria_tier_scales():
    c = _apply([1, 1, 5, 1], picks=["Hysteria"], conds={"life_lost_pct": 100})
    assert _amt(c, "attack_dmg_additional") == pytest.approx(0.007 * 100)


# ── Growing Anger (60) — informational only, no contribution ────────────────
def test_growing_anger_emits_no_contribution():
    # Disable the base node to isolate Growing Anger's own (lack of) contribution.
    c = _apply([-1, 1, 1, 1], picks=["Growing Anger"])
    assert c == []


# ── Split Form (75) ──────────────────────────────────────────────────────────
def test_split_form_signed_max_life():
    lo = _apply([1, 1, 1, 1], picks=["Split Form"])
    assert _amt(lo, "max_life_additional") == pytest.approx(-0.15)
    hi = _apply([1, 1, 1, 5], picks=["Split Form"])
    assert _amt(hi, "max_life_additional") == pytest.approx(0.05)
    mid = _apply([1, 1, 1, 4], picks=["Split Form"])
    assert _amt(mid, "max_life_additional") == 0.0   # tier4 is exactly 0 → no contribution emitted


# ── Rage Infusion (75) ───────────────────────────────────────────────────────
def test_rage_infusion_defaults_to_tier_cap():
    # Base node disabled to isolate Rage Infusion's own dmg_additional contribution.
    c1 = _apply([-1, 1, 1, 1], picks=["Rage Infusion"])
    assert _amt(c1, "dmg_additional") == pytest.approx(0.05 * 4)   # tier1 cap = 4
    c5 = _apply([-1, 1, 1, 5], picks=["Rage Infusion"])
    assert _amt(c5, "dmg_additional") == pytest.approx(0.05 * 8)   # tier5 cap = 8


def test_rage_infusion_user_stacks_clamped_to_cap():
    over = _apply([-1, 1, 1, 1], picks=["Rage Infusion"], conds={"rage_infusion_stacks": 99})
    assert _amt(over, "dmg_additional") == pytest.approx(0.05 * 4)   # clamped to tier1 cap
    under = _apply([-1, 1, 1, 1], picks=["Rage Infusion"], conds={"rage_infusion_stacks": 2})
    assert _amt(under, "dmg_additional") == pytest.approx(0.05 * 2)


# ── status_lines ─────────────────────────────────────────────────────────────
def test_status_lines_surface_every_pick():
    picks = ["Ritual of Offering", "Hysteria", "Growing Anger", "Rage Infusion"]
    s = ss.status_lines(slot_levels=[5, 1, 1, 1], advanced_picks=picks)
    texts = " ".join(x["text"] for x in s)
    assert "Artificial Moon" in texts
    assert "Ritual of Offering" in texts and "Hysteria" in texts
    assert "Growing Anger" in texts and "Rage Infusion" in texts


def test_status_lines_warns_seething_spirit_not_modeled():
    s = ss.status_lines(slot_levels=[1, 1, 1, 1], advanced_picks=["Ritual of Offering"])
    assert any(x["status"] == "warning" and "NOT YET MODELED" in x["text"] for x in s)
    s2 = ss.status_lines(slot_levels=[1, 1, 1, 1], advanced_picks=["Fury's Onslaught"])
    assert any(x["status"] == "warning" and "NOT YET MODELED" in x["text"] for x in s2)


def test_status_lines_warns_growing_anger_without_spirit():
    s = ss.status_lines(slot_levels=[1, 1, 1, 1], advanced_picks=["Growing Anger"])
    assert any(x["status"] == "warning" and "does nothing" in x["text"] for x in s)
    s2 = ss.status_lines(slot_levels=[1, 1, 1, 1], advanced_picks=["Growing Anger", "Fury's Onslaught"])
    assert not any(x["status"] == "warning" and "does nothing" in x["text"] for x in s2)


def test_status_lines_warns_non_melee_attack_main_skill():
    s = ss.status_lines(slot_levels=[1, 1, 1, 1], advanced_picks=[], main_skill_tags=["spell"],
                         main_skill_name="Chain Lightning")
    assert any(x["status"] == "warning" and "Chain Lightning" in x["text"] and "Rage generation" in x["text"]
               for x in s)


def test_status_lines_no_warning_for_qualifying_melee_attack_skill():
    s = ss.status_lines(slot_levels=[1, 1, 1, 1], advanced_picks=[], main_skill_tags=["attack", "melee"])
    assert not any(x["status"] == "warning" for x in s)


def test_status_lines_warns_channeled_mobility_only_with_spirit_pick():
    # Channeled melee attack skill: Rage generation is fine (no restriction), but Seething Spirit (Ritual
    # of Offering / Fury's Onslaught) specifically needs Non-Mobility, Non-Channeled — only warn when picked.
    no_pick = ss.status_lines(slot_levels=[1, 1, 1, 1], advanced_picks=[],
                               main_skill_tags=["attack", "melee", "channeled"])
    assert not any(x["status"] == "warning" for x in no_pick)
    with_pick = ss.status_lines(slot_levels=[1, 1, 1, 1], advanced_picks=["Ritual of Offering"],
                                 main_skill_tags=["attack", "melee", "channeled"])
    assert any(x["status"] == "warning" and "Seething Spirit requires" in x["text"] for x in with_pick)


def test_status_lines_no_main_skill_warning_when_tags_not_provided():
    s = ss.status_lines(slot_levels=[1, 1, 1, 1], advanced_picks=[])
    assert not any(x["status"] == "warning" for x in s)
