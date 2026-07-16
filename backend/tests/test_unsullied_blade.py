"""Rosa — Unsullied Blade (trait_id "unsullied_blade"). Spell→Attack damage bridge, Mercury Baptism true damage,
Realm-of-Mercury mana scaling, the main-hand-only damage split, and the advanced picks. Module unit tests (exact
amounts, converged scalars fed via ls_state) + engine integration.

NOTE (2026-07-16, review-council finding): every module unit test above calls `t.apply(build_input=None, ...)`,
so `season = getattr(build_input, "season", None)` is always `None` — `_catalog.pick_tier_values` short-circuits
straight to the SS12 literal fallback for those. That means Boundless Sanctuary's `_boundless_ele_per_enemy`/
`_boundless_ele_cap` catalog-read path (added alongside `_catalog`, see the module docstring) was never actually
exercised by any test. The "Engine integration — Boundless Sanctuary catalog read" section below closes that gap
by going through the real `engine_stats` endpoint with the active season pinned (the `_pinned_season` pattern
established in `test_chromatic_shot.py` / `test_high_court_chariot.py`), so it drives a real `build_input.season`
and reads the real per-season `_hero_traits.json` catalog text, not the fallback.
"""
import contextlib

import pytest
from engine.hero_traits import unsullied_blade as t
from persistence import season_manager
from server import engine_stats, EngineStatsRequest
from tests.mock_build import make_request, weapon, DUAL_WEAPONS

WEAPON = [weapon("weapon1", "Blade", 300, 300, 1.5, 500)]


@contextlib.contextmanager
def _pinned_season(name):
    """Temporarily set the ACTIVE season for the `engine_stats` round trip below, restoring whatever was active
    on exit (even on failure) — see module docstring."""
    prev = season_manager.get_active_season()
    season_manager.set_active_season(name)
    try:
        yield
    finally:
        season_manager.set_active_season(prev)


# ── Module unit tests ──────────────────────────────────────────────────────────────
def _ap(levels=None, picks=None, ls=None, conds=None):
    return t.apply(build_input=None, condition_state=conds or {}, ls_state=ls or {},
                   uptime_mode="max", slot_levels=levels or [5, 5, 5, 5], advanced_picks=picks or [])


def _amt(res, k):
    return sum(x["amount"] for x in res["contributions"] if x["stat_key"] == k)


def _has(res, k):
    return any(x["stat_key"] == k for x in res["contributions"])


def test_base_bridge_and_spell_damage_levels():
    r = _ap(levels=[5, 1, 1, 1])
    assert _amt(r, "spell_dmg_to_attack") == 1.0
    assert _amt(r, "mana_consume_external_blocked") == 1.0   # "Mana can only be consumed by Mystic Mercury" lock
    assert _amt(r, "max_mercury_points_flat") == 100.0
    assert _amt(r, "spell_dmg_additional") == pytest.approx(0.20)        # base L5 → +20%


def test_realm_scaling_tracks_unsealed_fraction():
    full = _ap(levels=[5, 1, 1, 1], ls={"max_mana": 2000.0, "unsealed_mana": 2000.0})
    assert _amt(full, "attack_speed_additional") == pytest.approx(0.20)  # 100% unsealed → cap +20%
    assert _amt(full, "elemental_dmg_additional") == pytest.approx(0.20)
    half = _ap(levels=[5, 1, 1, 1], ls={"max_mana": 2000.0, "unsealed_mana": 1000.0})
    assert _amt(half, "attack_speed_additional") == pytest.approx(0.10)  # 50% unsealed → +10%


def test_mystic_state_drops_realm_bonuses():
    r = _ap(levels=[5, 5, 1, 1], ls={"max_mana": 2000.0, "unsealed_mana": 2000.0, "dominant_element": "fire"},
            conds={"realm_of_mercury": False})
    assert not _has(r, "attack_speed_additional")                        # realm off
    assert not _has(r, "mercury_baptism_fraction")
    assert r["set_conditions"] == {}                                     # no infiltration off-realm
    assert _amt(r, "spell_dmg_to_attack") == 1.0                         # base bridge still on


