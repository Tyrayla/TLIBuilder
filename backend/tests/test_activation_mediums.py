"""Activation Medium general roll parser + wiring + Wind Rhythm server-breakpoint helper.

The parser reads every medium's concatenated per-tier line into canonical rolls (identity/unit/scale/per-tier
ranges/stat/group). Wiring emits the modeled stats (duration/cdr/minion/damage/hit-damage), overrides the cast
rate for "every X s" triggers, and drives the Wind Rhythm rate. Records everything; wires only modeled stats.
"""
from __future__ import annotations
import pytest

from tests.mock_build import make_request, DUAL_WEAPONS
from server import engine_stats, EngineStatsRequest
from engine.offense import compute_wind_rhythm_rate
from engine.skill_effects.activation_medium import parse_am_rolls
from engine.tick import period_ticks
from persistence import season_manager
from server import _get_skills_data

_SKILLS = _get_skills_data(season_manager.get_active_season())


def _rolls(item_id):
    return {r["identity"]: r for r in parse_am_rolls(_SKILLS[item_id])}


def _sup(item_id, **kw):
    return {"slot": 1, "item_id": item_id, "level": 1, "enabled": True, **kw}


def _off(skill, sups, cond=None, gear=None, level=20):
    return engine_stats(EngineStatsRequest(**make_request(
        skill, level, attached_supports=sups, extra_conditions=cond, gear=gear or DUAL_WEAPONS))).get("offense") or {}


# ── Parser ─────────────────────────────────────────────────────────────────────
def test_parser_covers_every_medium_without_error():
    ams = [k for k, v in _SKILLS.items() if "Activation Medium" in (v.get("skill_tags") or [])]
    assert len(ams) >= 20
    for k in ams:
        for r in parse_am_rolls(_SKILLS[k]):
            assert r["identity"] and r["unit"] in ("%", "s", "m", "")
            assert r["ranges_by_tier"]      # at least one tier


def test_rhythm_rolls_interval_seconds_and_move_cap_percent():
    r = _rolls("activation_medium_rhythm")
    assert r["trigger_interval"]["unit"] == "s" and r["trigger_interval"]["scale"] == 1.0
    assert r["trigger_interval"]["stat_key"] == "trigger_interval"
    # tier-0 has NO interval (only the movement line); interval bands start at tier 1 (0.3–0.5 → mid 0.4).
    assert 0 not in r["trigger_interval"]["ranges_by_tier"]
    assert r["trigger_interval"]["ranges_by_tier"][1]["mid"] == pytest.approx(0.4, abs=1e-6)
    assert r["rhythm_move_cap"]["unit"] == "%" and 0 in r["rhythm_move_cap"]["ranges_by_tier"]


def test_every_vs_interval_classification():
    # "every X s" = a real cadence (wired); "Interval: X s" = a rate-limit (recorded, not wired).
    assert _rolls("activation_medium_track")["trigger_interval"]["wired"] is True
    assert _rolls("activation_medium_root_attack")["trigger_rate_limit"]["wired"] is False


def test_duration_cooldown_selector_group():
    r = _rolls("activation_medium_boss")
    assert r["duration_additional"]["group"] == "cdr_or_duration"
    assert r["cdr_additional"]["group"] == "cdr_or_duration"
    assert r["duration_additional"]["stat_key"] == "skill_effect_duration_additional"
    assert r["cdr_additional"]["stat_key"] == "cdr_speed_additional"


# ── Wiring (generic trigger override + additive stats) ───────────────────────────
def test_trigger_interval_overrides_cast_rate_generically():
    # A non-Demolisher spell triggered by Rhythm fires at 1/interval, not its cast rate.
    o = _off("chain_lightning", [_sup("activation_medium_rhythm",
                                      specific_rolls={"trigger_interval": 0.5},
                                      specific_roll_tiers={"trigger_interval": 1})], level=14)
    assert o["skills_per_second"] == pytest.approx(2.0, abs=1e-6)


