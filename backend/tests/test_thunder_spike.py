"""Thunder Spike (thunder_spike, SS12) — Shadow Strike delivery model + skill-specific mechanics.

Independent testing pass, designed from the spec (owner-approved; sources: data/help_db.json
"shadow-strike", data/master_glossary.json id 136, data/verification/shadow-strike.json,
data/verification/thunder-spike.json), NOT from reading the implementation.

Formula (Help DB "shadow-strike" + glossary 136 "Phantom"):
    f(0) = 1.0
    f(N>=1) = 1 + (1 + 0.30*(N-1)) * (1 + Sigma shadow_dmg_additional)
    shadow_mult (Despised Shadow EV mix) = (1-p)*f(N) + p*f(N+k), p=0.33, k=3 (corroded 4)

Real end-to-end gear check (Despised Shadow + Frantic Shadow both equipped): N=1, p=0.33, k=3,
shadow_dmg_additional=0.15 (Despised Shadow's +(14-16)% additional Shadow Damage midpoint) ->
shadow_mult = 0.67*f(1) + 0.33*f(4) = 0.67*2.15 + 0.33*3.185 = 2.49155 (derived independently below,
matches data/verification/shadow-strike.json's recorded implementation value).
"""
from __future__ import annotations

import math

import pytest

from engine.models import BuildSource
from engine.offense import calculate_offense, _shadow_multiplier
from engine.skill_resolver import ResolvedSkill, SkillHitForm, resolve_skill, _REGISTRY
from server import engine_stats, EngineStatsRequest, _get_skills_data
from persistence import season_manager
from tests.mock_build import make_request, weapon

_SEASON = season_manager.get_active_season()
_SKILLS = _get_skills_data(_SEASON)

ALL = ("physical", "fire", "cold", "lightning", "erosion")


# ── Direct calculate_offense() helpers (mirrors tests/test_group1_offense.py) ────────────────────────
def _source(**stats):
    s = BuildSource()
    for k, v in stats.items():
        s.add(k, v)
    return s


def _flat_attack_source(**extra):
    """Attack source with 10-10 weapon flat in every damage type so every type is in calc_types."""
    s = _source(weapon_attack_speed=1.0, **extra)
    for t in ALL:
        s.add(f"{t}_dmg_gear_flat_min", 10.0)
        s.add(f"{t}_dmg_gear_flat_max", 10.0)
    return s


def _skill(tags=("attack",), intrinsic_convert=None):
    return ResolvedSkill(
        skill_id="t", name="T", tags=list(tags), max_level=1,
        hit_forms_by_level={1: [SkillHitForm(name="H", effectiveness_pct=100.0,
                                             form_type="additive", proc_stat_key=None)]},
        supported=True, base_steep_strike_chance=0.0, is_spell=False,
        base_dmg_by_level={}, base_cast_time=1.0, added_dmg_effectiveness=1.0, main_stat=[],
        intrinsic_convert=intrinsic_convert or {},
    )


# ── 1. Resolver registration + per-level effectiveness ───────────────────────────────────────────────
class TestResolverRegistration:
    def test_registered(self):
        assert "thunder_spike" in _REGISTRY

    def test_lv1_lv20_effectiveness(self):
        resolved = resolve_skill(_SKILLS["thunder_spike"])
        assert resolved.supported is True
        assert resolved.hit_forms_by_level[1][0].effectiveness_pct == pytest.approx(205.0)
        assert resolved.hit_forms_by_level[20][0].effectiveness_pct == pytest.approx(277.0)

    def test_intrinsic_conversion_declared(self):
        resolved = resolve_skill(_SKILLS["thunder_spike"])
        assert resolved.intrinsic_convert == {"physical": {"lightning": 1.0}}

    def test_shadow_strike_tag_present(self):
        resolved = resolve_skill(_SKILLS["thunder_spike"])
        assert "shadow strike" in {t.lower() for t in resolved.tags}


# ── 2. _shadow_multiplier formula (direct unit tests of the delivery model) ──────────────────────────
class TestShadowMultiplierFormula:
    def test_f0_is_one_regardless_of_additional(self):
        assert _shadow_multiplier(0, 0.0) == pytest.approx(1.0)
        assert _shadow_multiplier(0, 0.50) == pytest.approx(1.0)
        assert _shadow_multiplier(0, -0.20) == pytest.approx(1.0)

    def test_n1_no_additional_doubles(self):
        # f(1) = 1 (player) + 1 (first shadow, full) = 2.0 exactly.
        assert _shadow_multiplier(1, 0.0) == pytest.approx(2.0)

    def test_n3_falloff_arithmetic(self):
        # f(3) = 1 + (1 + 0.30*(3-1)) = 1 + 1.6 = 2.6 (first shadow 100%, 2 more @ 30% each = 60%).
        assert _shadow_multiplier(3, 0.0) == pytest.approx(2.6)

    def test_shadow_dmg_additional_scales_only_shadow_portion(self):
        # f(1, 0.15) = 1 + 1*(1.15) = 2.15 -- the leading "1 +" (player hit) is untouched by additional.
        assert _shadow_multiplier(1, 0.15) == pytest.approx(2.15)
        # f(3, 0.20) = 1 + 1.6*1.20 = 2.92
        assert _shadow_multiplier(3, 0.20) == pytest.approx(2.92)

    def test_negative_additional(self):
        # A craft-base "-5% additional Shadow Damage" roll: f(2, -0.05) = 1 + (1+0.30*1)*(0.95) = 2.235
        assert _shadow_multiplier(2, -0.05) == pytest.approx(2.235)


class TestDespisedShadowEVMix:
    """shadow_mult = (1-p)*f(N) + p*f(N+k), p=0.33, k=3 (corroded 4)."""

    def test_ev_mix_matches_hand_derivation(self):
        p, k, n, add = 0.33, 3, 1, 0.15
        f_base = _shadow_multiplier(n, add)
        f_bonus = _shadow_multiplier(n + k, add)
        expected = (1.0 - p) * f_base + p * f_bonus
        # Hand-derived: f(1,.15)=2.15, f(4,.15)=1+(1+.9)*1.15=3.185 -> 0.67*2.15+0.33*3.185=2.49155
        assert f_base == pytest.approx(2.15)
        assert f_bonus == pytest.approx(3.185)
        assert expected == pytest.approx(2.49155)

    def test_corroded_k4(self):
        p, k, n, add = 0.33, 4, 1, 0.15
        f_base = _shadow_multiplier(n, add)
        f_bonus = _shadow_multiplier(n + k, add)
        expected = (1.0 - p) * f_base + p * f_bonus
        # f(5, .15) = 1 + (1 + 0.30*4)*1.15 = 1 + 2.2*1.15 = 3.53
        assert f_bonus == pytest.approx(3.53)
        assert expected == pytest.approx(0.67 * 2.15 + 0.33 * 3.53)

    def test_p_zero_degenerates_to_f_n(self):
        # No chance source active -> the EV mix must collapse exactly to the base f(N).
        p, n, add = 0.0, 2, 0.10
        f_base = _shadow_multiplier(n, add)
        expected = (1.0 - p) * f_base + p * _shadow_multiplier(n + 3, add)
        assert expected == pytest.approx(f_base)

    def test_n_base_zero_chance_only_hits_f0_branch(self):
        # Despised Shadow alone (no Haunt/Frantic Shadow) -> N_base=0, so f(N_base)=f(0)=1.0 exactly; the
        # EV mix must still correctly weight the p-branch off that f(0)=1.0 baseline, not skip/short-circuit.
        r = calculate_offense(_flat_attack_source(shadow_dmg_additional=0.15), _skill(), 1,
                              shadow={"count": 0, "chance_pct": 0.33, "chance_quantity": 3})
        expected = 0.67 * _shadow_multiplier(0, 0.15) + 0.33 * _shadow_multiplier(3, 0.15)
        assert _shadow_multiplier(0, 0.15) == pytest.approx(1.0)
        assert r.shadow_mult == pytest.approx(expected)
        assert r.shadow_mult == pytest.approx(1.6072)


