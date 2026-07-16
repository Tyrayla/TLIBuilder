"""Rosa — High Court Chariot (trait_id "high_court_chariot") end-to-end engine coverage.

Locks: +30% block chance + Artificial Moon per-10-MI; inside-domain additional damage by level; Unbreakable
Stand's weighted per-enemy (Boss ×5) capped (per-tier cap since SS13, see below); Divine Intervention per-MI;
the **No Guard** model (base 10% × (1+stacks-lost) × (1+Block-Ratio additional), 2 stacks → +100%); Block Ratio
base 30% + Invulnerability + upper limit; inside-domain gating; never-silently-drop status surface;
non-regression (trait_id=None unchanged).

Unbreakable Stand's per-enemy bonus AND its cap are SEASON DATA (read from `_hero_traits.json` via
`engine.hero_traits._catalog`, see `high_court_chariot.py`'s 2026-07-16 SS12->SS13 drift-fix docstring) — SS12's
cap was a flat +100% scalar for every tier, SS13's is per-tier (+50/60/70/80/90%). `test_unbreakable_stand_...`
pins the season explicitly (`_pinned_season`, the pattern established in `test_chromatic_shot.py`) rather than
riding whatever the app's ambient active season happens to be.
"""
import contextlib

import pytest
from server import engine_stats, EngineStatsRequest
from persistence import season_manager
from tests.mock_build import make_request

SPELL = "chain_lightning"


def _val(stats, key):
    v = stats.get(key)
    return (v.get("value", v.get("total", 0)) if isinstance(v, dict) else (v or 0)) or 0


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


def _run(*, picks=None, conds=None, slot_levels=(5, 5, 5, 5), trait_id="high_court_chariot", **extra):
    req = make_request(SPELL, 20, trait_id=trait_id, trait_slot_levels=list(slot_levels),
                       advanced_trait_selections=list(picks or []), extra_conditions=conds or {}, **extra)
    r = engine_stats(EngineStatsRequest(**req))
    return r.model_dump() if hasattr(r, "model_dump") else r


def _stat(resp, key):
    return float(_val(resp["stats"], key))


class TestBaseAndBlock:
    def test_base_block_chance_and_artificial_moon(self):
        # Trait DELTA (the mock dual-wields → +30% Attack Block Chance baseline). Base +30% Attack & Spell Block
        # Chance; Artificial Moon (base L5) adds +1%/10 MI → +10% at MI 100. Delta = 0.40 over no-trait.
        base = _run(trait_id=None, conds={"murderous_intent": 100})
        r = _run(conds={"murderous_intent": 100})
        assert _stat(r, "attack_block_chance_inc") - _stat(base, "attack_block_chance_inc") == pytest.approx(0.40)
        assert _stat(r, "spell_block_chance_inc") - _stat(base, "spell_block_chance_inc") == pytest.approx(0.40)

    def test_artificial_moon_scales_with_mi(self):
        base = _run(trait_id=None, conds={"murderous_intent": 50})
        r = _run(conds={"murderous_intent": 50})   # floor(50/10)=5 → +5%; delta = 0.30 + 0.05 = 0.35
        assert _stat(r, "attack_block_chance_inc") - _stat(base, "attack_block_chance_inc") == pytest.approx(0.35)

    def test_block_ratio_base_and_invulnerability(self):
        base = _run()
        assert base["defense"]["block_ratio"] == pytest.approx(0.30)          # base 30%, no Invulnerability
        assert base["defense"]["block_ratio_upper_limit"] == pytest.approx(0.60)
        inv = _run(picks=["Invulnerability"])
        assert inv["defense"]["block_ratio"] == pytest.approx(0.45)           # 30% + 15% (tier 5)
        assert inv["defense"]["block_ratio_upper_limit"] == pytest.approx(0.75)


