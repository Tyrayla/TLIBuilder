"""Conditional gating for magnificent/noble support specific-tier lines (the hybrid: bespoke support
resolver delegates condition translation to server._translate_condition_expr, like the node resolver).

Guarantees: (1) NO regression on the verified non-conditional supports (Chain Lightning et al. resolve
byte-identical to the frozen baseline); (2) a conditional line ("…when only 1 enemy nearby") is GATED, not
applied always-on; (3) an untranslatable gate drops the line (no ungated DPS inflation); (4) enemy_nearby
auto-derives enemies_nearby >= 1.
"""
import json
import os

import pytest

from engine.support_resolver import resolve_support_contributions
from server import _translate_condition_expr as tc, engine_stats, EngineStatsRequest

_SKILLS = json.load(open(os.path.join(os.path.dirname(__file__), "..", "..", "data", "seasons", "SS12",
                                       "_skills.json"), encoding="utf-8"))
_BY_ID = {it["item_id"]: it for it in _SKILLS["skills"]}
_BASELINE = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "support_baseline.json"),
                           encoding="utf-8"))


def _resolve(sid, rank=5, level=1):
    st = _BY_ID[sid]["skill_type"]
    return resolve_support_contributions([{"item_id": sid, "skill_type": st, "rank": rank, "level": level}],
                                         _BY_ID, tc)


class TestNoRegression:
    @pytest.mark.parametrize("sid", ["chain_lightning_web_of_lightning_magnificent",
                                     "chain_lightning_lucky_noble"])
    def test_verified_chain_lightning_supports_unchanged(self, sid):
        new = [(c["stat_key"], round(c["amount"], 6)) for c in _resolve(sid)]
        old = [tuple(x) for x in _BASELINE[sid]["contribs"]]
        assert new == old
        assert all(c.get("condition") is None for c in _resolve(sid))

    def test_nonconditional_supports_identical_to_baseline(self):
        """Every baseline support's UNGATED contributions still match (gated/dropped conditionals are the
        only intended change)."""
        bad = []
        for sid, base in _BASELINE.items():
            ungated = [(c["stat_key"], round(c["amount"], 6)) for c in _resolve(sid) if not c.get("condition")]
            old = [tuple(x) for x in base["contribs"]]
            # ungated must be old minus any dropped-conditional tail entries → ungated is a prefix of old
            if ungated != old[:len(ungated)]:
                bad.append((sid, old, ungated))
        assert not bad, f"non-conditional support amounts changed: {bad[:5]}"


class TestGating:
    def test_duel_line_is_gated(self):
        duel = _resolve("focused_slash_duel_magnificent")
        cond_lines = [c for c in duel if c.get("condition")]
        assert cond_lines and cond_lines[0]["condition"] == {"key": "enemies_nearby", "op": "==", "value": 1}

    def test_untranslatable_conditional_dropped(self):
        # blazing_bullet's specific +44% has an untranslatable gate → dropped (was applied ungated).
        new = [round(c["amount"], 3) for c in _resolve("blazing_bullet_ignition_point_noble")]
        assert new == [0.2]  # only the universal rank line; the conditional specific line is gone


def _baseline_sword(slot):
    """A no-affix baseline 1H sword (base implicits only) so attack skills produce real DPS in tests."""
    def c(stat, val):
        return {"stat": stat, "display_value": val, "unit": "", "item_name": "Baseline 1H Sword",
                "text": "base", "slot": slot, "condition": None}
    return {"item_name": "Baseline 1H Sword", "base_type": "One-Handed Sword", "slot": slot,
            "contributions": [c("physical_dmg_gear_flat_min", 100), c("physical_dmg_gear_flat_max", 150),
                              c("weapon_attack_speed", 1.5), c("weapon_crit_rating_flat", 500)]}


class TestEndToEnd:
    """Focused Slash dual-wielding baseline 1H swords; Duel's +67.5% gates on enemies_nearby == 1."""
    def _dps(self, cond):
        sup = [{"item_id": "focused_slash_duel_magnificent", "skill_type": "magnificent_support_skill",
                "rank": 1, "level": 1}]
        r = engine_stats(EngineStatsRequest(
            slots=[None, None, None, None], condition_state=cond,
            gear=[_baseline_sword("weapon1"), _baseline_sword("weapon2")],
            skills=[{"slot": 1, "skill_id": "focused_slash", "level": 14}],
            main_skill={"skill_id": "focused_slash", "level": 14},
            attached_supports=sup, characterLevel=100))
        return r["offense"]["total_dps"]

    def test_gate_off_and_on(self):
        off = self._dps({"enemies_nearby": 2})
        assert off > 0
        assert self._dps({"enemies_nearby": 1}) == pytest.approx(off * 1.675, rel=1e-3)

    def test_enemy_nearby_autoderives_count(self):
        assert self._dps({"enemy_nearby": True}) == pytest.approx(self._dps({"enemies_nearby": 1}))


def _skills():
    from server import _get_skills_data
    from persistence import season_manager
    return _get_skills_data(season_manager.get_active_season())


def test_standard_support_specific_line_not_double_resolved():
    """A STANDARD support (support_skill) is resolved by resolve_standard_supports in the compute loop, so
    resolve_support_contributions must NOT also parse its specific line — else it double-counts. Regression:
    Critical Strike Damage Increase landed as BOTH dmg_additional_on_crit (here) and dmg_additional (there)."""
    sk = _skills()
    std = [{"item_id": "critical_strike_damage_increase", "skill_type": "support_skill",
            "level": 20, "slot": 1, "enabled": True}]
    assert resolve_support_contributions(std, sk, tc) == []
