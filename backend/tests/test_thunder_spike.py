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

    def test_chance_pct_zero_degenerates(self):
        plain = calculate_offense(_flat_attack_source(), _skill(), 1,
                                  shadow={"count": 2, "chance_pct": 0.0, "chance_quantity": 3})
        withshadow = calculate_offense(_flat_attack_source(), _skill(), 1,
                                       shadow={"count": 2, "chance_pct": 0.0, "chance_quantity": 0.0})
        assert plain.shadow_mult == pytest.approx(withshadow.shadow_mult)
        assert plain.shadow_mult == pytest.approx(_shadow_multiplier(2, 0.0))


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
    (server.py's `_intrinsic_numbed_effects`): enemy_numbed (set_true) and numbed_stacks (max-floor 1).
    Each is gated by its OWN key in manual_keys, so they are overridable independently."""

    def test_auto_sets_both_enemy_numbed_and_stacks_floor(self):
        r = _off()
        auto = r.get("auto_conditions") or {}
        assert auto.get("enemy_numbed", {}).get("value") is True
        assert auto.get("numbed_stacks", {}).get("value", 0.0) >= 1.0
        # numbed_lightning_taken (+5%/stack) is an enemy-damage-taken multiplier -- only visible post
        # target-mitigation (total_dps_vs_target), not the raw outgoing total_dps.
        floored = r["stats"].get("numbed_lightning_taken", {}).get("total", 0.0)
        assert floored == pytest.approx(0.05)   # 1 stack * 5%/stack

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
        # each auto-derived condition is gated on its own manual_keys membership.
        r = _off(extra_conditions={"enemy_numbed": False})
        auto = r.get("auto_conditions") or {}
        assert auto.get("enemy_numbed", {}).get("value") is not True
        assert auto.get("numbed_stacks", {}).get("value", 0.0) >= 1.0
        assert r["stats"].get("numbed_lightning_taken", {}).get("total", 0.0) == pytest.approx(0.05)

    def test_user_can_raise_stacks_explicitly(self):
        low = _off(extra_conditions={"numbed_stacks": 1})
        high = _off(extra_conditions={"numbed_stacks": 10})
        assert high["offense"]["total_dps_vs_target"] > low["offense"]["total_dps_vs_target"]


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
        assert auto.get("numbed_stacks", {}).get("value", 0.0) >= 1.0

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
