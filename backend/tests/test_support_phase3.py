"""Tests: Phase 3 wiring — standard-support resolution + tag-gate, auto-derived condition-effect
application (with manual-value protection), and the support buff/debuff base-effect tables."""
import json, os
import pytest
from engine.support_resolver import resolve_standard_supports
from engine.support_mapper import ConditionEffect
from engine.compute import _apply_cond_effects
from engine.aggregator import aggregate
from engine.models import BuildInput

_SKILLS = os.path.join(os.path.dirname(__file__), "..", "..", "data", "seasons", "SS12", "_skills.json")


def _skills():
    d = json.load(open(_SKILLS, encoding="utf-8"))
    s = d.get("skills", d) if isinstance(d, dict) else d
    return {x.get("item_id"): x for x in s}, {x.get("name"): x.get("item_id") for x in s}


class TestResolveStandard:
    def setup_method(self):
        self.by_id, self.name2id = _skills()

    def _sup(self, name, level=1):
        return {"item_id": self.name2id[name], "skill_type": "support_skill", "level": level}

    def test_high_voltage_on_spell_emits_and_autoderives(self):
        contribs, effects = resolve_standard_supports([self._sup("High Voltage")], self.by_id, "spell", ["lightning"], {})
        assert any(c["stat_key"] == "lightning_dmg_additional" and c["amount"] > 0 for c in contribs)
        cks = {e.condition_key for e in effects}
        assert "enemy_numbed" in cks and "numbed_stacks" in cks

    def test_spell_only_support_gated_off_attack(self):
        contribs, _ = resolve_standard_supports([self._sup("Control Spell")], self.by_id, "attack", [], {})
        assert contribs == []

    def test_conditional_reads_conds(self):
        c4, _ = resolve_standard_supports([self._sup("Overload")], self.by_id, "spell", ["lightning"], {"focus_blessings": 4})
        assert any(c["stat_key"] == "dmg_additional" and c["amount"] == pytest.approx(0.122) for c in c4)

    def test_noble_mag_not_handled_here(self):
        # a magnificent support (different skill_type) is skipped by the standard resolver
        sup = dict(self._sup("Control Spell"), skill_type="magnificent_support_skill")
        assert resolve_standard_supports([sup], self.by_id, "spell", ["lightning"], {}) == ([], [])

    def test_willpower_per_level_compounds(self):
        # Willpower L16: per-stack 5.6% (from the level Descript), compounding → (1.056)^6 − 1
        c, _ = resolve_standard_supports([dict(self._sup("Willpower"), level=16)], self.by_id, "spell",
                                         ["lightning"], {"standing_still": True, "willpower_stacks": 6})
        wp = next(x for x in c if "Willpower" in x["text"])
        assert wp["stat_key"] == "dmg_additional" and wp["amount"] == pytest.approx(1.056 ** 6 - 1)

    def test_willpower_needs_standing_still(self):
        c, _ = resolve_standard_supports([dict(self._sup("Willpower"), level=16)], self.by_id, "spell",
                                         ["lightning"], {"willpower_stacks": 6})
        assert not any("Willpower" in x["text"] for x in c)


class TestApplyCondEffects:
    def test_set_true_dtype_gated(self):
        cs = {}
        _apply_cond_effects(cs, [ConditionEffect("enemy_numbed", 1, "set_true", requires_dtype="lightning")], ["lightning"], set())
        assert cs["enemy_numbed"] is True

    def test_dtype_gate_blocks(self):
        cs = {}
        _apply_cond_effects(cs, [ConditionEffect("enemy_numbed", 1, "set_true", requires_dtype="lightning")], ["cold"], set())
        assert "enemy_numbed" not in cs

    def test_requires_precondition(self):
        cs = {"enemy_cursed": True}
        _apply_cond_effects(cs, [ConditionEffect("enemy_paralyzed", 1, "set_true", requires_cond="enemy_cursed")], [], set())
        assert cs["enemy_paralyzed"] is True
        cs2 = {}
        _apply_cond_effects(cs2, [ConditionEffect("enemy_paralyzed", 1, "set_true", requires_cond="enemy_cursed")], [], set())
        assert "enemy_paralyzed" not in cs2

    def test_max_never_lowers(self):
        cs = {"numbed_stacks": 5.0}
        _apply_cond_effects(cs, [ConditionEffect("numbed_stacks", 1, "max")], [], set())
        assert cs["numbed_stacks"] == 5.0

    def test_manual_value_not_overridden(self):
        cs = {"enemy_numbed": False}
        _apply_cond_effects(cs, [ConditionEffect("enemy_numbed", 1, "set_true")], [], {"enemy_numbed"})
        assert cs["enemy_numbed"] is False


class TestBuffDebuffTables:
    def _agg(self, conds):
        return aggregate(
            BuildInput(slots=[], slates=[], season="t", condition_state=conds), {}, {},
            active_booleans=frozenset(k for k, v in conds.items() if isinstance(v, bool) and v),
            numeric_vals={k: float(v) for k, v in conds.items() if not isinstance(v, bool)},
        )

    def test_paralysis_global_damage_taken(self):
        assert self._agg({"enemy_paralyzed": True}).total("paralysis_dmg_taken") == pytest.approx(0.15)

    def test_electric_overload_lightning(self):
        assert self._agg({"electric_overload": True}).total("lightning_dmg_additional") == pytest.approx(0.15)
