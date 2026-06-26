"""Selena — Sing with the Tide (trait_id "sing_with_the_tide"). On-Tide damage buffs/debuffs scaled by Tide Effect,
Bard/Loud Song states, and the advanced picks. Module unit tests (exact amounts, tide_mult fed via ls_state) +
engine integration (enemy-multiplier consumption, Bard warning, trait_id=None unchanged).
"""
import pytest
from engine.hero_traits import sing_with_the_tide as t
from server import engine_stats, EngineStatsRequest
from tests.mock_build import make_request, weapon

WEAPON = [weapon("weapon1", "Blade", 350, 350, 1.5, 500)]


# ── Module unit tests ──────────────────────────────────────────────────────────────
def _ap(levels=None, picks=None, ls=None, conds=None):
    return t.apply(build_input=None, condition_state=conds or {}, ls_state=ls or {},
                   uptime_mode="max", slot_levels=levels or [5, 1, 1, 1], advanced_picks=picks or [])["contributions"]


def _amt(c, k):
    return sum(x["amount"] for x in c if x["stat_key"] == k)


def _has(c, k):
    return any(x["stat_key"] == k for x in c)


def test_base_on_tide_bard_defaults():
    c = _ap()                                                  # base L5, Bard default, on Tide, tide_mult=1 (pass 1)
    assert _amt(c, "dmg_additional") == pytest.approx(0.15)    # on-Tide +15%
    assert _amt(c, "tide_dmg_taken") == pytest.approx(0.20)    # L5 enemy debuff
    assert _amt(c, "channeled_dmg_additional") == pytest.approx(-0.20)   # Bard penalty
    assert not _has(c, "attack_speed_additional")             # no Loud Song penalties by default
    assert _amt(c, "skill_area_inc") == pytest.approx(0.10)    # Artificial Moon (L5)


def test_enemy_tide_dmg_taken_scales_with_level():
    assert _amt(_ap(levels=[2, 1, 1, 1]), "tide_dmg_taken") == pytest.approx(0.05)
    assert _amt(_ap(levels=[1, 1, 1, 1]), "tide_dmg_taken") == 0.0       # L1 = 0


def test_loud_song_penalties_and_tide_effect():
    c = _ap(conds={"selena_bard": False, "selena_loud_song": True})
    assert _amt(c, "tide_effect_additional") == pytest.approx(0.80)
    assert _amt(c, "attack_speed_additional") == pytest.approx(-0.20)
    assert _amt(c, "cast_speed_additional") == pytest.approx(-0.20)
    assert _amt(c, "movement_speed_additional") == pytest.approx(-0.20)
    assert not _has(c, "channeled_dmg_additional")            # not Bard


def test_both_states_active_future_memory():
    # Ceaseless Tide will enable both at once — independent gating must allow it.
    c = _ap(conds={"selena_bard": True, "selena_loud_song": True})
    assert _amt(c, "channeled_dmg_additional") == pytest.approx(-0.20)   # Bard
    assert _amt(c, "tide_effect_additional") == pytest.approx(0.80)      # Loud Song
    assert _amt(c, "attack_speed_additional") == pytest.approx(-0.20)


def test_ceaseless_tide_flag_suppresses_loud_song_speed_penalties():
    c = _ap(conds={"selena_loud_song": True, "ceaseless_tide": True})
    assert not _has(c, "attack_speed_additional")             # penalties suppressed
    assert _amt(c, "tide_effect_additional") == pytest.approx(0.80)      # +80% still applies


def test_tide_mult_scales_damage_and_debuff():
    c = _ap(ls={"tide_mult": 2.0})
    assert _amt(c, "dmg_additional") == pytest.approx(0.30)    # 0.15 × 2.0
    assert _amt(c, "tide_dmg_taken") == pytest.approx(0.40)    # 0.20 × 2.0


def test_undersea_ballad_converts_global_skill_area_to_increased_tide_effect():
    assert _amt(_ap(picks=["Undersea Ballad"], ls={"skill_area_inc": 0.50}),
                "tide_effect_inc") == pytest.approx(0.50)
    assert _amt(_ap(picks=["Undersea Ballad"], ls={"skill_area_inc": 2.0}),
                "tide_effect_inc") == pytest.approx(0.90)     # tier0 cap +90%


def test_sea_foam_channeled_stacks_min_doubles_in_bard():
    ls = {"max_channeled_stacks_flat": 2.0, "min_channeled_stacks_flat": 1.0}
    bard = _ap(picks=["Sea Foam Nocturne"], ls=ls)            # stacks = 2 + 1×2 = 4
    assert _amt(bard, "tide_effect_additional") == pytest.approx(0.16 * 4)
    loud = _ap(picks=["Sea Foam Nocturne"], ls=ls, conds={"selena_bard": False, "selena_loud_song": True})
    assert _amt(loud, "tide_effect_additional") == pytest.approx(0.80 + 0.16 * 3)   # +Loud Song 0.80, stacks 2+1=3


