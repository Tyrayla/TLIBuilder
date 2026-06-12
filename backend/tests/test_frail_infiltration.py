"""Frail + Infiltration enemy-vulnerability debuffs (master-glossary values).

Frail: "Additionally increases Spell Damage taken by 15%" — Spell-FORM scoped (applies to all damage of a
Spell skill, gated off for Attack skills). Infiltration (fire/cold/lightning): "Additionally increases
<type> Damage taken by 13%" — element-TYPE scoped. Each scaled by its *_effect_inc. enemy_affected_by_*
conditions are user-set (auto-derive from inflict affixes is a follow-up). Vulnerability (curse) deferred;
its chance-to-suffer-Trauma stays NYI. Increased-vs-additional pooling flagged for in-game testing — kept
multiplicative here.
"""
import pytest

from engine.offense import _enemy_vuln_mult
from engine.models import BuildSource
from server import _parse_custom_mod_text as pm, engine_stats, EngineStatsRequest


def _src(**stats):
    s = BuildSource()
    for k, v in stats.items():
        s.add(k, v)
    return s


class TestVulnMultiplier:
    def test_frail_spell_only(self):
        s = _src(frail_spell_taken=0.15)
        assert _enemy_vuln_mult(s, "lightning", is_spell=True) == pytest.approx(1.15)
        assert _enemy_vuln_mult(s, "lightning", is_spell=False) == pytest.approx(1.0)  # Spell-form gated off

    def test_infiltration_type_scoped(self):
        s = _src(fire_infiltration_taken=0.13)
        assert _enemy_vuln_mult(s, "fire", is_spell=True) == pytest.approx(1.13)
        assert _enemy_vuln_mult(s, "lightning", is_spell=True) == pytest.approx(1.0)  # wrong type
        assert _enemy_vuln_mult(s, "erosion", is_spell=True) == pytest.approx(1.0)    # no erosion infiltration

    def test_sources_multiply(self):
        s = _src(frail_spell_taken=0.15, lightning_infiltration_taken=0.13)
        assert _enemy_vuln_mult(s, "lightning", is_spell=True) == pytest.approx(1.15 * 1.13)


class TestResolveEffectStats:
    @pytest.mark.parametrize("text,key", [
        ("+40 % Frail Effect", "frail_effect_inc"),
        ("+30 % Fire Infiltration Effect", "fire_infiltration_effect_inc"),
        ("+25 % Cold Infiltration Effect", "cold_infiltration_effect_inc"),
        ("+20 % Lightning Infiltration Effect", "lightning_infiltration_effect_inc"),
    ])
    def test_effect_resolves(self, text, key):
        assert pm(text)[0]["stat_key"] == key


class TestEndToEnd:
    def _dps(self, cond):
        return engine_stats(EngineStatsRequest(
            slots=[None, None, None, None], condition_state=cond,
            skills=[{"slot": 1, "skill_id": "chain_lightning", "level": 14}],
            main_skill={"skill_id": "chain_lightning", "level": 14}, characterLevel=100))["offense"]["total_dps"]

    def test_frail_applies_to_spell(self):
        base = self._dps({})
        assert self._dps({"enemy_affected_by_frail": True}) == pytest.approx(base * 1.15)

    def test_lightning_infiltration_applies(self):
        base = self._dps({})
        assert self._dps({"enemy_affected_by_lightning_infiltration": True}) == pytest.approx(base * 1.13)

    def test_fire_infiltration_does_not_touch_lightning_skill(self):
        base = self._dps({})
        assert self._dps({"enemy_affected_by_fire_infiltration": True}) == pytest.approx(base)

    def test_frail_effect_scales(self):
        # +100% Frail Effect doubles the 15% -> 30% on a spell skill
        base = self._dps({})
        # condition + a frail_effect_inc source via custom mod
        res = engine_stats(EngineStatsRequest(
            slots=[None, None, None, None], condition_state={"enemy_affected_by_frail": True},
            custom_mods=["+100 % Frail Effect"],
            skills=[{"slot": 1, "skill_id": "chain_lightning", "level": 14}],
            main_skill={"skill_id": "chain_lightning", "level": 14}, characterLevel=100))["offense"]["total_dps"]
        assert res == pytest.approx(base * 1.30)
