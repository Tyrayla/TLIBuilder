"""Per-slot contribution foundation: slot-local supports fold only into their slot's offense (no cross-
contamination), the materialize identity fast-path is preserved, enable/disable toggles gate cleanly, and
the custom-mod path strips conditions consistently with gear."""
import pytest

from server import engine_stats, EngineStatsRequest
from engine.models import BuildSource, SourceEntry
from engine.compute import _apply_cond_effects
from engine.support_mapper import ConditionEffect


def _sword(slot):
    def c(stat, val):
        return {"stat": stat, "display_value": val, "unit": "", "item_name": "BL", "text": "base",
                "slot": slot, "condition": None}
    return {"item_name": "BL", "base_type": "One-Handed Sword", "slot": slot,
            "contributions": [c("physical_dmg_gear_flat_min", 100), c("physical_dmg_gear_flat_max", 150),
                              c("weapon_attack_speed", 1.5), c("weapon_crit_rating_flat", 500)]}


def _req(**kw):
    base = dict(slots=[None, None, None, None], gear=[_sword("weapon1"), _sword("weapon2")],
                characterLevel=100)
    base.update(kw)
    return engine_stats(EngineStatsRequest(**base))


class TestMaterializeIdentity:
    def test_identity_fast_path_no_overlays(self):
        s = BuildSource()
        s.add_with_source("attack_dmg_inc", 0.3, SourceEntry(
            stat="attack_dmg_inc", amount=0.3, source_type="gear", label="g", text="t"))
        assert s.materialize_for_skill({"attack"}, 1) is s   # no scoped/slot entries → returns self

    def test_slot_entry_folds_only_for_matching_slot(self):
        s = BuildSource()
        s.add_slotted("dmg_additional", 0.2, 2, None, SourceEntry(
            stat="dmg_additional", amount=0.2, source_type="support", label="s", text="x"))
        assert s.materialize_for_skill(set(), 1).total("dmg_additional") == 0.0   # slot 1 doesn't see slot 2
        assert s.materialize_for_skill(set(), 2).total("dmg_additional") == pytest.approx(0.2)


class TestSlotIsolation:
    """A support on slot 2 must not change slot 1's DPS (two Berserking/attack setups don't cross-feed)."""
    _SUP2 = {"item_id": "focused_slash_duel_magnificent", "skill_type": "magnificent_support_skill",
             "rank": 5, "level": 1, "slot": 2}

    def _two_slot(self, with_sup2):
        return _req(
            skills=[{"slot": 1, "skill_id": "berserking_blade", "level": 14},
                    {"slot": 2, "skill_id": "focused_slash", "level": 14}],
            main_skill={"skill_id": "berserking_blade", "level": 14},
            attached_supports=[self._SUP2] if with_sup2 else [],
            condition_state={"enemies_nearby": 2})

    def test_slot2_support_does_not_change_slot1(self):
        a = self._two_slot(False)["slot_offense"]
        b = self._two_slot(True)["slot_offense"]
        assert b["1"]["total_dps"] == pytest.approx(a["1"]["total_dps"], rel=1e-9)   # slot 1 unaffected
        assert b["2"]["total_dps"] > a["2"]["total_dps"]                              # slot 2 boosted


class TestEnabledGating:
    _SUP = {"item_id": "berserking_blade_rampage_noble", "skill_type": "noble_support_skill",
            "rank": 1, "level": 1, "slot": 1}

    def _dps(self, supports):
        return _req(skills=[{"slot": 1, "skill_id": "berserking_blade", "level": 14}],
                    main_skill={"skill_id": "berserking_blade", "level": 14},
                    attached_supports=supports)["offense"]["total_dps"]

    def test_disabled_support_equals_omitting_it(self):
        none = self._dps([])
        enabled = self._dps([self._SUP])
        disabled = self._dps([{**self._SUP, "enabled": False}])
        assert enabled > none
        assert disabled == pytest.approx(none, rel=1e-9)

    def test_disabled_skill_drops_its_slot(self):
        r = _req(skills=[{"slot": 1, "skill_id": "berserking_blade", "level": 14, "enabled": True},
                         {"slot": 2, "skill_id": "focused_slash", "level": 14, "enabled": False}],
                 main_skill={"skill_id": "berserking_blade", "level": 14})
        assert "1" in r["slot_offense"] and "2" not in r["slot_offense"]


class TestCustomModConditionStripping:
    """Consistency: the custom-mod path strips a condition gate like gear, instead of failing to resolve."""
    def _dps(self, cond):
        return _req(condition_state=cond, custom_mods=["+50 % Attack Damage against Low Life enemies"],
                    skills=[{"slot": 1, "skill_id": "berserking_blade", "level": 14}],
                    main_skill={"skill_id": "berserking_blade", "level": 14})["offense"]["total_dps"]

    def test_conditional_custom_mod_resolves_and_gates(self):
        r = _req(custom_mods=["+50 % Attack Damage against Low Life enemies"],
                 skills=[{"slot": 1, "skill_id": "berserking_blade", "level": 14}],
                 main_skill={"skill_id": "berserking_blade", "level": 14})
        assert r["custom_mod_statuses"][0]["resolved"] is True   # was previously unresolved (NYI)
        assert self._dps({"enemy_low_life": True}) > self._dps({})


class TestBuildWideDebuffDedup:
    """#2: a build-wide enemy condition fed by multiple enabled hosts combines by OR / max, never summed
    (two skills both applying Numbed = Numbed once at max stacks, not double)."""
    def test_set_true_is_or_not_additive(self):
        cs = {}
        effs = [ConditionEffect("enemy_numbed", 1.0, "set_true", requires_dtype="lightning"),
                ConditionEffect("enemy_numbed", 1.0, "set_true", requires_dtype="lightning")]
        _apply_cond_effects(cs, effs, ["lightning"], set())
        assert cs["enemy_numbed"] is True   # boolean OR, not 2

    def test_max_not_sum(self):
        cs = {}
        effs = [ConditionEffect("numbed_stacks", 3.0, "max", requires_dtype="lightning"),
                ConditionEffect("numbed_stacks", 5.0, "max", requires_dtype="lightning"),
                ConditionEffect("numbed_stacks", 2.0, "max", requires_dtype="lightning")]
        _apply_cond_effects(cs, effs, ["lightning"], set())
        assert cs["numbed_stacks"] == 5.0   # max of the three, not 10

    def test_manual_value_respected(self):
        cs = {"numbed_stacks": 8.0}
        _apply_cond_effects(cs, [ConditionEffect("numbed_stacks", 5.0, "max", requires_dtype="lightning")],
                            ["lightning"], {"numbed_stacks"})
        assert cs["numbed_stacks"] == 8.0   # user-set value not lowered/overridden