def test_idyll_per_metre_additional_damage():
    c = _ap(picks=["Idyll of the Tide"])                      # tier0 0.01 × 15 stacks = 0.15, + base 0.15
    assert _amt(c, "dmg_additional") == pytest.approx(0.30)
    c2 = _ap(picks=["Idyll of the Tide"], conds={"idyll_stacks": 5})
    assert _amt(c2, "dmg_additional") == pytest.approx(0.15 + 0.01 * 5)


def test_chantey_only_in_loud_song_and_murmurs_only_in_bard():
    chantey_bard = _ap(picks=["Chantey of Sinking"], levels=[5, 1, 1, 1])
    assert not _has(chantey_bard, "tide_effect_additional")   # Chantey needs Loud Song
    chantey_loud = _ap(picks=["Chantey of Sinking"], levels=[5, 1, 1, 1],
                       conds={"selena_bard": False, "selena_loud_song": True})
    assert _amt(chantey_loud, "tide_effect_additional") == pytest.approx(0.80 + 0.35 * 2)   # Loud +0.80, 2 stacks
    murmurs = _ap(picks=["Murmurs of the Distant Tide"], levels=[5, 1, 1, 1])
    assert _amt(murmurs, "tide_effect_additional") == pytest.approx(0.60)   # Bard tier0


def test_wave_aria_vs_enemies_on_tide():
    assert _amt(_ap(picks=["Wave Aria"]), "dmg_additional") == pytest.approx(0.15 + 0.10)   # base + Wave Aria tier0


def test_off_tide_zeroes_tide_effects():
    c = _ap(conds={"player_on_tide": False, "enemy_on_tide": False})
    assert not _has(c, "dmg_additional")
    assert not _has(c, "tide_dmg_taken")
    assert _amt(c, "channeled_dmg_additional") == pytest.approx(-0.20)   # Bard penalty still applies


def test_disabled_base_node_emits_nothing():
    assert _ap(levels=[-5, 1, 1, 1]) == []


def test_status_lines_warn_on_bard_incompatible_skill():
    attack = t.status_lines(slot_levels=[5, 1, 1, 1], advanced_picks=[],
                            main_skill_tags=["Attack"], main_skill_name="Cleave")
    assert any(s["status"] == "warning" and "Cleave" in s["text"] for s in attack)
    chan = t.status_lines(slot_levels=[5, 1, 1, 1], advanced_picks=[],
                          main_skill_tags=["Spell", "Channeled"], main_skill_name="Beam")
    assert not any(s["status"] == "warning" for s in chan)    # channeled is fine in Bard


# ── Engine integration ──────────────────────────────────────────────────────────────
def _off(picks=None, conds=None, skill="icebound_beam", trait="sing_with_the_tide"):
    kw = dict(gear=WEAPON, trait_slot_levels=[5, 1, 1, 1], advanced_trait_selections=picks or [],
              condition_state=conds or {})
    if trait:
        kw["trait_id"] = trait
    req = make_request(skill, 16, **kw)
    r = engine_stats(EngineStatsRequest(**req))
    return (r if isinstance(r, dict) else r.model_dump())


def test_tide_dmg_taken_raises_enemy_multiplier():
    none = _off(trait=None)["offense"]
    bard = _off()["offense"]
    em_none = list(none["enemy_mult_by_type"].values())[0]
    em_bard = list(bard["enemy_mult_by_type"].values())[0]
    assert em_bard > em_none                                   # enemy +20% taken on Tide
    assert em_bard == pytest.approx(em_none * 1.20, rel=0.01)  # L5 base, tide_mult≈1 in Bard (no Tide Effect sources)


def test_loud_song_converges_tide_effect():
    # Loud Song +80% Tide Effect → tide_mult 1.8 → enemy debuff 0.20×1.8 = 0.36.
    none = _off(trait=None)["offense"]
    loud = _off(conds={"selena_bard": False, "selena_loud_song": True})["offense"]
    em_none = list(none["enemy_mult_by_type"].values())[0]
    em_loud = list(loud["enemy_mult_by_type"].values())[0]
    assert em_loud == pytest.approx(em_none * 1.36, rel=0.01)


def test_bard_warning_surfaces_for_attack_main_skill():
    d = _off(skill="berserking_blade")
    assert any(s.get("status") == "warning" for s in d.get("trait_mod_statuses", []))