def _emit(medium_id, condition_state=None, **sup_kw):
    """Run the AM wiring hook against a fresh source; return {stat: amount} it emitted (slot-local, materialized)."""
    from engine.skill_effects.activation_medium import apply_slot_effects
    from engine.models import BuildSource
    src = BuildSource()
    apply_slot_effects(source=src, resolved=None, slot=1, condition_state=(condition_state or {}), mod_tags=set(),
                       attached_supports=[_sup(medium_id, **sup_kw)], skills_by_id=_SKILLS)
    eff = src.materialize_for_skill(set(), 1)
    return {e.stat: e.amount for e in eff.source_log}


def test_duration_selector_emits_only_chosen_option():
    emitted = _emit("activation_medium_boss",
                    roll_group_choice={"cdr_or_duration": "duration_additional"},
                    specific_rolls={"duration_additional": 0.20}, specific_roll_tiers={"duration_additional": 0})
    assert emitted.get("skill_effect_duration_additional") == pytest.approx(0.20)
    assert "cdr_speed_additional" not in emitted     # the unchosen option is not emitted


def test_cooldown_selector_emits_cdr_when_chosen():
    emitted = _emit("activation_medium_boss",
                    roll_group_choice={"cdr_or_duration": "cdr_additional"},
                    specific_rolls={"cdr_additional": 0.20}, specific_roll_tiers={"cdr_additional": 0})
    assert emitted.get("cdr_speed_additional") == pytest.approx(0.20)
    assert "skill_effect_duration_additional" not in emitted


def test_minion_medium_emits_minion_damage():
    emitted = _emit("activation_medium_minion",
                    specific_rolls={"minion_dmg_additional": 0.33}, specific_roll_tiers={"minion_dmg_additional": 1})
    assert emitted.get("minion_dmg_additional") == pytest.approx(0.33)


# ── Rhythm per-level movement-damage rate (2026-07-12 fix: data-driven, was hardcoded 0.03) ──────
def test_rhythm_move_rate_by_level_matches_crawled_progression():
    # Anchors the per-level %/meter rate to SS12's OWN crawled text (activation_medium_rhythm.progression):
    # it drops 3%->2% at level 2. A future retune (or a regression back to a hardcoded constant) trips this.
    from engine.skill_effects.activation_medium import _rhythm_move_rate_by_level
    rates = _rhythm_move_rate_by_level(_SKILLS["activation_medium_rhythm"])
    assert rates == {0: 0.03, 1: 0.03, 2: 0.02, 3: 0.02}


def test_rhythm_move_cap_uses_level_2_rate_not_hardcoded_3_percent():
    # Level-2 Rhythm: rate is 2%/m (not the old hardcoded 3%/m). meters=3 stays under the level-2 cap
    # (14-16%, mid 15%), so the emitted dmg_additional exercises the RATE, not the min() clamp.
    emitted = _emit("activation_medium_rhythm", condition_state={"demolisher_meters_moved": 3},
                    level=2, specific_roll_tiers={"rhythm_move_cap": 2})
    assert emitted.get("dmg_additional") == pytest.approx(0.06, abs=1e-9)   # 0.02 * 3, not 0.03 * 3 (0.09)


def test_rhythm_move_cap_still_clamps_at_the_cap():
    # Same level-2 Rhythm, but with enough meters that the uncapped 2%/m value (0.02*20=0.40) blows past
    # the level-2 cap's mid (0.15) -> min(...) clamps to the cap, confirming the clamp survived the fix.
    emitted = _emit("activation_medium_rhythm", condition_state={"demolisher_meters_moved": 20},
                    level=2, specific_roll_tiers={"rhythm_move_cap": 2})
    assert emitted.get("dmg_additional") == pytest.approx(0.15, abs=1e-9)


def test_rhythm_move_cap_uses_3_percent_at_level_0_and_1():
    # Levels 0 and 1 are unchanged by the fix (still 3%/m) — guards the fix didn't regress the low tiers.
    for lvl in (0, 1):
        emitted = _emit("activation_medium_rhythm", condition_state={"demolisher_meters_moved": 3},
                        level=lvl, specific_roll_tiers={"rhythm_move_cap": lvl})
        assert emitted.get("dmg_additional") == pytest.approx(0.09, abs=1e-9), f"level {lvl}"