# ── 3. calculate_offense(shadow=) direct wiring ───────────────────────────────────────────────────────
class TestCalculateOffenseShadowKwarg:
    def test_shadow_none_byte_identical_to_no_shadow(self):
        base = calculate_offense(_flat_attack_source(), _skill(), 1)
        explicit_none = calculate_offense(_flat_attack_source(), _skill(), 1, shadow=None)
        assert explicit_none.total_dps == pytest.approx(base.total_dps)
        assert base.shadow_mult == pytest.approx(1.0)
        assert base.shadow_count == 0
        # shadow_hits_per_sec is the linear N + p*k hit-rate primitive (distinct from the nonlinear
        # shadow_mult damage EV mix) -- with no shadow model attached at all, it must be exactly zero.
        assert base.shadow_hits_per_sec == pytest.approx(0.0)
        assert explicit_none.shadow_hits_per_sec == pytest.approx(0.0)

    def test_shadow_hits_per_sec_zero_on_non_shadow_strike_skill_end_to_end(self):
        # A real non-Shadow-Strike skill (server.engine_stats path, shadow=None wiring from
        # engine.compute) must report shadow_hits_per_sec == 0.0, mirroring the shadow_mult neutrality
        # already covered by TestZeroShadowsControl.
        o = engine_stats(EngineStatsRequest(**make_request("chain_lightning", 14, gear=DUAL_WEAPONS)))
        d = (o if isinstance(o, dict) else o.model_dump())["offense"]
        assert d["shadow_hits_per_sec"] == pytest.approx(0.0)

    def test_n0_shadow_dict_is_still_neutral(self):
        base = calculate_offense(_flat_attack_source(), _skill(), 1)
        n0 = calculate_offense(_flat_attack_source(), _skill(), 1,
                                shadow={"count": 0, "chance_pct": 0.0, "chance_quantity": 0.0})
        assert n0.total_dps == pytest.approx(base.total_dps)
        assert n0.shadow_mult == pytest.approx(1.0)

    def test_n1_exactly_doubles_dps(self):
        base = calculate_offense(_flat_attack_source(), _skill(), 1)
        one = calculate_offense(_flat_attack_source(), _skill(), 1,
                                shadow={"count": 1, "chance_pct": 0.0, "chance_quantity": 0.0})
        assert one.shadow_mult == pytest.approx(2.0)
        assert one.total_dps == pytest.approx(base.total_dps * 2.0)

    def test_n3_with_additional_matches_formula(self):
        base = calculate_offense(_flat_attack_source(), _skill(), 1)
        r = calculate_offense(_flat_attack_source(shadow_dmg_additional=0.20), _skill(), 1,
                              shadow={"count": 3, "chance_pct": 0.0, "chance_quantity": 0.0})
        assert r.shadow_mult == pytest.approx(2.92)
        assert r.shadow_dmg_additional == pytest.approx(0.20)
        assert r.total_dps == pytest.approx(base.total_dps * 2.92)

    def test_chance_ev_mix_matches_spec_worked_example(self):
        r = calculate_offense(_flat_attack_source(shadow_dmg_additional=0.15), _skill(), 1,
                              shadow={"count": 1, "chance_pct": 0.33, "chance_quantity": 3})
        assert r.shadow_mult == pytest.approx(2.49155)
        assert r.shadow_count == 1
        assert r.shadow_chance_pct == pytest.approx(0.33)
        assert r.shadow_chance_quantity == pytest.approx(3.0)
        # shadow_hits_per_sec is the LINEAR chance-mix expectation N + p*k (deliberately NOT the same
        # quantity as the nonlinear shadow_mult damage EV mix above) -- derived independently from spec,
        # using the engine's own reported cast/attack rate (skills_per_second), not a re-read of the
        # implementation's internal `sps` variable.
        sps = r.skills_per_second
        expected_shadow_hits_per_sec = (1 + 0.33 * 3) * sps
        assert r.shadow_hits_per_sec == pytest.approx(expected_shadow_hits_per_sec)

    def test_chance_pct_zero_degenerates(self):
        plain = calculate_offense(_flat_attack_source(), _skill(), 1,
                                  shadow={"count": 2, "chance_pct": 0.0, "chance_quantity": 3})
        withshadow = calculate_offense(_flat_attack_source(), _skill(), 1,
                                       shadow={"count": 2, "chance_pct": 0.0, "chance_quantity": 0.0})
        assert plain.shadow_mult == pytest.approx(withshadow.shadow_mult)
        assert plain.shadow_mult == pytest.approx(_shadow_multiplier(2, 0.0))


class TestShadowHitsPerSecRate:
    """shadow_hits_per_sec (offense.py ~2202-2221): the LINEAR chance-mix hit-rate expectation
    N + p*k, times the skill's own cast/attack rate. Deliberately distinct from shadow_mult, which
    folds the nonlinear _shadow_multiplier falloff formula for the DAMAGE EV mix. Covers the
    chance-only and flat-count-only edges the worked example (N=1, p=0.33, k=3) doesn't isolate."""

    def test_chance_only_no_flat_count(self):
        # count=0, chance_pct=0.33, chance_quantity=3 -> N + p*k = 0 + 0.33*3 = 0.99 exactly.
        r = calculate_offense(_flat_attack_source(), _skill(), 1,
                              shadow={"count": 0, "chance_pct": 0.33, "chance_quantity": 3})
        sps = r.skills_per_second
        assert r.shadow_hits_per_sec == pytest.approx(0.99 * sps)

    def test_flat_count_only_no_chance(self):
        # count=2, no chance source at all -> N + p*k collapses to the flat count: 2 exactly.
        r = calculate_offense(_flat_attack_source(), _skill(), 1,
                              shadow={"count": 2, "chance_pct": 0.0, "chance_quantity": 0.0})
        sps = r.skills_per_second
        assert r.shadow_hits_per_sec == pytest.approx(2.0 * sps)


# ── 4. shadow_dmg_additional scoping (regression guard for the pool-leak bug) ────────────────────────
class TestShadowDmgAdditionalScoping:
    def test_not_shadow_skill_untouched_by_shadow_dmg_additional(self):
        # A non-Shadow-Strike skill (shadow=None) must be COMPLETELY unaffected by shadow_dmg_additional,
        # even though the stat is present on the source -- it must not leak into the generic hit-additional
        # pool (buglog: shadow-dmg-additional-generic-pool-leak).
        base = calculate_offense(_flat_attack_source(), _skill(), 1, shadow=None)
        with_stat = calculate_offense(_flat_attack_source(shadow_dmg_additional=0.50), _skill(), 1, shadow=None)
        assert with_stat.total_dps == pytest.approx(base.total_dps)

    def test_shadow_skill_only_shadow_portion_scaled(self):
        # On an ACTIVE shadow (N=1), shadow_dmg_additional must scale ONLY the shadow portion of the
        # delivery multiplier (the leading "1 +" player-hit term is untouched) -- assert the EXACT
        # multiplier, not just "bigger".
        r = calculate_offense(_flat_attack_source(shadow_dmg_additional=0.50), _skill(), 1,
                              shadow={"count": 1, "chance_pct": 0.0, "chance_quantity": 0.0})
        # f(1, 0.50) = 1 + 1*(1.50) = 2.50 (NOT 1*(1+0.5) + 1*(1+0.5) = 3.0, which would be the bug's
        # "generic pool" shape of scaling the player hit too).
        assert r.shadow_mult == pytest.approx(2.50)