def test_baptism_of_purity_fraction_mana_and_infiltration():
    r = _ap(levels=[5, 5, 1, 1], ls={"max_mana": 1000.0, "unsealed_mana": 1000.0, "dominant_element": "cold"})
    assert _amt(r, "mercury_baptism_fraction") == pytest.approx(0.44)    # L45 tier 4
    assert _amt(r, "max_mana_additional") == pytest.approx(0.20)
    assert r["set_conditions"]["enemy_affected_by_cold_infiltration"] is True


def test_cleanse_filth_mana_before_life_and_ele_cap():
    r = _ap(picks=["Cleanse Filth"], levels=[5, 1, 5, 1], ls={"max_mana": 5000.0, "unsealed_mana": 5000.0})
    assert _amt(r, "mana_before_life_inc") == pytest.approx(0.25)
    # tier4: 0.04/1000 × 5000 = 0.20 (under the +80% cap)
    assert _amt(r, "elemental_dmg_additional") == pytest.approx(0.20 + 0.04 * 5)   # +realm ele 0.20
    capped = _ap(picks=["Cleanse Filth"], levels=[5, 1, 5, 1], ls={"max_mana": 100000.0, "unsealed_mana": 100000.0})
    assert _amt(capped, "elemental_dmg_additional") == pytest.approx(0.20 + 0.80)  # cap +80%


def test_boundless_sanctuary_per_enemy_cap():
    r = _ap(picks=["Boundless Sanctuary"], levels=[5, 1, 5, 1],
            ls={"max_mana": 1000.0, "unsealed_mana": 1000.0}, conds={"enemies_in_realm": 1, "enemy_count_weight": 5})
    # tier4: 0.10/enemy × (1×5 Boss weight) = 0.50 (under +100% cap)
    assert _amt(r, "elemental_dmg_additional") == pytest.approx(0.20 + 0.50)


def test_utmost_devotion_lifts_override_and_scales_on_mercury():
    r = _ap(picks=["Utmost Devotion"], levels=[5, 1, 1, 5], ls={"max_mana": 3000.0, "unsealed_mana": 3000.0,
            "max_mercury_points_flat": 100.0, "max_mercury_points_inc": 0.0})
    assert not _has(r, "mana_consume_external_blocked")                  # Utmost lifts the consume lock
    assert _amt(r, "max_mercury_points_inc") == pytest.approx(0.30)      # 0.10/1000 × 3000
    # current mercury = 100 × (1+0) × 100% = 100; tier4 ele = 0.001 × 100 = 0.10
    assert _amt(r, "elemental_dmg_additional") == pytest.approx(0.20 + 0.001 * 100)


def test_born_to_cleanse_mystic_vs_realm_retain():
    realm = _ap(picks=["Born to Cleanse"], levels=[5, 1, 1, 5], ls={"max_mana": 1000.0, "unsealed_mana": 1000.0})
    assert _amt(realm, "elemental_dmg_additional") == pytest.approx(0.20 + 0.25 * 0.40)   # realm: 40% retained
    assert _amt(realm, "main_hand_dmg_additional") == pytest.approx(0.48 * 0.40)
    mystic = _ap(picks=["Born to Cleanse"], levels=[5, 1, 1, 5], conds={"realm_of_mercury": False})
    assert _amt(mystic, "elemental_dmg_additional") == pytest.approx(0.25)                # mystic: full
    assert _amt(mystic, "main_hand_dmg_additional") == pytest.approx(0.48)


def test_mystic_phase_consumes_realm_phase_restores():
    # Mystic Mercury (build-up) consumes 10% unsealed Max Mana/attack and turns OFF the Realm bonuses.
    m = _ap(levels=[5, 1, 1, 1], ls={"max_mana": 2000.0, "unsealed_mana": 2000.0}, conds={"mystic_mercury": True})
    assert _amt(m, "mana_consumed_pct_current_per_attack_use_mystic") == pytest.approx(0.10)
    assert not _has(m, "mana_restored_pct_current_per_attack_use")       # no restore in Mystic
    assert not _has(m, "attack_speed_additional")                        # Mystic overrides Realm bonuses
    # Default (Realm) phase restores 15%/attack and does NOT consume.
    rlm = _ap(levels=[5, 1, 1, 1], ls={"max_mana": 2000.0, "unsealed_mana": 2000.0})
    assert _amt(rlm, "mana_restored_pct_current_per_attack_use") == pytest.approx(0.15)
    assert not _has(rlm, "mana_consumed_pct_current_per_attack_use_mystic")


