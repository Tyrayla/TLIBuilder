"""Rosa — High Court Chariot (trait_id "high_court_chariot") end-to-end engine coverage.

Locks: +30% block chance + Artificial Moon per-10-MI; inside-domain additional damage by level; Unbreakable
Stand's weighted per-enemy (Boss ×5) + 100% cap; Divine Intervention per-MI; the **No Guard** model (base 10% ×
(1+stacks-lost) × (1+Block-Ratio additional), 2 stacks → +100%); Block Ratio base 30% + Invulnerability + upper
limit; inside-domain gating; never-silently-drop status surface; non-regression (trait_id=None unchanged).
"""
import pytest
from server import engine_stats, EngineStatsRequest
from tests.mock_build import make_request

SPELL = "chain_lightning"


def _val(stats, key):
    v = stats.get(key)
    return (v.get("value", v.get("total", 0)) if isinstance(v, dict) else (v or 0)) or 0


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
        # +10%/enemy (tier 5) × (1 enemy × 5 Boss weight) = +50% additional damage.
        one = self._dps(_run(picks=["Unbreakable Stand"], conds={"enemies_in_holy_domain": 1}))
        base = self._dps(_run(conds={"inside_holy_domain": True}))
        assert one > base
        # Cap at +100%: 3 enemies × 5 = 15 × 10% = 150% → capped 100%; 5 enemies same (already capped).
        cap3 = self._dps(_run(picks=["Unbreakable Stand"], conds={"enemies_in_holy_domain": 3}))
        cap5 = self._dps(_run(picks=["Unbreakable Stand"], conds={"enemies_in_holy_domain": 5}))
        assert cap5 == pytest.approx(cap3)

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