# ── 5. Independent multiplication with other delivery multipliers ────────────────────────────────────
class TestIndependentMultiplication:
    def test_shadow_and_multistrike_multiply_independently(self):
        base = calculate_offense(_flat_attack_source(), _skill(), 1)
        shadow_only = calculate_offense(_flat_attack_source(), _skill(), 1,
                                        shadow={"count": 1, "chance_pct": 0.0, "chance_quantity": 0.0})
        ms_only = calculate_offense(_flat_attack_source(multistrike_chance=0.5), _skill(), 1)
        both = calculate_offense(_flat_attack_source(multistrike_chance=0.5), _skill(), 1,
                                 shadow={"count": 1, "chance_pct": 0.0, "chance_quantity": 0.0})
        shadow_factor = shadow_only.total_dps / base.total_dps
        ms_factor = ms_only.total_dps / base.total_dps
        assert both.total_dps == pytest.approx(base.total_dps * shadow_factor * ms_factor, rel=1e-9)
        assert both.shadow_mult == pytest.approx(shadow_only.shadow_mult)
        assert both.multistrike_mult == pytest.approx(ms_only.multistrike_mult)

    def test_shadow_and_tangle_multiply_independently(self):
        base = calculate_offense(_flat_attack_source(), _skill(), 1)
        shadow_only = calculate_offense(_flat_attack_source(), _skill(), 1,
                                        shadow={"count": 1, "chance_pct": 0.0, "chance_quantity": 0.0})
        tangle_only = calculate_offense(_flat_attack_source(), _skill(), 1,
                                        tangle={"count": 3, "placeable": 3, "inactivated": 0})
        both = calculate_offense(_flat_attack_source(), _skill(), 1,
                                 shadow={"count": 1, "chance_pct": 0.0, "chance_quantity": 0.0},
                                 tangle={"count": 3, "placeable": 3, "inactivated": 0})
        shadow_factor = shadow_only.total_dps / base.total_dps
        tangle_factor = tangle_only.total_dps / base.total_dps
        assert both.total_dps == pytest.approx(base.total_dps * shadow_factor * tangle_factor, rel=1e-9)
        assert both.shadow_mult == pytest.approx(shadow_only.shadow_mult)
        assert both.tangle_mult == pytest.approx(tangle_only.tangle_mult)


# ── 6. Intrinsic 100% Physical -> Lightning conversion ────────────────────────────────────────────────
class TestIntrinsicConversion:
    def test_damage_by_type_pure_lightning(self):
        skill = _skill(intrinsic_convert={"physical": {"lightning": 1.0}})
        # A PURE physical-only source (like a real weapon) -- not _flat_attack_source, which seeds every
        # damage type so the test can independently spot elemental leaks elsewhere.
        physical_only = _source(weapon_attack_speed=1.0, physical_dmg_gear_flat_min=10.0,
                                physical_dmg_gear_flat_max=10.0)
        r = calculate_offense(physical_only, skill, 1)
        form = r.hit_forms[0]
        assert form.damage_by_type.get("physical", 0.0) == pytest.approx(0.0)
        assert form.damage_by_type.get("lightning", 0.0) > 0.0
        # Nothing else should be leaking non-physical, non-lightning types in from a pure-physical source.
        for dt in ("fire", "cold", "erosion"):
            assert form.damage_by_type.get(dt, 0.0) == pytest.approx(0.0)


# ── End-to-end (server.engine_stats), real gear/support/talent data ──────────────────────────────────
DUAL_WEAPONS = [
    weapon("weapon1", "Test Sword", 200, 350, 1.3, 600),
    weapon("weapon2", "Test Dagger", 300, 500, 1.1, 600),
]


def _off(**kw):
    kw.setdefault("gear", DUAL_WEAPONS)
    r = engine_stats(EngineStatsRequest(**make_request("thunder_spike", 20, **kw)))
    return (r if isinstance(r, dict) else r.model_dump())


def _sup(item_id, stype, level=1, rank=1, slot=1):
    return {"item_id": item_id, "skill_type": stype, "rank": rank, "level": level, "slot": slot}


def _ts_expected_stacks(sps: float) -> float:
    """The Phase 2 (2026-07-15) independent-stacking window formula for Thunder Spike's inherent
    on-hit Numbed: E[stacks] = D*sps / ceil(I*sps), I=1.0s (skill's own tooltip inflict interval),
    D=2.0s (master_glossary 762 default Numbed duration). Mirrors engine.compute.py ~1061 exactly --
    re-derived here from the same formula, not copied from an implementation import, so this is still
    an independent check of the WIRING (does the engine feed it the right sps?), not the formula's
    own math (covered directly by TestNumbedStacksFormulaPhase2 below)."""
    return (2.0 * sps) / math.ceil(1.0 * sps)


class TestZeroShadowsControl:
    def test_no_shadow_source_is_plain_attack(self):
        o = _off()["offense"]
        assert o["shadow_count"] == 0
        assert o["shadow_mult"] == pytest.approx(1.0)
        # total_dps must equal the raw hit-forms sum * every OTHER delivery multiplier (i.e. shadow_mult
        # folds to a no-op) -- cross-check against the direct-call control.
        base = calculate_offense(_flat_attack_source(), _skill(), 1)
        # (Not a numeric equality across the two paths -- just confirms the field is neutral/absent-shaped.)
        assert o["shadow_chance_pct"] == pytest.approx(0.0)
        assert o["shadow_dmg_additional"] == pytest.approx(0.0)


class TestNumbedAutoSet:
    """Thunder Spike auto-derives TWO independent conditions from its intrinsic True-Body-Numbed line
    (engine.compute.py ~1004-1071, moved from server.py's old `_intrinsic_numbed_effects` in the Phase 2
    change below): enemy_numbed (set_true) and numbed_stacks (max-floor, now FRACTIONAL). Each is gated
    by its OWN key in manual_keys, so they are overridable independently.

    Phase 2 (2026-07-15, owner-measurement-confirmed): the numbed_stacks floor changed from a flat 1.0
    to the independent-stacking window formula E[stacks] = D*sps / ceil(I*sps) (I=1s inflict interval,
    D=2s glossary-762 Numbed duration), using the slot's own compute_skill_rates sps (same rate the
    offense pass uses, including any Activation-Medium trigger override). This reconciles all three
    owner RECOUNT runs (solo, +Haunt, +Haunt+slate) to within 0.25% -- see data/verification/
    thunder-spike.json and .wolf/memory.md "Part B v3, FINAL" / "N-independence + direct-proof test".
    The DUAL_WEAPONS build below (1.3aps + 1.1aps dual-wield, no AM trigger) computes sps=2.64, so the
    expected stacks are 2.0*2.64/ceil(2.64) = 2.0*2.64/3 = 1.76 (not the old flat 1.0) -- expectations
    below are DERIVED from the build's own reported skills_per_second, not a hardcoded magic number, so
    they stay correct if the test's dual-wield weapon stats ever change."""

    def test_auto_sets_both_enemy_numbed_and_stacks_floor(self):
        r = _off()
        auto = r.get("auto_conditions") or {}
        sps = r["offense"]["skills_per_second"]
        expected_stacks = _ts_expected_stacks(sps)
        assert auto.get("enemy_numbed", {}).get("value") is True
        assert auto.get("numbed_stacks", {}).get("value", 0.0) == pytest.approx(expected_stacks)
        # numbed_lightning_taken (+5%/stack) is an enemy-damage-taken multiplier -- only visible post
        # target-mitigation (total_dps_vs_target), not the raw outgoing total_dps.
        floored = r["stats"].get("numbed_lightning_taken", {}).get("total", 0.0)
        assert floored == pytest.approx(0.05 * expected_stacks)   # expected_stacks * 5%/stack
        assert expected_stacks == pytest.approx(1.76)             # pinned to the dual-wield sps=2.64 case

    def test_numbed_stacks_override_removes_the_floor(self):
        # Overriding numbed_stacks (its OWN key) explicitly suppresses the auto max-floor.
        r = _off(extra_conditions={"numbed_stacks": 0})
        auto = r.get("auto_conditions") or {}
        assert auto.get("numbed_stacks", {}).get("value") is None or auto["numbed_stacks"]["value"] == 0.0
        assert r["stats"].get("numbed_lightning_taken", {}).get("total", 0.0) == pytest.approx(0.0)
        base = _off()["offense"]["total_dps_vs_target"]
        assert r["offense"]["total_dps_vs_target"] < base

    def test_enemy_numbed_override_is_independent_of_stacks_floor(self):
        # Overriding enemy_numbed alone (its OWN key) must NOT touch the separate numbed_stacks floor --
        # each auto-derived condition is gated on its own manual_keys membership. Phase 2 (2026-07-15):
        # expected stacks derived from the build's own sps (2.64 -> 1.76), same as
        # test_auto_sets_both_enemy_numbed_and_stacks_floor above -- overriding enemy_numbed must not
        # change it.
        r = _off(extra_conditions={"enemy_numbed": False})
        auto = r.get("auto_conditions") or {}
        sps = r["offense"]["skills_per_second"]
        expected_stacks = _ts_expected_stacks(sps)
        assert auto.get("enemy_numbed", {}).get("value") is not True
        assert auto.get("numbed_stacks", {}).get("value", 0.0) == pytest.approx(expected_stacks)
        assert r["stats"].get("numbed_lightning_taken", {}).get("total", 0.0) == pytest.approx(0.05 * expected_stacks)

    def test_user_can_raise_stacks_explicitly(self):
        low = _off(extra_conditions={"numbed_stacks": 1})
        high = _off(extra_conditions={"numbed_stacks": 10})
        assert high["offense"]["total_dps_vs_target"] > low["offense"]["total_dps_vs_target"]