def test_born_to_cleanse_reduces_realm_restore():
    # −30% additional Mana restoration for Realm → 15% × (1 − 0.30) = 10.5%.
    r = _ap(picks=["Born to Cleanse"], levels=[5, 1, 1, 5], ls={"max_mana": 1000.0, "unsealed_mana": 1000.0})
    assert _amt(r, "mana_restored_pct_current_per_attack_use") == pytest.approx(0.15 * 0.70)


def test_disabled_base_node_emits_nothing():
    assert _ap(levels=[-5, 5, 5, 5])["contributions"] == []


# ── Engine integration ──────────────────────────────────────────────────────────────
def _gear(**kv):
    return [{"item_name": "X", "contributions": [
        {"stat": k, "display_value": v, "unit": "", "slot": "ring", "item_name": "X", "text": k}
        for k, v in kv.items()]}]


def _off(gear, trait="unsullied_blade", picks=None, levels=None, conds=None, skill="berserking_blade"):
    kw = dict(gear=gear, advanced_trait_selections=picks or [], trait_slot_levels=levels or [5, 1, 1, 1],
              condition_state=conds or {})
    if trait:
        kw["trait_id"] = trait
    r = engine_stats(EngineStatsRequest(**make_request(skill, 16, **kw)))
    return (r if isinstance(r, dict) else r.model_dump())["offense"]


def test_spell_damage_bridges_to_attacks_only_with_trait():
    spell = _gear(spell_dmg_additional=0.50)
    # Without the trait, spell damage does nothing to an attack skill.
    assert (_off(WEAPON + spell, trait=None)["total_dps_vs_target"]
            == pytest.approx(_off(WEAPON, trait=None)["total_dps_vs_target"], rel=1e-6))
    # With the trait, the bridged +50% additional spell damage multiplies the attack's damage by ×1.50.
    assert (_off(WEAPON + spell)["total_dps_vs_target"]
            == pytest.approx(_off(WEAPON)["total_dps_vs_target"] * 1.50, rel=0.01))


def test_mercury_baptism_adds_unmitigated_true_damage():
    # fire elemental attack so the baptism stage has an elemental share; L45 enabled, realm default on.
    g = WEAPON + _gear(fire_attack_dmg_flat_min=200, fire_attack_dmg_flat_max=200)
    o = _off(g, levels=[5, 5, 1, 1])
    assert o["mercury_baptism_fraction"] == pytest.approx(0.44)
    assert o["mercury_baptism_dps"] > 0.0
    off_realm = _off(g, levels=[5, 5, 1, 1], conds={"realm_of_mercury": False})
    assert off_realm["mercury_baptism_dps"] == 0.0                       # no Baptism outside Realm


def test_main_hand_split_single_vs_dual():
    g = _gear(main_hand_dmg_additional=0.40)
    single = _off(WEAPON, trait=None), _off(WEAPON + g, trait=None)
    assert single[1]["total_dps_vs_target"] == pytest.approx(single[0]["total_dps_vs_target"] * 1.40, rel=0.01)
    dual = _off(DUAL_WEAPONS, trait=None), _off(DUAL_WEAPONS + g, trait=None)
    ratio = dual[1]["total_dps_vs_target"] / dual[0]["total_dps_vs_target"]
    assert 1.0 < ratio < 1.40                                            # only the weapon1 share scaled


def test_trait_none_unchanged():
    o = _off(WEAPON, trait=None)
    assert o["mercury_baptism_dps"] == 0.0
    assert o["mercury_baptism_fraction"] == 0.0


# ── Mana cycle (consume / restore / lock) integration ─────────────────────────────────
def _full(gear, trait="unsullied_blade", picks=None, levels=None, conds=None, skill="berserking_blade"):
    kw = dict(gear=gear, advanced_trait_selections=picks or [], trait_slot_levels=levels or [5, 1, 1, 1],
              condition_state=conds or {})
    if trait:
        kw["trait_id"] = trait
    r = engine_stats(EngineStatsRequest(**make_request(skill, 16, **kw)))
    return r if isinstance(r, dict) else r.model_dump()