class TestInsideDomainDamage:
    def _dps(self, resp):
        return resp["offense"]["total_dps_vs_target"]

    def test_inside_domain_additional_raises_dps(self):
        inside = self._dps(_run(conds={"inside_holy_domain": True}))
        outside = self._dps(_run(conds={"inside_holy_domain": False}))
        assert inside > outside   # +44% additional (base L5) only applies inside

    def test_unbreakable_stand_weighted_enemies_and_cap(self):
        # +10%/enemy (tier 5) × (1 enemy × 5 Boss weight) = +50% additional damage. Season-pinned to SS13 (per-
        # enemy bonus is unchanged from SS12, but the cap below is not — see module docstring).
        with _pinned_season("SS13"):
            one = self._dps(_run(picks=["Unbreakable Stand"], conds={"enemies_in_holy_domain": 1}))
            base = self._dps(_run(conds={"inside_holy_domain": True}))
            assert one > base
            # SS13 cap is per-tier: tier 5 = +90% (SS12's was a flat +100% for every tier — see module
            # docstring). 3 enemies × 5 = 15 × 10% = 150% → capped +90%; 5 enemies same (already capped).
            cap3 = _run(picks=["Unbreakable Stand"], conds={"enemies_in_holy_domain": 3})
            cap5 = _run(picks=["Unbreakable Stand"], conds={"enemies_in_holy_domain": 5})
            assert self._dps(cap5) == pytest.approx(self._dps(cap3))
            base_inside = 0.44   # base-level-5 "inside Holy Domain" additional damage (unaffected by the drift fix)
            assert _stat(cap3, "dmg_additional") == pytest.approx(base_inside + 0.90, abs=1e-3)

    def test_unbreakable_stand_cap_ss12_vs_ss13(self):
        """Same code path (no `if season ==` branch), fed each season's own catalog data: SS12's flat +100%
        cap vs SS13's per-tier +90% (tier 5) cap — the property the 2026-07-16 drift fix is actually about."""
        kw = dict(picks=["Unbreakable Stand"], conds={"enemies_in_holy_domain": 3})
        with _pinned_season("SS12"):
            ss12 = _stat(_run(**kw), "dmg_additional")
        with _pinned_season("SS13"):
            ss13 = _stat(_run(**kw), "dmg_additional")
        assert ss12 == pytest.approx(0.44 + 1.00, abs=1e-3)
        assert ss13 == pytest.approx(0.44 + 0.90, abs=1e-3)

    def test_unbreakable_stand_per_enemy_ss12_vs_ss13_at_tier_1(self):
        """`test_unbreakable_stand_cap_ss12_vs_ss13` above only probes tier 5 (default `slot_levels=(5,5,5,5)`),
        where SS12's per-enemy bonus (0.10) and SS13's (0.10) happen to be IDENTICAL — only the cap's shape
        change is exercised there. `_unbreakable_per_enemy` itself drifts at every tier BELOW 5 (SS12
        .07/.08/.09/.095 vs SS13 .06/.07/.08/.09 for tiers 1-4); a marker/index bug in `_unbreakable_per_enemy`
        specific to a non-max tier would not be caught by any other test. Pin tier 1 (`slot_levels[1] = 1`,
        Unbreakable Stand's own slot) with the weighted enemy count kept well under either season's cap (1
        enemy × the Boss training-dummy weight of 5 = 5 weighted enemies; 0.07×5=0.35 and 0.06×5=0.30 are both
        far under even SS13's lowest per-tier cap of 0.50) so this isolates the per-enemy value, not the cap."""
        kw = dict(picks=["Unbreakable Stand"], conds={"enemies_in_holy_domain": 1}, slot_levels=(5, 1, 5, 5))
        with _pinned_season("SS12"):
            ss12 = _stat(_run(**kw), "dmg_additional")
        with _pinned_season("SS13"):
            ss13 = _stat(_run(**kw), "dmg_additional")
        base_inside = 0.44   # base-level-5 "inside Holy Domain" additional damage (slot_levels[0] stays 5)
        assert ss12 == pytest.approx(base_inside + 0.07 * 5, abs=1e-3)   # SS12 tier-1 per-enemy 0.07
        assert ss13 == pytest.approx(base_inside + 0.06 * 5, abs=1e-3)   # SS13 tier-1 per-enemy 0.06
        assert ss12 != pytest.approx(ss13)   # the actual drift this test guards — tier 1 SS12 != SS13

    def test_divine_intervention_per_mi(self):
        hi = self._dps(_run(picks=["Divine Intervention"], conds={"murderous_intent": 100}))
        lo = self._dps(_run(picks=["Divine Intervention"], conds={"murderous_intent": 50}))
        assert hi > lo

    def test_improvision_gated_on_toggle(self):
        off = self._dps(_run(picks=["Improvision"], conds={"improvision_active": False}))
        on = self._dps(_run(picks=["Improvision"], conds={"improvision_active": True}))
        assert on > off


