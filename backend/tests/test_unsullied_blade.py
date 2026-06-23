"""Rosa — Unsullied Blade (trait_id "unsullied_blade"). Spell→Attack damage bridge, Mercury Baptism true damage,
Realm-of-Mercury mana scaling, the main-hand-only damage split, and the advanced picks. Module unit tests (exact
amounts, converged scalars fed via ls_state) + engine integration.
"""
import pytest
from engine.hero_traits import unsullied_blade as t
from server import engine_stats, EngineStatsRequest
from tests.mock_build import make_request, weapon, DUAL_WEAPONS

WEAPON = [weapon("weapon1", "Blade", 300, 300, 1.5, 500)]


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
    assert _amt(r, "mana_cost_override") == 1.0
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
    assert not _has(r, "mana_cost_override")                             # Utmost lifts the override
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