def _consume_only(c):
    """The consume drain governed by the 'only Mystic consumes' lock. mana_per_sec is already consume-only —
    the skill's intrinsic cost is a SEPARATE field (skill_cost_mana_per_sec), never lumped into consumption."""
    return c["mana_per_sec"]


def test_consume_lock_blocks_external_mana_consume_until_utmost():
    drain = _gear(mana_consumed_flat_per_sec=50.0)
    # Lock ON (base node, no Utmost) → the external 50/s mana consume is zeroed (skill cost still applies separately).
    assert _consume_only(_full(WEAPON + drain)["consumption"]) == pytest.approx(0.0, abs=1e-6)
    # Utmost Devotion lifts the lock → the external 50/s consume counts again.
    lifted = _full(WEAPON + drain, picks=["Utmost Devotion"], levels=[5, 1, 1, 5])
    assert _consume_only(lifted["consumption"]) == pytest.approx(50.0, rel=1e-3)


def test_mystic_consume_counts_and_realm_restore_feeds_recovery():
    # Mystic phase: the trait's own consume counts even with the lock on (it bypasses it). Measured net of skill cost.
    mystic = _full(WEAPON, conds={"mystic_mercury": True})
    assert _consume_only(mystic["consumption"]) > 0.0
    assert mystic["recovery"]["restoration_mana_per_sec"] == pytest.approx(0.0, abs=1e-6)   # no restore in Mystic
    # Realm phase (default): restores mana on attack, no consume (skill cost aside).
    realm = _full(WEAPON)
    assert realm["recovery"]["restoration_mana_per_sec"] > 0.0
    assert _consume_only(realm["consumption"]) == pytest.approx(0.0, abs=1e-6)


# ── Engine integration — Boundless Sanctuary catalog read (SS12 vs SS13) ───────────────
# Real season data (not synthetic): SS12 kept its literal-era values, SS13 rebalanced both the per-enemy
# bonus AND its cap down a tier. `_boundless_ele_per_enemy`/`_boundless_ele_cap` read this live from each
# season's own `_hero_traits.json` via `_catalog.pick_tier_values` — same code path for both seasons, no
# `if season ==` branch (see `unsullied_blade.py`'s 2026-07-16 drift-fix docstring). This must go through the
# real `engine_stats` endpoint with a real `build_input.season` (unlike every unit test above, which calls
# `t.apply(build_input=None, ...)` and therefore always short-circuits to the SS12 fallback literal, never
# touching this catalog-read path at all).
_BOUNDLESS_PER_ENEMY = {"SS12": [0.06, 0.07, 0.08, 0.09, 0.10], "SS13": [0.05, 0.06, 0.07, 0.08, 0.09]}
_BOUNDLESS_CAP = {"SS12": [0.60, 0.70, 0.80, 0.90, 1.00], "SS13": [0.50, 0.60, 0.70, 0.80, 0.90]}


def _boundless_amt(resp):
    """The Boundless Sanctuary source's own contribution to Additional Elemental Damage (isolated from the
    base Realm-of-Mercury +20% that's always also present)."""
    sources = resp["stats"]["elemental_dmg_additional"]["sources"]
    return sum(s["amount"] for s in sources if s["source_name"] == "Boundless Sanctuary")


@pytest.mark.parametrize("season", ["SS12", "SS13"])
@pytest.mark.parametrize("tier", [1, 5])
def test_boundless_sanctuary_catalog_read_per_enemy_and_cap(season, tier):
    with _pinned_season(season):
        # Isolate the per-enemy value: weighted enemy count of exactly 1 keeps it well under the cap at every tier.
        per_enemy_resp = _full(WEAPON, picks=["Boundless Sanctuary"], levels=[5, 1, tier, 1],
                                conds={"enemies_in_realm": 1, "enemy_count_weight": 1})
        assert _boundless_amt(per_enemy_resp) == pytest.approx(_BOUNDLESS_PER_ENEMY[season][tier - 1])
        # Isolate the cap: a large weighted enemy count blows well past per_enemy × enemies for every tier.
        cap_resp = _full(WEAPON, picks=["Boundless Sanctuary"], levels=[5, 1, tier, 1],
                          conds={"enemies_in_realm": 50, "enemy_count_weight": 1})
        assert _boundless_amt(cap_resp) == pytest.approx(_BOUNDLESS_CAP[season][tier - 1])