class TestNumbedStacksFormulaPhase2:
    """Independent coverage of the Phase 2 (2026-07-15) `numbed_stacks` auto-derive formula
    E[stacks](sps) = D*sps / ceil(I*sps), I=1.0s, D=2.0s (engine.compute.py ~1004-1071), wired from
    the SAME compute_skill_rates sps the offense pass uses (including AM trigger overrides peeked via
    a scratch-source apply_slot_effects run). Formula and measurement basis: .wolf/memory.md 2026-07-15
    "Part B v3, FINAL" / "N-independence + direct-proof test" -- owner-confirmed via RECOUNT
    reconciliation of solo/+Haunt/+Haunt+slate runs to within 0.25%, and independently via a
    zero-shadow Rhythm cadence test (permanent 2 stacks at 1.0s/0.5s intervals, 1<->2 alternation at
    0.7s). See also data/verification/thunder-spike.json."""

    # ── (a) Solo manual 1.5 attacks/sec: the exact RECOUNT reconciliation pin ────────────────────────
    def test_solo_manual_1_5aps_stacks_exactly_1_5(self):
        # Single weapon, no dual wield -> weapon_attack_speed IS skills_per_second (no AM trigger).
        solo_weapon = [weapon("weapon1", "Solo Blade", 100, 150, 1.5, 0)]
        r = _off(gear=solo_weapon, dual_wield=False)
        assert r["offense"]["skills_per_second"] == pytest.approx(1.5)
        auto = r.get("auto_conditions") or {}
        assert auto.get("numbed_stacks", {}).get("value") == pytest.approx(1.5)

    def test_solo_manual_1_5aps_vs_target_matches_recount_reconciliation_pin(self):
        # Reconstructs the OWNER'S real RECOUNT verification build (data/verification/thunder-spike.json
        # "setup"): white "Unforgotten Long Blade" (154-154 Physical implicit, 1.5 APS, 500 crit rating),
        # no other gear/talents, character level 85, target Lv85 training dummy (the make_request
        # default). The build's hero trait (Erika, Lightning Shadow tier 1) is the source of its
        # +18% additional Numbed Effect (data/seasons/SS12/_hero_traits.json:2718) -- injected here as a
        # bare `numbed_effect_additional` character contribution (the numeric EFFECT of the trait line,
        # not a re-exercise of the hero-trait resolver code path, which is covered elsewhere) since this
        # test's job is the numbed_stacks WIRING, not hero-trait resolution.
        #
        # Sanity anchor: forcing numbed_stacks=1 (the OLD flat-1 model) on this exact build reproduces
        # the engine-agent's recorded flat-1 comparison value (340.34, data/verification/
        # thunder-spike.json "notes") almost exactly -- confirming this reconstruction faithfully mirrors
        # the real verified build before checking the Phase 2 auto-derived value.
        weapon_gear = [weapon("weapon1", "Unforgotten Long Blade", 154, 154, 1.5, 500)]

        def _build(char_level=85, extra_conditions=None):
            req = make_request("thunder_spike", 20, gear=weapon_gear, dual_wield=False,
                               char_level=char_level, extra_conditions=extra_conditions)
            req["character"] = req["character"] + [
                {"stat": "numbed_effect_additional", "amount": 0.18, "label": "Lightning Shadow",
                 "text": "Erika Lightning Shadow tier 1: +18% additional Numbed Effect"},
            ]
            return req

        flat1 = engine_stats(EngineStatsRequest(**_build(extra_conditions={"numbed_stacks": 1})))
        d_flat1 = flat1 if isinstance(flat1, dict) else flat1.model_dump()
        assert d_flat1["offense"]["total_dps_vs_target"] == pytest.approx(340.34, abs=0.05)

        r = engine_stats(EngineStatsRequest(**_build()))
        d = r if isinstance(r, dict) else r.model_dump()
        assert d["offense"]["skills_per_second"] == pytest.approx(1.5)
        auto = d.get("auto_conditions") or {}
        assert auto.get("numbed_stacks", {}).get("value") == pytest.approx(1.5)
        # The reconciliation pin: predicted 349.82 (.wolf/memory.md RUN A, +0.23% vs the measured 349
        # RECOUNT average) -- allow a small tolerance around the hand-derived rescaling.
        assert d["offense"]["total_dps_vs_target"] == pytest.approx(349.82, abs=0.5)

    # ── (b) AM-triggered cadences: both formula cases from the owner's Rhythm discriminating test ─────
    def test_am_trigger_interval_0_5_gives_stacks_2(self):
        # trigger_interval=0.5 -> cast rate 2.0/s -> E[stacks] = 2.0*2.0/ceil(2.0) = 2.0 (forced 2/s,
        # matches the owner's "still 100% uptime" observation).
        rhythm = {"slot": 1, "item_id": "activation_medium_rhythm", "level": 1, "enabled": True,
                  "specific_rolls": {"trigger_interval": 0.5}, "specific_roll_tiers": {"trigger_interval": 1}}
        r = _off(attached_supports=[rhythm])
        assert r["offense"]["skills_per_second"] == pytest.approx(2.0)
        auto = r.get("auto_conditions") or {}
        assert auto.get("numbed_stacks", {}).get("value") == pytest.approx(2.0)

    def test_am_trigger_interval_1_0_gives_stacks_2(self):
        # trigger_interval=1.0 -> cast rate 1.0/s -> E[stacks] = 2.0*1.0/ceil(1.0) = 2.0 (Rhythm 1.0s,
        # matches the owner's "permanently 2 Numbed stacks" observation).
        rhythm = {"slot": 1, "item_id": "activation_medium_rhythm", "level": 1, "enabled": True,
                  "specific_rolls": {"trigger_interval": 1.0}, "specific_roll_tiers": {"trigger_interval": 1}}
        r = _off(attached_supports=[rhythm])
        assert r["offense"]["skills_per_second"] == pytest.approx(1.0)
        auto = r.get("auto_conditions") or {}
        assert auto.get("numbed_stacks", {}).get("value") == pytest.approx(2.0)

    # ── (c) A cadence giving a genuinely fractional (non-1.0/1.5/2.0) expectation ──────────────────────
    def test_am_trigger_interval_0_7_gives_fractional_stacks(self):
        # trigger_interval=0.7 -> cast rate 1/0.7 = 1.42857.../s (NOT an integer multiple of 1s) ->
        # E[stacks] = 2*sps/ceil(sps) = 2*(10/7)/2 = 10/7 = 1.428571... -- the owner's Rhythm 0.7s
        # discriminating test (.wolf/memory.md "Part B v3, FINAL" fit table) observed exactly this
        # non-integer alternation shape (bounces 1<->2, not a constant).
        rhythm = {"slot": 1, "item_id": "activation_medium_rhythm", "level": 1, "enabled": True,
                  "specific_rolls": {"trigger_interval": 0.7}, "specific_roll_tiers": {"trigger_interval": 1}}
        r = _off(attached_supports=[rhythm])
        sps = r["offense"]["skills_per_second"]
        assert sps == pytest.approx(1.0 / 0.7)
        auto = r.get("auto_conditions") or {}
        assert auto.get("numbed_stacks", {}).get("value") == pytest.approx(10.0 / 7.0)
        assert auto.get("numbed_stacks", {}).get("value") == pytest.approx(_ts_expected_stacks(sps))
        # Not one of the "clean" cadence values (1.0/1.5/2.0) -- confirms this is a genuine fraction.
        assert auto.get("numbed_stacks", {}).get("value") not in (pytest.approx(1.0), pytest.approx(2.0))

    # ── (d) A manual numbed_stacks override still wins over the auto-derive, even at high sps ─────────
    def test_manual_override_skips_auto_derive_even_at_high_sps(self):
        # A high-sps AM trigger would otherwise auto-derive close to the 2.0 structural cap -- a manual
        # numbed_stacks=5 (its OWN key, in manual_cond_keys) must skip the auto-derive branch entirely
        # (engine.compute._apply_cond_effects: `if e.condition_key in manual_keys: continue`), not get
        # max()'d against the formula's output.
        rhythm = {"slot": 1, "item_id": "activation_medium_rhythm", "level": 1, "enabled": True,
                  "specific_rolls": {"trigger_interval": 0.5}, "specific_roll_tiers": {"trigger_interval": 1}}
        r = _off(attached_supports=[rhythm], extra_conditions={"numbed_stacks": 5})
        assert r["offense"]["skills_per_second"] == pytest.approx(2.0)   # AM trigger did engage
        auto = r.get("auto_conditions") or {}
        # The auto-derive branch never ran for this key -- no auto_conditions entry (or a None/falsy one).
        assert auto.get("numbed_stacks", {}).get("value") in (None, 0.0)
        assert r["stats"].get("numbed_lightning_taken", {}).get("total", 0.0) == pytest.approx(0.25)  # 5 * 5%

    # ── (e) The formula never exceeds the structural cap of 2.0, at extreme sps values ─────────────────
    def test_formula_never_exceeds_2_at_extreme_sps(self):
        # Pure math check of the closed form itself (D/s <= D/I = 2 always, since ceil(I*sps) >= I*sps):
        # covers sub-1/s, super-1/s, and near the engine's practical ~30/s tick-rate ceiling.
        for sps in (0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0, 29.0, 29.9):
            e = _ts_expected_stacks(sps)
            assert 0.0 < e <= 2.0 + 1e-9, f"sps={sps} produced E[stacks]={e} > 2.0"

    def test_engine_wired_high_sps_stays_at_or_below_2(self):
        # Confirms the ENGINE (not just the standalone formula) respects the same cap at a high sps
        # reached via ordinary attack-speed stacking (attack_speed_inc), not an AM trigger.
        for inc in (2.0, 6.0, 10.0):
            req = make_request("thunder_spike", 20, gear=DUAL_WEAPONS)
            req["character"] = req["character"] + [
                {"stat": "attack_speed_inc", "amount": inc, "label": "Test", "text": "test attack speed"},
            ]
            r = engine_stats(EngineStatsRequest(**req))
            d = r if isinstance(r, dict) else r.model_dump()
            sps = d["offense"]["skills_per_second"]
            assert sps > 2.0   # confirm the attack-speed stacking actually pushed sps up meaningfully
            auto = d.get("auto_conditions") or {}
            stacks = auto.get("numbed_stacks", {}).get("value", 0.0)
            assert 0.0 < stacks <= 2.0 + 1e-9
            assert stacks == pytest.approx(_ts_expected_stacks(sps))

    # ── (f) A genuinely high-aps build hitting the engine's real 30 Hz tick-rate cap ─────────────────
    def test_engine_extreme_aps_at_tick_cap_stays_at_2(self):
        # Distinct from (e) above (test_engine_wired_high_sps_stays_at_or_below_2, which stacks
        # attack_speed_inc up to 10.0 -> sps ~29): this build pushes a real weapon (10.0 base aps) PLUS
        # heavy attack_speed_inc stacking (+800%) so the reported sps actually SATURATES the engine's
        # global 30 Hz per-caster tick cap (engine.tick.cap_rate) -- the most extreme aps the real engine
        # will ever report, not just "high". The auto-derived numbed_stacks must still read straight off
        # the OUTPUT (auto_conditions), not the formula helper, and stay within the structural cap.
        solo_weapon = [weapon("weapon1", "Extreme Blade", 100, 150, 10.0, 0)]
        req = make_request("thunder_spike", 20, gear=solo_weapon, dual_wield=False)
        req["character"] = req["character"] + [
            {"stat": "attack_speed_inc", "amount": 8.0, "label": "Test", "text": "extreme attack speed"},
        ]
        r = engine_stats(EngineStatsRequest(**req))
        d = r if isinstance(r, dict) else r.model_dump()
        sps = d["offense"]["skills_per_second"]
        assert sps == pytest.approx(30.0)   # confirms the tick cap actually engaged
        auto = d.get("auto_conditions") or {}
        stacks = auto.get("numbed_stacks", {}).get("value", 0.0)
        assert 0.0 < stacks <= 2.0 + 1e-9
        assert stacks == pytest.approx(2.0)

    # ── (g) The epsilon guard: a build whose raw sps lands a hair ABOVE an exact integer ─────────────
    def test_engine_float_noise_at_integer_boundary_respects_epsilon_guard(self):
        # engine.compute.py's numbed_stacks derivation uses ceil(I*sps - 1e-9) (an epsilon guard against
        # float noise landing a hair above an integer breakpoint and flipping ceil() up a full unit --
        # same treatment as the consumed_recently rounding at compute.py ~811). weapon_aps=1.12 combined
        # with attack_speed_inc=5.25 is mathematically 1.12*6.25=7.0 exactly, but float64 multiplication
        # actually lands the real engine's reported sps at 7.000000000000001 (verified: not fabricated --
        # this is genuine IEEE-754 rounding from the engine's own multiply, not an injected value). WITHOUT
        # the epsilon guard, ceil(7.000000000000001)=8 -> E[stacks]=2*7.000000000000001/8=1.75. WITH the
        # guard, ceil(7.000000000000001 - 1e-9)=7 (correctly landing on the intended side of the 7.0
        # breakpoint) -> E[stacks]=2*7.000000000000001/7=2.0000000000000004, i.e. the structural cap.
        #
        # Deliberately does NOT use the module-level _ts_expected_stacks() helper above for the expected
        # value -- that helper has NO epsilon term (by design: it mirrors the formula's math, not the
        # engine's float-noise guard), so at this exact boundary it would itself compute the WRONG
        # (pre-guard) 1.75 answer. This test's own epsilon-aware expected value is the independent check.
        solo_weapon = [weapon("weapon1", "Boundary Blade", 100, 150, 1.12, 0)]
        req = make_request("thunder_spike", 20, gear=solo_weapon, dual_wield=False)
        req["character"] = req["character"] + [
            {"stat": "attack_speed_inc", "amount": 5.25, "label": "Test", "text": "boundary attack speed"},
        ]
        r = engine_stats(EngineStatsRequest(**req))
        d = r if isinstance(r, dict) else r.model_dump()
        sps = d["offense"]["skills_per_second"]
        assert sps > 7.0   # confirms the float-noise overshoot is real, not exactly 7.0
        assert sps == pytest.approx(7.0, abs=1e-9)   # ...but negligibly so (genuine float noise, not a gross error)
        epsilon_aware_expected = (2.0 * sps) / math.ceil(1.0 * sps - 1e-9)
        no_guard_would_give = (2.0 * sps) / math.ceil(1.0 * sps)
        assert epsilon_aware_expected == pytest.approx(2.0)
        assert no_guard_would_give == pytest.approx(1.75)
        auto = d.get("auto_conditions") or {}
        stacks = auto.get("numbed_stacks", {}).get("value", 0.0)
        assert stacks == pytest.approx(epsilon_aware_expected)
        assert stacks != pytest.approx(no_guard_would_give)