# ── Wind Rhythm (server-tick breakpoint helper) ─────────────────────────────────
class _WSrc:
    def __init__(self, cast_inc=0.0, cast_add=0.0, cdr_inc=0.0, cdr_add=0.0):
        self._v = {"cast_speed_inc": cast_inc, "cast_speed_additional": cast_add,
                   "cdr_speed_inc": cdr_inc, "cdr_speed_additional": cdr_add}

    def total(self, k):
        return self._v.get(k, 0.0)


def test_wind_rhythm_formula_matches_calculator():
    # base 0.5, wind 40%, cdr 0, cast 100%, add'l cast 100% → raw = 0.5/(1+0.4×(1×2)) = 0.27778 → 9 ticks → 0.3s.
    w = compute_wind_rhythm_rate(_WSrc(cast_inc=1.0, cast_add=1.0), 0.5, 0.40)
    assert w["raw_cast_time"] == pytest.approx(0.27778, abs=1e-4)
    assert w["ticks"] == 9 and w["server_cast_time"] == pytest.approx(9 / 30, abs=1e-6)
    assert w["rate"] == pytest.approx(30 / 9, abs=1e-6)


def test_wind_rhythm_cdr_is_separate_factor():
    # base 0.5, cdr_inc 8% → raw 0.5/1.08 = 0.46296 → ceil(13.889)=14 ticks (matches the calculator table).
    w = compute_wind_rhythm_rate(_WSrc(cdr_inc=0.08), 0.5, 0.40)
    assert w["raw_cast_time"] == pytest.approx(0.5 / 1.08, abs=1e-5)
    assert w["ticks"] == 14


def test_wind_rhythm_additional_cast_is_multiplicative():
    # +10% additional cast shifts the cast breakpoint by ÷1.1 (Tyra-observed 350→318). Check via raw: with
    # cast_inc=1.0, add'l 0 vs add'l 0.1 → final_cast 1.0 vs 1.1 → raw drops by the 1.1 factor in the wind term.
    a = compute_wind_rhythm_rate(_WSrc(cast_inc=1.0, cast_add=0.0), 0.5, 0.40)["raw_cast_time"]
    b = compute_wind_rhythm_rate(_WSrc(cast_inc=1.0, cast_add=0.1), 0.5, 0.40)["raw_cast_time"]
    assert b == pytest.approx(0.5 / (1 + 0.40 * 1.0 * 1.1), abs=1e-5)
    assert b < a


def test_wind_rhythm_drives_cast_rate_end_to_end():
    # Base cooldown follows the medium TIER (support level); the share follows its own per-roll tier.
    o = _off("chain_lightning", [_sup("activation_medium_wind_rhythm", level=0,
             specific_rolls={"wind_cast_to_cdr": 0.40}, specific_roll_tiers={"wind_cast_to_cdr": 0})], level=14)
    assert o["wind_rhythm_active"] is True
    assert o["wind_rhythm_base_cooldown"] == pytest.approx(0.5)   # tier-0 base cooldown
    assert o["skills_per_second"] == pytest.approx(o["wind_rhythm_rate"], abs=1e-6)
    o2 = _off("chain_lightning", [_sup("activation_medium_wind_rhythm", level=3,
              specific_rolls={"wind_cast_to_cdr": 0.40}, specific_roll_tiers={"wind_cast_to_cdr": 0})], level=14)
    assert o2["wind_rhythm_base_cooldown"] == pytest.approx(0.8)   # tier-3 base cooldown


# ── Generalized "additional Hit Damage for the supported skill" ──────────────────
def test_generalized_hit_damage_applies_to_non_bespoke_supports():
    from engine.support_resolver import resolve_support_contributions
    from server import _translate_condition_expr as tc
    for sid in ("bombard_cannon_magnificent", "charged_pummel_drastic_shift_magnificent"):
        st = _SKILLS[sid]["skill_type"]
        contribs = resolve_support_contributions([{"item_id": sid, "skill_type": st, "rank": 5, "level": 1}],
                                                 _SKILLS, tc)
        assert any(c["stat_key"] == "hit_dmg_additional" for c in contribs)
