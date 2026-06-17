"""Empower (Euphoria) player buffs — scaled by Empower Skill Effect, emitted as typed/scoped player damage stats
(so they ride offense's conversion-aware pipeline like auras). Plus the empower supports (Well-Fought Battle user-set
casts default-max; Mass Effect charge-scaled) and the per-skill charges helper.

Scope: player damage/speed/crit buffs. Minion/Sentry/ally-targeted empowers are NYI. Uptime assumed 100%.
"""
import pytest

from engine.models import BuildSource
from engine.empower_resolver import resolve_empowers
from engine.support_resolver import resolve_standard_supports
from engine.skill_charges import skill_base_charges, is_charge_ambiguous
from server import (_parse_custom_mod_text as pm, _get_skills_data, season_manager,
                    _translate_condition_expr, engine_stats, EngineStatsRequest)

SBI = _get_skills_data(season_manager.get_active_season())


class TestEndToEnd:
    def _dps(self, skills, conds=None, custom=None):
        return engine_stats(EngineStatsRequest(
            slots=[None, None, None, None], condition_state=conds or {}, custom_mods=custom or [],
            skills=skills, main_skill={"skill_id": "chain_lightning", "level": 14},
            characterLevel=100))["offense"]["total_dps"]

    MAIN = {"slot": 1, "skill_id": "chain_lightning", "level": 14}
    SECRET = {"slot": 2, "skill_id": "secret_origin_unleash", "level": 20}   # +15% additional Spell Damage
    BULL = {"slot": 2, "skill_id": "bull_s_rage", "level": 20}               # +27% additional Melee Damage

    def test_spell_empower_applies(self):
        base = self._dps([self.MAIN])
        assert self._dps([self.MAIN, self.SECRET]) == pytest.approx(base * 1.15)

    def test_empower_effect_scales(self):
        base = self._dps([self.MAIN])
        assert self._dps([self.MAIN, self.SECRET], custom=["+100 % Empower Skill Effect"]) == pytest.approx(base * 1.30)

    def test_melee_empower_does_not_buff_a_spell(self):
        # Bull's Rage buffs Melee skills; chain_lightning is a Spell — scope gates it out (like conversion-correctness).
        base = self._dps([self.MAIN])
        assert self._dps([self.MAIN, self.BULL]) == pytest.approx(base)


class TestResolve:
    def test_player_buff_resolves(self):
        b, _st, _sc, _m = resolve_empowers(
            [{"slot": 2, "skill_id": "secret_origin_unleash", "level": 20}], SBI, pm, _translate_condition_expr)
        assert any(g["stat_key"] == "spell_dmg_additional" and g["base_amount"] == pytest.approx(0.15) for g in b)

    def test_ally_targeted_is_nyi(self):
        # Archery Bond grants Euphoria to Nearby allies/Sentries → no player buffs, surfaced NYI.
        b, st, _sc, _m = resolve_empowers(
            [{"slot": 2, "skill_id": "archery_bond", "level": 20}], SBI, pm, _translate_condition_expr)
        assert b == [] and any(s["kind"] == "nyi" for s in st)


class TestCharges:
    def test_cooldown_skill_has_charge(self):
        assert skill_base_charges(SBI["black_hole"]) == 1   # Black Hole has a cooldown

    def test_no_cooldown_no_charge(self):
        assert skill_base_charges(SBI["bull_s_rage"]) is None

    def test_ambiguous_flagged(self):
        assert is_charge_ambiguous({"detailed_description": ["Has a cooldown but no number"]}) is True
        assert is_charge_ambiguous({"detailed_description": ["Deals fire damage"]}) is False


class TestEmpowerSupports:
    def _resolve(self, item_id, host, empower_slots, conds=None):
        return resolve_standard_supports(
            [{"item_id": item_id, "slot": 2, "level": 1}], SBI, None, [], conds or {}, {2: "spell"},
            source=BuildSource(), empower_slots=empower_slots, slot_skill={2: host})[0]

    def _eff(self, contribs):
        return sum(c["amount"] for c in contribs if c["stat_key"] == "empower_effect_inc")

    def test_well_fought_battle_default_max(self):
        # 5.25% per cast × 3 (default max) = 15.75% Empower Effect.
        eff = self._eff(self._resolve("well_fought_battle", "secret_origin_unleash", {2}))
        assert eff == pytest.approx(0.1575, abs=1e-3)

    def test_well_fought_battle_user_set(self):
        eff = self._eff(self._resolve("well_fought_battle", "secret_origin_unleash", {2},
                                      conds={"well_fought_battle_stacks": 1}))
        assert eff == pytest.approx(0.0525, abs=1e-3)

    def test_mass_effect_charge_scaled(self):
        # Black Hole has a cooldown (1 charge); Mass Effect adds +1 → 2 charges → 10.5% × 2 = 21%.
        eff = self._eff(self._resolve("mass_effect", "black_hole", {2}))
        assert eff == pytest.approx(0.21, abs=1e-3)

    def test_empower_only_gate(self):
        # Mass Effect on a non-empower host (empower_slots empty) is gated out — no contribution.
        assert self._eff(self._resolve("mass_effect", "chain_lightning", set())) == 0.0