class TestNumbedAutoSetSecondarySlot:
    """Regression guard for the 2026-07-15 correctness fix (server.py ~line 1034, review-council finding):
    the intrinsic Numbed auto-derive used to check ONLY `req.main_skill.skill_id` -- Thunder Spike slotted
    as a SECONDARY active skill (main_skill is something else) was still actively casting and inflicting
    Numbed on every hit, but the auto-conditions never fired for it. The fix scans ALL slotted skills in
    `skills_input` (mirroring resolve_curses), gated per-slot on that slot's OWN `enabled` flag."""

    @staticmethod
    def _req(thunder_enabled: bool | None = True, include_thunder: bool = True) -> dict:
        req = make_request("chain_lightning", 14, gear=DUAL_WEAPONS)
        skills = [{"slot": 1, "skill_id": "chain_lightning", "level": 14}]
        if include_thunder:
            entry = {"slot": 2, "skill_id": "thunder_spike", "level": 20}
            if thunder_enabled is not None:
                entry["enabled"] = thunder_enabled
            skills.append(entry)
        req["skills"] = skills
        return req

    def test_secondary_slot_thunder_spike_auto_sets_numbed(self):
        # main_skill=chain_lightning (slot 1), thunder_spike slotted+enabled in slot 2 -> auto-conditions
        # must still fire, since Thunder Spike is actively casting even though it isn't the main skill.
        r = engine_stats(EngineStatsRequest(**self._req()))
        d = r if isinstance(r, dict) else r.model_dump()
        auto = d.get("auto_conditions") or {}
        assert auto.get("enemy_numbed", {}).get("value") is True
        # Exact formula expectation (2026-07-15 correctness-review tightening: was a loose `>= 1.0`) --
        # derived from an INDEPENDENT call of Thunder Spike as the MAIN skill on the exact same
        # gear/condition_state (DUAL_WEAPONS, char_level=90, dual_wield=True, no supports attached to
        # either slot). compute_skill_rates is a pure function of the skill's own resolved rate + `source`
        # (never of which slot number hosts it), so this reproduces the secondary slot's own sps exactly
        # without re-reading the implementation's internal rate. Cross-checked against the already-pinned
        # 1.76 value from TestNumbedAutoSet.test_auto_sets_both_enemy_numbed_and_stacks_floor above (same
        # DUAL_WEAPONS build, sps=2.64).
        thunder_as_main_sps = _off()["offense"]["skills_per_second"]
        expected_stacks = _ts_expected_stacks(thunder_as_main_sps)
        assert expected_stacks == pytest.approx(1.76)
        assert auto.get("numbed_stacks", {}).get("value", 0.0) == pytest.approx(expected_stacks)

    def test_secondary_slot_thunder_spike_disabled_does_not_auto_set(self):
        # Same setup, but the slot-2 Thunder Spike entry is explicitly disabled -> it is NOT casting, so
        # the auto-conditions must NOT fire.
        r = engine_stats(EngineStatsRequest(**self._req(thunder_enabled=False)))
        d = r if isinstance(r, dict) else r.model_dump()
        auto = d.get("auto_conditions") or {}
        assert auto.get("enemy_numbed", {}).get("value") is not True
        assert auto.get("numbed_stacks", {}).get("value", 0.0) < 1.0

    def test_no_thunder_spike_control_does_not_auto_set(self):
        # Control: chain_lightning alone (no Thunder Spike slotted anywhere) -> no auto-set, confirming the
        # scan doesn't spuriously fire on an unrelated build.
        r = engine_stats(EngineStatsRequest(**self._req(include_thunder=False)))
        d = r if isinstance(r, dict) else r.model_dump()
        auto = d.get("auto_conditions") or {}
        assert auto.get("enemy_numbed", {}).get("value") is not True
        assert auto.get("numbed_stacks", {}).get("value", 0.0) < 1.0


