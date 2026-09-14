"""Rehan — Seething Silhouette (trait_id "seething_silhouette"). Base trait + Artificial Moon +
all 6 advanced picks, plus Seething Spirit's own derived-offense pass (compute.py) and the
Ritual of Offering player-Disarm zero-out. Unit-tests `apply()`/`spirit_grant()` directly
(matching wind_stalker's convention — exact contribution amounts) and integration-tests the
`spirit_offense` field end to end via `engine_stats`.
"""
import pytest
from engine.hero_traits import seething_silhouette as ss
from server import engine_stats, EngineStatsRequest
from tests.mock_build import make_request, weapon, DUAL_WEAPONS

SKILL = "chain_lightning"   # a SPELL — cast_speed, not attack_speed; isolates the dmg_additional pool math
ATTACK_SKILL = "focused_slash"   # a real melee attack skill — needed to exercise attack_speed_additional
ATTACK_WEAPON = [weapon("weapon1", "Blade", 350, 350, 1.5, 500)]


def _run(picks=None, extra_conditions=None, slot_levels=(5, 5, 1, 1), skill=SKILL, gear=None, dual_wield=True):
    req = make_request(skill, 20, trait_id="seething_silhouette", trait_slot_levels=list(slot_levels),
                        advanced_trait_selections=list(picks or []), gear=gear, dual_wield=dual_wield,
                        extra_conditions={"berserk_active": True, **(extra_conditions or {})})
    r = engine_stats(EngineStatsRequest(**req))
    return r.model_dump() if hasattr(r, "model_dump") else r


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


def test_status_lines_reports_seething_spirit_as_working():
    s = ss.status_lines(slot_levels=[1, 1, 1, 1], advanced_picks=["Ritual of Offering"])
    assert any(x["status"] == "working" and "Seething Spirit" in x["text"] and "Disarmed" in x["text"] for x in s)
    s2 = ss.status_lines(slot_levels=[1, 1, 1, 1], advanced_picks=["Fury's Onslaught"])
    assert any(x["status"] == "working" and "Seething Spirit" in x["text"] for x in s2)


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


# ── spirit_grant() unit tests ────────────────────────────────────────────────
def test_spirit_grant_none_without_pick_or_berserk():
    assert ss.spirit_grant(slot_levels=[1, 1, 1, 1], advanced_picks=[], berserk_active=True) is None
    assert ss.spirit_grant(slot_levels=[1, 1, 1, 1], advanced_picks=["Ritual of Offering"],
                            berserk_active=False) is None
    assert ss.spirit_grant(slot_levels=[1, -1, 1, 1], advanced_picks=["Ritual of Offering"],
                            berserk_active=True) is None   # lv45 node disabled


def test_spirit_grant_ritual_of_offering():
    g = ss.spirit_grant(slot_levels=[1, 1, 1, 1], advanced_picks=["Ritual of Offering"], berserk_active=True)
    assert g == {"source": "Ritual of Offering", "spirit_dmg_additional": 0.20,
                 "spirit_dmg_additional_text": "Ritual of Offering: +20% additional Seething Spirit Damage",
                 "spirit_attack_speed_additional": 0.0, "spirit_attack_speed_additional_text": "",
                 "player_only_dmg_to_exclude": 0.0, "player_disarmed": True}
    g5 = ss.spirit_grant(slot_levels=[1, 5, 1, 1], advanced_picks=["Ritual of Offering"], berserk_active=True)
    assert g5["spirit_dmg_additional"] == pytest.approx(0.40)


def test_spirit_grant_ritual_of_offering_undisarmed_by_rage_infusion():
    g = ss.spirit_grant(slot_levels=[1, 1, 1, 5], advanced_picks=["Ritual of Offering", "Rage Infusion"],
                         berserk_active=True)
    assert g["player_disarmed"] is False
    # Rage Infusion node disabled → still disarmed even though the pick name is present.
    g2 = ss.spirit_grant(slot_levels=[1, 1, 1, -5], advanced_picks=["Ritual of Offering", "Rage Infusion"],
                          berserk_active=True)
    assert g2["player_disarmed"] is True