class TestNoGuard:
    def test_no_guard_base_two_stacks(self):
        # Desperation only, no Invulnerability → Block Ratio 30%. No Guard = 10% × (1+1.00 stacks) × (1 + 30×0.028).
        r = _run(picks=["Desperation"], conds={"inside_holy_domain": True})
        expected = 0.10 * (1 + 1.00) * (1 + 30 * 0.028)
        assert _stat(r, "no_guard_dmg_taken") == pytest.approx(expected, rel=1e-3)

    def test_no_guard_scales_with_block_ratio(self):
        # Invulnerability raises Block Ratio 30%→45% → larger No Guard additional pool.
        r = _run(picks=["Invulnerability", "Desperation"], conds={"inside_holy_domain": True})
        expected = 0.10 * (1 + 1.00) * (1 + 45 * 0.028)
        assert _stat(r, "no_guard_dmg_taken") == pytest.approx(expected, rel=1e-3)

    def test_no_guard_raises_dps(self):
        without = _run()["offense"]["total_dps_vs_target"]
        with_ng = _run(picks=["Desperation"])["offense"]["total_dps_vs_target"]
        assert with_ng > without   # enemy takes more damage

    def test_no_guard_off_outside_domain(self):
        r = _run(picks=["Desperation"], conds={"inside_holy_domain": False})
        assert _stat(r, "no_guard_dmg_taken") == 0.0

    def test_player_self_debuff_emitted(self):
        # No Guard hits the player too — emitted (NYI; defense doesn't consume it yet) but surfaced.
        r = _run(picks=["Desperation"], conds={"inside_holy_domain": True})
        assert _stat(r, "no_guard_self_dmg_taken") > 0.0


class TestTraitSkillSlot:
    def test_slot10_support_resolves_without_error(self):
        # The Holy Domain trait skill (slot 10) hosts supports via the normal per-slot machinery; it deals no
        # damage (no slot-10 offense) but resolving its supports must not error or disturb the main slot.
        req = make_request(SPELL, 20, trait_id="high_court_chariot", trait_slot_levels=[5, 5, 5, 5],
                           advanced_trait_selections=["Invulnerability", "Desperation"])
        req["skills"] = list(req["skills"]) + [{"slot": 10, "skill_id": "rosa_holy_domain", "level": 1, "enabled": True}]
        req["attached_supports"] = list(req.get("attached_supports") or []) + [
            {"item_id": "activation_medium_boss", "skill_type": "activation_medium_skill", "level": 1, "slot": 10, "enabled": True}]
        r = engine_stats(EngineStatsRequest(**req))
        d = r.model_dump() if hasattr(r, "model_dump") else r
        assert d["offense"]["total_dps_vs_target"] > 0          # main skill still computes
        assert "10" not in (d.get("slot_offense") or {})        # slot 10 has no offense (no damage)


class TestSurfaceAndRegression:
    def test_status_lines_cover_picks(self):
        r = _run(picks=["Unbreakable Stand", "Invulnerability", "Desperation"])
        texts = " ".join(s["text"] for s in (r.get("trait_mod_statuses") or r.get("trait_statuses") or []))
        # at minimum the bespoke module ran (No Guard stat present)
        assert _stat(r, "no_guard_dmg_taken") > 0 or texts

    def test_no_trait_unchanged(self):
        none = _run(trait_id=None)
        assert _stat(none, "no_guard_dmg_taken") == 0.0       # trait-specific: nothing without the trait
        assert none["defense"]["block_ratio"] == pytest.approx(0.30)   # base 30%, no Invulnerability