class TestRumblingThunder:
    # rank=5 -> the universal "+20% additional damage for the supported skill" line (_RANK_TABLE[5]=0.20,
    # ungated); level=1 -> tier-1 "+(45-48)% additional Lightning Damage" (thunder_spike_true_body_buff-gated).
    _RT = _sup("thunder_spike_rumbling_thunder_noble", "noble_support_skill", level=1, rank=5)

    def test_default_on_applies_lightning_additional(self):
        base = _off()["offense"]["total_dps"]
        with_rt = _off(attached_supports=[self._RT])["offense"]["total_dps"]
        assert with_rt > base

    def test_condition_false_removes_lightning_additional_but_keeps_flat_20pct(self):
        on = _off(attached_supports=[self._RT])["offense"]["total_dps"]
        off_cond = _off(attached_supports=[self._RT],
                        extra_conditions={"thunder_spike_true_body_buff": False})["offense"]["total_dps"]
        base = _off()["offense"]["total_dps"]
        assert off_cond < on          # the gated Lightning-additional line dropped out
        assert off_cond > base        # but the flat "+20% additional damage for the supported skill"
                                       # (Rank line, ungated) still applies


class TestTrembleElectricOverloadIsolation:
    """Regression guard for the item_id scoping fix in engine.support_mapper.map_autoderive_line
    (support_mapper.py ~line 267, buglog 2026-07-15): the electric_overload branch used to match ANY
    support's text containing the bare substring "buff on Critical Strike" -- Thunder Spike: Tremble
    (Noble)'s own intrinsic line ("The supported skill gains a buff on Critical Strike: +(66-71)% Numbed
    Effect for 2 s") contains that exact substring. Socket Tremble alone (NO Electric Overload attached)
    and confirm electric_overload never auto-sets -- the golden fixture always co-attaches Electric
    Overload, so it alone can't catch cross-triggering."""
    _TREMBLE = _sup("thunder_spike_tremble_noble", "noble_support_skill", level=5, rank=5)

    def test_tremble_alone_does_not_auto_set_electric_overload(self):
        r = _off(attached_supports=[self._TREMBLE])
        auto = r.get("auto_conditions") or {}
        assert auto.get("electric_overload", {}).get("value") is not True

    def test_tremble_alone_no_lightning_additional_from_electric_overload_condition(self):
        # Cross-check via the stat itself: without Electric Overload's condition set, the
        # "+15% additional Lightning Damage (Electric Overload buff)" condition-source contribution must
        # be absent (Tremble's own rank/tier lines may still contribute lightning_dmg_additional, so this
        # checks the SOURCE, not the total).
        r = _off(attached_supports=[self._TREMBLE])
        sources = (r["stats"].get("lightning_dmg_additional", {}) or {}).get("sources", [])
        assert not any("Electric Overload" in (s.get("label") or "") for s in sources)


class TestHauntSlotLocal:
    _HAUNT = _sup("haunt", "support_skill", level=1, slot=1)

    def test_plus2_shadows_on_supported_slot(self):
        o = _off(attached_supports=[self._HAUNT])["offense"]
        assert o["shadow_count"] == 2
        assert o["shadow_mult"] == pytest.approx(_shadow_multiplier(2, 0.0))

    def test_haunt_on_other_slot_does_not_leak(self):
        # Haunt attached to slot 2 (a different skill) must NOT grant shadow count to the slot-1 main skill.
        r = engine_stats(EngineStatsRequest(
            slots=[None, None, None, None], gear=DUAL_WEAPONS,
            condition_state={}, skills=[{"slot": 1, "skill_id": "thunder_spike", "level": 20},
                                        {"slot": 2, "skill_id": "thunder_spike", "level": 20}],
            main_skill={"skill_id": "thunder_spike", "level": 20},
            attached_supports=[self._sup_at_slot2()], characterLevel=90))
        d = r if isinstance(r, dict) else r.model_dump()
        main_offense = d["offense"]
        assert main_offense["shadow_count"] == 0

    @staticmethod
    def _sup_at_slot2():
        return _sup("haunt", "support_skill", level=1, slot=2)


class TestRoninTalentShadowQuantity:
    def test_ronin_c6_r2_grants_plus1(self):
        req = make_request("thunder_spike", 20, gear=DUAL_WEAPONS)
        req["slots"] = [{"treeName": "Ronin", "nodeStates": {"ronin_c6_r2": 1}, "coreTalentSelections": {}},
                        None, None, None]
        r = engine_stats(EngineStatsRequest(**req))
        d = r if isinstance(r, dict) else r.model_dump()
        assert d["offense"]["shadow_count"] == 1