def test_spirit_grant_furys_onslaught():
    g = ss.spirit_grant(slot_levels=[1, 1, 1, 1], advanced_picks=["Fury's Onslaught"], berserk_active=True)
    assert g == {"source": "Fury's Onslaught", "spirit_dmg_additional": 0.0,
                 "spirit_dmg_additional_text": "",
                 "spirit_attack_speed_additional": -0.30,
                 "spirit_attack_speed_additional_text":
                     "Fury's Onslaught: -30% additional Seething Spirit Attack Speed",
                 "player_only_dmg_to_exclude": 0.50, "player_disarmed": False}
    g5 = ss.spirit_grant(slot_levels=[1, 5, 1, 1], advanced_picks=["Fury's Onslaught"], berserk_active=True)
    assert g5["player_only_dmg_to_exclude"] == pytest.approx(0.78)


def test_spirit_grant_ritual_takes_precedence_if_both_named():
    # Not a real build state (pick-one-from-two), but spirit_grant should still resolve deterministically.
    g = ss.spirit_grant(slot_levels=[1, 1, 1, 1], advanced_picks=["Ritual of Offering", "Fury's Onslaught"],
                         berserk_active=True)
    assert g["source"] == "Ritual of Offering"


# ── spirit_offense integration tests (via engine_stats) ──────────────────────
def _spirit_dps(resp):
    so = resp.get("spirit_offense") or {}
    r = so.get("seething_spirit")
    return r["total_dps_vs_target"] if r else None


def test_no_spirit_pick_no_spirit_offense():
    resp = _run(picks=[])
    assert resp.get("spirit_offense") is None


def test_ritual_of_offering_disarms_player_and_populates_spirit():
    resp = _run(picks=["Ritual of Offering"])
    assert resp["offense"]["total_dps_vs_target"] == 0.0
    assert _spirit_dps(resp) > 0.0


def test_furys_onslaught_does_not_disarm_and_excludes_player_only_dmg():
    resp = _run(picks=["Fury's Onslaught"])
    player_dps = resp["offense"]["total_dps_vs_target"]
    spirit_dps = _spirit_dps(resp)
    assert player_dps > 0.0
    assert spirit_dps is not None and spirit_dps > 0.0
    assert spirit_dps < player_dps


def test_furys_onslaught_spirit_dmg_pool_excludes_exact_ratio_not_double_penalized():
    # Regression for a real bug caught in review: the additional-damage pool is a per-affix PRODUCT of
    # (1+amount) factors (offense._build_additional_factors) where negatives NEVER net against positives
    # — so naively offsetting Fury's Onslaught's own +78% (dealt BY THE PLAYER) with an untracked
    # BuildSource.add(-0.78) would compound to (1.78)x(0.22)=0.3916 instead of cleanly omitting it. The
    # fix removes the tracked SourceEntry itself. chain_lightning is a SPELL (cast_speed, not attack_speed)
    # so Fury's Onslaught's -30% additional Spirit Attack Speed contributes NO rate difference here — this
    # isolates the dmg_additional pool math exactly: player = (1.44 base)x(1.78 FO) = 2.5632, spirit =
    # 1.44 base only (FO's own +78% excluded, nothing else differs) -> ratio = 1.44/2.5632.
    resp = _run(picks=["Fury's Onslaught"])
    player_dps = resp["offense"]["total_dps_vs_target"]
    spirit_dps = _spirit_dps(resp)
    assert spirit_dps / player_dps == pytest.approx(1.44 / 2.5632, rel=1e-4)


