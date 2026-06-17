"""Curse skills — enemy damage-taken amplification, Curse Effect scaling, curse limit + conflict, and
conversion-correctness (a curse keys off the FINAL damage type, so a Lightning curse is nullified once the
skill converts 100% of its lightning to cold).

Scope: damage-taken amplification only (Vulnerability→Physical, Scorch→Fire, Biting Cold→Cold, Electrocute→
Lightning, Corruption→Erosion, Timid→all Hit). Entangled Pain (DoT) / Dazzled / Ominous are NYI. Curse pooling
across types is multiplicative (matches the enemy-vulnerability stage) — flagged for in-game verification.
"""
import pytest

from engine.offense import _enemy_vuln_mult
from engine.models import BuildSource
from engine.curse_resolver import resolve_curses
from server import (_parse_custom_mod_text as pm, _extract_affix_curse,
                    engine_stats, EngineStatsRequest, _get_skills_data, season_manager)


def _src(**stats):
    s = BuildSource()
    for k, v in stats.items():
        s.add(k, v)
    return s


class TestVulnMultiplier:
    def test_per_type_scoped(self):
        s = _src(physical_curse_taken=0.39)
        assert _enemy_vuln_mult(s, "physical") == pytest.approx(1.39)
        assert _enemy_vuln_mult(s, "fire") == pytest.approx(1.0)        # wrong type
        assert _enemy_vuln_mult(s, "erosion") == pytest.approx(1.0)

    def test_hit_applies_to_every_type(self):
        s = _src(hit_curse_taken=0.39)   # Timid — all hit damage
        for t in ("physical", "fire", "cold", "lightning", "erosion"):
            assert _enemy_vuln_mult(s, t) == pytest.approx(1.39)

    def test_distinct_curses_multiply(self):
        s = _src(fire_curse_taken=0.39, hit_curse_taken=0.20)
        assert _enemy_vuln_mult(s, "fire") == pytest.approx(1.39 * 1.20)


class TestParsers:
    @pytest.mark.parametrize("text,key,amt", [
        ("+30 % Curse Effect", "curse_effect_inc", 0.30),
        ("+20 % additional Curse Effect", "curse_effect_additional", 0.20),
        ("You can cast 1 additional Curses", "max_curses_flat", 1.0),
        ("You can only cast 1 Curses", "curse_limit_cap_flat", 1.0),
    ])
    def test_parse(self, text, key, amt):
        res = pm(text)
        assert res and res[0]["stat_key"] == key and res[0]["amount"] == pytest.approx(amt)

    def test_affix_curse_extraction(self):
        assert _extract_affix_curse("Triggers Lv. 20 Scorch Curse upon inflicting damage. Cooldown: 0.2 s") == \
            {"curse_name": "Scorch", "level": 20}
        assert _extract_affix_curse("Nearby enemies within 15 m are cursed by Lv. 20 Ominous") == \
            {"curse_name": "Ominous", "level": 20}
        assert _extract_affix_curse("Nearby enemies within 10m are cursed by Lv. (16-20) Biting Cold") == \
            {"curse_name": "Biting Cold", "level": 20}
        assert _extract_affix_curse("+39 % increased Fire Damage") is None


class TestResolveCurses:
    def test_dedup_keeps_highest_level(self):
        sbi = _get_skills_data(season_manager.get_active_season())
        # Same curse from a slot (Lv1) and an affix (Lv20) → one entry, highest level kept.
        active, _st, _meta = resolve_curses(
            [{"slot": 2, "skill_id": "electrocute", "level": 1}],
            [{"curse_name": "Electrocute", "level": 20, "source_label": "Gear"}], sbi)
        elec = [c for c in active if (c["curse_name"] or "").lower() == "electrocute"]
        assert len(elec) == 1 and elec[0]["level"] == 20
        assert elec[0]["stat_key"] == "lightning_curse_taken"


class TestEndToEnd:
    def _dps(self, skills, conds=None, custom=None):
        return engine_stats(EngineStatsRequest(
            slots=[None, None, None, None], condition_state=conds or {}, custom_mods=custom or [],
            skills=skills, main_skill={"skill_id": "chain_lightning", "level": 14},
            characterLevel=100))["offense"]["total_dps"]

    _MAIN = {"slot": 1, "skill_id": "chain_lightning", "level": 14}
    _ELEC = {"slot": 2, "skill_id": "electrocute", "level": 20}
    _SCORCH = {"slot": 3, "skill_id": "scorch", "level": 20}
    _COLD = {"slot": 2, "skill_id": "biting_cold", "level": 20}
    _CONV = ["Converts 100% of Lightning Damage to Cold Damage"]

    def test_electrocute_amplifies_lightning(self):
        base = self._dps([self._MAIN])
        assert self._dps([self._MAIN, self._ELEC]) == pytest.approx(base * 1.39)

    def test_conversion_nullifies_wrong_type_curse(self):
        # Lightning curse on a skill that converts 100% of its lightning to cold → curse does nothing.
        base = self._dps([self._MAIN], custom=self._CONV)
        assert self._dps([self._MAIN, self._ELEC], custom=self._CONV) == pytest.approx(base)

    def test_cold_curse_applies_after_conversion(self):
        # The matching (cold) curse DOES apply to the converted damage.
        base = self._dps([self._MAIN], custom=self._CONV)
        assert self._dps([self._MAIN, self._COLD], custom=self._CONV) == pytest.approx(base * 1.39)

    def test_curse_effect_scales(self):
        base = self._dps([self._MAIN])
        # +100% Curse Effect doubles the 0.39 line → ×1.78
        assert self._dps([self._MAIN, self._ELEC], custom=["+100 % Curse Effect"]) == pytest.approx(base * 1.78)

    def test_over_limit_conflict_contributes_nothing(self):
        base = self._dps([self._MAIN])
        # 2 curses, default limit 1, no resolution → no curse stats applied.
        assert self._dps([self._MAIN, self._ELEC, self._SCORCH]) == pytest.approx(base)

    def test_conflict_resolved_by_selection(self):
        base = self._dps([self._MAIN])
        got = self._dps([self._MAIN, self._ELEC, self._SCORCH],
                        conds={"curse_sel_electrocute": True})
        assert got == pytest.approx(base * 1.39)   # only the selected (lightning) curse applies

    def test_raising_limit_avoids_conflict(self):
        base = self._dps([self._MAIN])
        got = self._dps([self._MAIN, self._ELEC, self._SCORCH], custom=["You can cast 1 additional Curses"])
        # limit 2 → both apply; only Electrocute (lightning) touches the lightning main skill.
        assert got == pytest.approx(base * 1.39)