class TestGearShadowSources:
    _DESPISED = {"item_name": "Despised Shadow", "unresolved_texts": [
        "33 % chance to gain +3 Shadows when using the Shadow Strike skill",
        "+(14–16) % additional Shadow Damage",
    ]}
    _FRANTIC = {"item_name": "Frantic Shadow", "unresolved_texts": [
        "Shadow Quantity +1",
        "1 % chance to gain +100 % Attack Speed for 1 s when Shadows hit enemies",
    ]}

    def test_despised_shadow_plus_frantic_shadow_matches_derived_ev(self):
        o = _off(gear=DUAL_WEAPONS + [self._DESPISED, self._FRANTIC])["offense"]
        assert o["shadow_count"] == 1
        assert o["shadow_chance_pct"] == pytest.approx(0.33)
        assert o["shadow_chance_quantity"] == pytest.approx(3.0)
        assert o["shadow_dmg_additional"] == pytest.approx(0.15)
        # Independently re-derive the EV mix from the raw formula (not copied from the implementation):
        p, k, n, add = 0.33, 3, 1, 0.15
        expected = (1.0 - p) * _shadow_multiplier(n, add) + p * _shadow_multiplier(n + k, add)
        assert expected == pytest.approx(2.49155)
        assert o["shadow_mult"] == pytest.approx(expected)

    def test_negative_craft_base_roll(self):
        craft = {"item_name": "Craft Claw", "unresolved_texts": [
            "Shadow Quantity +2 -5 % additional Shadow Damage",
        ]}
        o = _off(gear=DUAL_WEAPONS + [craft])["offense"]
        assert o["shadow_count"] == 2
        assert o["shadow_dmg_additional"] == pytest.approx(-0.05)
        assert o["shadow_mult"] == pytest.approx(_shadow_multiplier(2, -0.05))

    def test_pool_leak_regression_on_non_shadow_skill(self):
        # Regression guard for shadow-dmg-additional-generic-pool-leak: the SAME gear attached to a
        # NON-Shadow-Strike main skill must not have its generic additional-damage pool inflated by
        # shadow_dmg_additional.
        gear_with_shadow = DUAL_WEAPONS + [self._DESPISED, self._FRANTIC]
        r_plain = engine_stats(EngineStatsRequest(**make_request("chain_lightning", 14, gear=DUAL_WEAPONS)))
        r_shadow_gear = engine_stats(EngineStatsRequest(**make_request("chain_lightning", 14, gear=gear_with_shadow)))
        d_plain = (r_plain if isinstance(r_plain, dict) else r_plain.model_dump())["offense"]
        d_shadow_gear = (r_shadow_gear if isinstance(r_shadow_gear, dict) else r_shadow_gear.model_dump())["offense"]
        assert d_shadow_gear["total_dps"] == pytest.approx(d_plain["total_dps"])
        assert d_shadow_gear["shadow_count"] == 0
        assert d_shadow_gear["shadow_mult"] == pytest.approx(1.0)

    def test_frantic_shadow_attack_speed_procs_surface_nyi_not_dropped(self):
        # "X% chance to gain +Y% Attack Speed for Z s when Shadows hit enemies" is explicit NYI
        # (owner decision, data/verification/shadow-strike.json) -- it must show up unresolved, never
        # silently applied as if it worked.
        r = _off(gear=DUAL_WEAPONS + [self._FRANTIC])
        statuses = r.get("gear_mod_statuses") or []
        matches = [s for s in statuses if "Shadows hit enemies" in s.get("text", "")]
        assert matches, "expected the Frantic Shadow shadow-hit-proc line to be surfaced in gear_mod_statuses"
        assert any(s.get("resolved") is False for s in matches), \
            "Frantic Shadow's shadow-hit Attack Speed proc must surface as unresolved (NYI), not silently apply"


class TestCraftBaseCompoundRangeVariants:
    """The craft-base "Ultimate Suffix" compound roll ("Shadow Quantity +N (+/-)(A[-B]) % additional Shadow
    Damage", engine.mod_parser.py ~line 488) previously only had coverage for the single-value "-5%"
    branch (test_negative_craft_base_roll above). These drive the RANGE branch, with raw_text strings
    quoted verbatim from data/seasons/SS12/_craft_base_types.json (lines ~24627, ~24654 -- note the en
    dash "–" in the source range, not a hyphen)."""

    def test_plus_30_to_40_pct_range_uses_midpoint(self):
        # data/seasons/SS12/_craft_base_types.json:24627
        craft = {"item_name": "Craft Claw", "unresolved_texts": [
            "Shadow Quantity +2 +(30–40) % additional Shadow Damage",
        ]}
        o = _off(gear=DUAL_WEAPONS + [craft])["offense"]
        assert o["shadow_count"] == 2
        assert o["shadow_dmg_additional"] == pytest.approx(0.35)   # (30+40)/2 / 100
        assert o["shadow_mult"] == pytest.approx(_shadow_multiplier(2, 0.35))

    def test_plus_10_to_15_pct_range_uses_midpoint(self):
        # data/seasons/SS12/_craft_base_types.json:24654
        craft = {"item_name": "Craft Claw", "unresolved_texts": [
            "Shadow Quantity +2 +(10–15) % additional Shadow Damage",
        ]}
        o = _off(gear=DUAL_WEAPONS + [craft])["offense"]
        assert o["shadow_count"] == 2
        assert o["shadow_dmg_additional"] == pytest.approx(0.125)  # (10+15)/2 / 100
        assert o["shadow_mult"] == pytest.approx(_shadow_multiplier(2, 0.125))


class TestChanceQuantityStackingCharacterization:
    """Characterization test (documents current behavior, not a spec assertion): TWO independent gear
    sources each granting shadow_chance_pct / shadow_chance_quantity_flat sum ADDITIVELY
    (engine.compute: `eff.total("shadow_chance_pct")` clamped to [0,1], `eff.total("shadow_chance_quantity_flat")`
    unclamped -- offense.py ~2198-2199). This matches the engine's existing additive_chance convention
    (proc-chance stats sum, they don't compound multiplicatively). Both raw_text lines are quoted verbatim
    from Despised Shadow's real base and corroded rolls (data/seasons/SS12/_legendary_gear.json ~13555,
    ~13631) -- stacked on two SEPARATE synthetic gear slots purely to exercise the aggregator's additive-sum
    path; not a claim that dual-wielding two Despised Shadows is an achievable in-game combo."""

    def test_two_shadow_chance_sources_sum_additively(self):
        item_a = {"item_name": "Despised Shadow", "unresolved_texts": [
            "33 % chance to gain +3 Shadows when using the Shadow Strike skill",
        ]}
        item_b = {"item_name": "Despised Shadow (Corroded)", "unresolved_texts": [
            "33 % chance to gain +4 Shadows when using the Shadow Strike skill",
        ]}
        o = _off(gear=DUAL_WEAPONS + [item_a, item_b])["offense"]
        assert o["shadow_count"] == 0
        assert o["shadow_chance_pct"] == pytest.approx(0.66)        # 0.33 + 0.33, additive
        assert o["shadow_chance_quantity"] == pytest.approx(7.0)    # 3 + 4, additive
        expected = (1.0 - 0.66) * _shadow_multiplier(0, 0.0) + 0.66 * _shadow_multiplier(7, 0.0)
        assert o["shadow_mult"] == pytest.approx(expected)