def test_furys_onslaught_spirit_attack_speed_penalty_applies_on_a_real_attack_skill():
    # attack_speed_additional only affects rate for ATTACK skills (offense.py: spells use cast_speed
    # instead) — chain_lightning (a spell) can't exercise this path, so use a real melee attack skill.
    # Expected ratio = the same dmg-pool-only ratio (1.44/2.5632) further multiplied by the -30% Spirit
    # Attack Speed factor (0.70) — confirms the penalty actually reduces Spirit's rate, not just its damage.
    resp = _run(picks=["Fury's Onslaught"], skill=ATTACK_SKILL, gear=ATTACK_WEAPON, dual_wield=False)
    player_dps = resp["offense"]["total_dps_vs_target"]
    spirit_dps = _spirit_dps(resp)
    assert spirit_dps / player_dps == pytest.approx((1.44 / 2.5632) * 0.70, rel=1e-3)


def test_seething_spirit_uptime_scales_linearly():
    full = _spirit_dps(_run(picks=["Ritual of Offering"], extra_conditions={"seething_spirit_uptime": 100}))
    half = _spirit_dps(_run(picks=["Ritual of Offering"], extra_conditions={"seething_spirit_uptime": 50}))
    assert half == pytest.approx(full / 2, rel=1e-6)


def test_berserk_off_no_spirit_and_no_disarm():
    resp = _run(picks=["Ritual of Offering"], extra_conditions={"berserk_active": False})
    assert resp.get("spirit_offense") is None
    assert resp["offense"]["total_dps_vs_target"] > 0.0   # NOT disarmed outside Berserk


def test_rage_infusion_undisarms_player_alongside_ritual_of_offering():
    disarmed = _run(picks=["Ritual of Offering"])
    both = _run(picks=["Ritual of Offering", "Rage Infusion"])
    assert disarmed["offense"]["total_dps_vs_target"] == 0.0
    assert both["offense"]["total_dps_vs_target"] > 0.0
    assert _spirit_dps(both) > 0.0   # Spirit still contributes alongside the un-disarmed player


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


def test_spirit_offense_inherits_main_skill_level_bonus():
    """Regression for bug-279: Seething Spirit "casts your own main skill", so a +N Main Skill
    Level source (gear/support/talent) must raise Spirit's damage too, same as it raises the
    player's — before the fix, compute.py hardcoded is_main_skill=False for Spirit's independent
    calculate_offense call, so the main_skill_level stat was never added to Spirit's effective
    level and its damage stayed frozen while the player's rose."""
    main_skill_level_gear = [{
        "item_name": "Test Main Skill Level Source",
        "contributions": [{"stat": "main_skill_level", "display_value": 3, "unit": "",
                            "slot": "amulet", "item_name": "Test Main Skill Level Source",
                            "text": "+3 to Main Skill Level"}],
    }]
    baseline = _run(picks=["Fury's Onslaught"])
    boosted = _run(picks=["Fury's Onslaught"], gear=DUAL_WEAPONS + main_skill_level_gear)
    assert boosted["offense"]["total_dps_vs_target"] > baseline["offense"]["total_dps_vs_target"]
    assert _spirit_dps(boosted) > _spirit_dps(baseline)


def test_spirit_offense_level_summary_populated_and_attributes_main_skill_level():
    """Regression: compute.py's Spirit `calculate_offense` call never attached `level_summary`
    (unlike `_offense_for_slot`'s player-skill path, which always does) — the source-attributed
    "Effective Skill Level" breakdown silently fell back to a bare `Level N` label for Spirit's
    panel in PlayerStatsScreen.tsx, even after bug-279 fixed the underlying scaled damage number."""
    main_skill_level_gear = [{
        "item_name": "Test Main Skill Level Source",
        "contributions": [{"stat": "main_skill_level", "display_value": 3, "unit": "",
                            "slot": "amulet", "item_name": "Test Main Skill Level Source",
                            "text": "+3 to Main Skill Level"}],
    }]
    resp = _run(picks=["Fury's Onslaught"], gear=DUAL_WEAPONS + main_skill_level_gear)
    spirit = resp["spirit_offense"]["seething_spirit"]
    summary = spirit.get("level_summary")
    assert summary is not None
    assert summary["bonus_level"] == 3
    assert summary["effective_level"] == summary["base_level"] + 3
    sources = summary.get("bonus_sources") or []
    assert any(s["stat"] == "main_skill_level" and s["levels"] == 3 for s in sources)


def test_spirit_stat_map_excludes_furys_onslaught_player_only_line():
    """Regression: the frontend's "Total Additional" breakdown panel read the PLAYER's global stat
    map even in Spirit mode, so it showed Fury's Onslaught's own +57% (tier2) "dealt by the player"
    line as one of Spirit's sources — even though that exact line is surgically excluded from
    Spirit's own dmg_additional total (compute.py's player_only_dmg_to_exclude removal) and the
    displayed ×total never included it. compute.py now attaches Spirit's OWN stat_map (built off
    Spirit's own, already-excluded source_log), so the row list can never disagree with the total
    again — this asserts the excluded line is simply absent from Spirit's own map."""
    resp = _run(picks=["Fury's Onslaught"], slot_levels=(5, 2, 1, 1))
    spirit = resp["spirit_offense"]["seething_spirit"]
    stat_map = spirit.get("stat_map")
    assert stat_map is not None
    dmg_sources = stat_map.get("dmg_additional", {}).get("sources", [])
    assert not any(s["source_name"] == "Fury's Onslaught" for s in dmg_sources)
    # The base trait's own +26% (tier2 Berserk dmg) line is NOT excluded — still present.
    assert any(s["source_name"] == "Seething Silhouette" for s in dmg_sources)


def test_spirit_stat_map_includes_ritual_of_offerings_own_spirit_damage_line():
    """Regression: Ritual of Offering's own "+X% additional Seething Spirit Damage" bonus was added
    to Spirit's clone via the untracked BuildSource.add() (no SourceEntry), so it correctly fed the
    numeric total but never appeared as a labelled row in any breakdown — indistinguishable from not
    applying at all. Now added via add_with_source with real source metadata and surfaced through
    Spirit's own stat_map."""
    resp = _run(picks=["Ritual of Offering"], slot_levels=(1, 3, 1, 1))
    spirit = resp["spirit_offense"]["seething_spirit"]
    stat_map = spirit["stat_map"]
    dmg_sources = stat_map["dmg_additional"]["sources"]
    ritual_rows = [s for s in dmg_sources if s["source_name"] == "Ritual of Offering"]
    assert len(ritual_rows) == 1
    assert ritual_rows[0]["amount"] == pytest.approx(0.30)   # tier3 of [.20,.25,.30,.35,.40]
    assert "30%" in ritual_rows[0]["text"] and "Seething Spirit Damage" in ritual_rows[0]["text"]


def test_spirit_stat_map_includes_furys_onslaught_spirit_attack_speed_line():
    """Regression: Fury's Onslaught's -30% additional Seething Spirit Attack Speed was also an
    untracked BuildSource.add() — it silently reduced Spirit's rate (verified by the ratio tests
    above) but had no visible row anywhere, which reads identically to "not applying" from the UI.
    Now tracked and surfaced through Spirit's own stat_map."""
    resp = _run(picks=["Fury's Onslaught"])
    spirit = resp["spirit_offense"]["seething_spirit"]
    stat_map = spirit["stat_map"]
    as_sources = stat_map["attack_speed_additional"]["sources"]
    fo_rows = [s for s in as_sources if s["source_name"] == "Fury's Onslaught"]
    assert len(fo_rows) == 1
    assert fo_rows[0]["amount"] == pytest.approx(-0.30)
    assert "-30%" in fo_rows[0]["text"] and "Seething Spirit Attack Speed" in fo_rows[0]["text"]