class TestDespisedShadowUseVsCastGate:
    """Regression guard for the 2026-07-15 USE-vs-CAST fix (buglog id
    despised-shadow-use-vs-cast-overcount; engine.compute._offense_for_slot ~1353-1364): Despised Shadow's
    "chance to gain +K Shadows when USING the Shadow Strike skill" is USE-gated, not CAST-gated -- an
    Activation-Medium/Rhythm-triggered slot fires CASTs, not USEs, so the chance-mix EV must NOT apply
    there. Haunt's flat "+2 Shadow Quantity" grant and Despised Shadow's own "+% additional Shadow Damage"
    line (not a "when using" proc) are unaffected. Same trigger detection the Demolisher block uses
    (eff.total("trigger_interval") > 0 or eff.total("wind_rhythm_base_cooldown") > 0)."""

    _DESPISED = {"item_name": "Despised Shadow", "unresolved_texts": [
        "33 % chance to gain +3 Shadows when using the Shadow Strike skill",
        "+(14–16) % additional Shadow Damage",
    ]}
    _HAUNT = _sup("haunt", "support_skill", level=1, slot=1)
    # Real activation_medium_rhythm support, trigger_interval pinned to 0.5s (tier-1 roll) -> cast rate
    # 1/0.5 = 2.0, confirmed below via skills_per_second (same pattern as
    # test_activation_mediums.test_trigger_interval_overrides_cast_rate_generically).
    _RHYTHM_TRIGGER = {"slot": 1, "item_id": "activation_medium_rhythm", "level": 1, "enabled": True,
                        "specific_rolls": {"trigger_interval": 0.5}, "specific_roll_tiers": {"trigger_interval": 1}}

    def test_am_triggered_zeroes_chance_keeps_flat_and_additional(self):
        o = _off(gear=DUAL_WEAPONS + [self._DESPISED],
                 attached_supports=[self._HAUNT, self._RHYTHM_TRIGGER])["offense"]
        # Confirm the AM trigger actually engaged (real trigger_interval=0.5 -> skills_per_second=2.0).
        assert o["skills_per_second"] == pytest.approx(2.0, abs=1e-6)
        assert o["shadow_chance_pct"] == pytest.approx(0.0)
        assert o["shadow_count"] == 2                                    # Haunt's flat grant, untouched
        # shadow_hits_per_sec = N * sps with NO chance term (0 + 0*3 collapses to just N).
        assert o["shadow_hits_per_sec"] == pytest.approx(2 * o["skills_per_second"])
        assert o["shadow_dmg_additional"] == pytest.approx(0.15)         # Despised Shadow's own line, unaffected
        assert o["shadow_mult"] == pytest.approx(_shadow_multiplier(2, 0.15))
        assert o["shadow_mult"] == pytest.approx(2.495)

    def test_manual_control_without_am_chance_applies(self):
        # Same gear/support set MINUS the AM trigger -- the discriminating control proving the gate is
        # trigger-conditional, not a global regression: the chance-mix must apply normally here.
        o = _off(gear=DUAL_WEAPONS + [self._DESPISED], attached_supports=[self._HAUNT])["offense"]
        assert o["shadow_chance_pct"] == pytest.approx(0.33)
        assert o["shadow_count"] == 2
        p, k, n, add = 0.33, 3, 2, 0.15
        expected_mult = (1.0 - p) * _shadow_multiplier(n, add) + p * _shadow_multiplier(n + k, add)
        assert o["shadow_mult"] == pytest.approx(expected_mult)
        assert o["shadow_hits_per_sec"] == pytest.approx((n + p * k) * o["skills_per_second"])

    def test_chance_only_am_triggered_shadow_mode_inert(self):
        # No flat-count source (no Haunt) -- Despised Shadow's chance alone, AM-triggered: chance is gated
        # to 0 and there's no flat count, so compute.py's "if _shadow_n > 0 or _shadow_chance > 0" guard is
        # False -> shadow=None, byte-identical to a plain (non-Shadow-Strike-active) hit.
        triggered = _off(gear=DUAL_WEAPONS + [self._DESPISED], attached_supports=[self._RHYTHM_TRIGGER])["offense"]
        plain = _off(gear=DUAL_WEAPONS, attached_supports=[self._RHYTHM_TRIGGER])["offense"]
        assert triggered["shadow_count"] == 0
        assert triggered["shadow_chance_pct"] == pytest.approx(0.0)
        assert triggered["shadow_mult"] == pytest.approx(1.0)
        assert triggered["shadow_hits_per_sec"] == pytest.approx(0.0)
        assert triggered["total_dps"] == pytest.approx(plain["total_dps"])


class TestNumbedFloorRatchetRegression:
    """Regression pin for the iteration-lag ratchet bug (buglog id thunder-spike-numbed-floor-ratchet,
    fixed 2026-07-15, compute.py:1117-1138). numbed_stacks used to be fed through _apply_cond_effects's
    persistent max-mode ConditionEffect machinery (condition_state[key] = max(cur_from_last_pass, value)),
    which RATCHETS across engine.compute()'s fixed-point loop iterations: a transient pass-1 sps computed
    BEFORE an iteration-lagged malus enters `source` permanently locks in a too-high floor that a later,
    CORRECT (lower-sps) pass can never bring back down. Concrete trigger (buglog): Aim/Euphoria's
    -16% Attack/Cast Speed malus -- aim_active is only written into condition_state at the END of the pass
    that reads aim_trigger_flag, so the malus is absent from THAT SAME pass's already-completed
    aggregate() call and only lands in the NEXT pass's `source`.

    THIS TEST MUST FAIL against the old max-mode (ratchet) implementation: it would converge on the stale
    pre-malus transient (1.66666...) instead of the correct post-malus converged value (1.4 exactly).
    The fix (direct-assign each pass, never max()'d against the prior pass) is what makes it pass.
    """

    def test_aim_euphoria_iteration_lag_converges_to_post_malus_not_pre_malus_transient(self):
        # Manual verification basis (buglog, owner-confirmed): a single weapon aps=2.5 (no dual wield) +
        # a raw aim_trigger_flag gear contribution (Aim/Euphoria triggered via gear, not a slotted skill).
        # Pre-malus (pass 1, before aim_active has entered `source`): sps=2.5,
        # E[stacks]=2*2.5/ceil(2.5)=1.66666... Post-malus (converged, pass 2+): Aim's -16% Attack Speed
        # lands as an attack_speed_inc=-0.16 addend once aim_active is live in `source`, giving
        # sps=2.5*0.84=2.1, E[stacks]=2*2.1/ceil(2.1)=1.4 exactly.
        aim_gear = {"item_name": "Test Aim Trigger", "contributions": [
            {"stat": "aim_trigger_flag", "display_value": 1.0, "unit": "", "slot": "amulet",
             "item_name": "Test Aim Trigger", "text": "Test Aim Trigger:aim_trigger_flag"},
        ]}
        solo_weapon = [weapon("weapon1", "Aim Test Blade", 100, 150, 2.5, 0)]
        r = _off(gear=solo_weapon + [aim_gear], dual_wield=False)
        d = r["offense"]
        sps = d["skills_per_second"]
        # Confirm the malus actually converged into the reported sps (2.1, not the pre-malus 2.5) -- i.e.
        # aim_active really did engage and settle, not just get read once and dropped.
        assert sps == pytest.approx(2.1, abs=1e-6)
        pre_malus_transient = _ts_expected_stacks(2.5)
        post_malus_converged = _ts_expected_stacks(sps)
        assert pre_malus_transient == pytest.approx(5.0 / 3.0)      # 1.66666...
        assert post_malus_converged == pytest.approx(1.4)
        auto = r.get("auto_conditions") or {}
        stacks = auto.get("numbed_stacks", {}).get("value", 0.0)
        assert stacks == pytest.approx(post_malus_converged)
        assert stacks == pytest.approx(1.4)
        assert stacks != pytest.approx(pre_malus_transient)         # the ratchet-bug failure mode
        # Cross-check via the enemy-damage-taken stat, same pattern as TestNumbedAutoSet above.
        floored = r["stats"].get("numbed_lightning_taken", {}).get("total", 0.0)
        assert floored == pytest.approx(0.05 * post_malus_converged)


class TestHighVoltageFloorStillWorksAfterDirectAssignSplit:
    """Regression guard (2026-07-15, thunder-spike-numbed-floor-ratchet fix, compute.py:1132-1136): the
    Thunder Spike direct-assign change must not have clobbered the GENERIC "inflicts Numbed" auto-derive
    path a non-Thunder-Spike skill uses. High Voltage ("Inflicts Numbed when the supported skill deals Hit
    Lightning Damage", item_id high_voltage) still rides the normal, pass-invariant _apply_cond_effects
    max-mode ConditionEffect (support_mapper.map_autoderive_line) -- a flat floor of numbed_stacks=1.0,
    unaffected by the attached skill's own sps. Also re-read fresh via _fresh_max_effect_value() when a
    Thunder Spike slot happens to ALSO be present (the "OTHER pass-invariant auto floor" the direct-assign
    block maxes against), but here there is no Thunder Spike in the build at all -- pure isolation of the
    generic path."""

    def test_high_voltage_on_lightning_skill_keeps_flat_floor_1(self):
        high_voltage = _sup("high_voltage", "support_skill", level=1, rank=1, slot=1)
        r = engine_stats(EngineStatsRequest(**make_request("chain_lightning", 14, gear=DUAL_WEAPONS,
                                                            attached_supports=[high_voltage])))
        d = r if isinstance(r, dict) else r.model_dump()
        auto = d.get("auto_conditions") or {}
        assert auto.get("enemy_numbed", {}).get("value") is True
        # Flat floor of exactly 1.0 -- NOT the Thunder Spike rate-dependent formula (this build's own sps
        # is well above 1.0, so a rate-dependent floor would read differently; the flat 1.0 confirms this
        # generic path, not an accidental fallthrough into the Thunder Spike direct-assign block).
        assert d["offense"]["skills_per_second"] > 1.0
        assert auto.get("numbed_stacks", {}).get("value", 0.0) == pytest.approx(1.0)
        floored = d["stats"].get("numbed_lightning_taken", {}).get("total", 0.0)
        assert floored == pytest.approx(0.05)   # 1 stack * 5%/stack
