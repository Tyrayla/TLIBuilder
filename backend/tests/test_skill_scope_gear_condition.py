"""Leading/trailing condition on an UNRESOLVED (scoped) gear affix (follow-up to the skill-scope feature).

The frontend sends affixes it can't type-resolve as raw `unresolved_texts`; the server gear loop resolves
them. A conditional like "If you have recently moved more than 60 m, +X% additional damage dealt by Spell
Skills" must (a) resolve the stat clause to its base stat + scope (NOT red-NYI), and (b) GATE the
contribution on the translated condition — applied only when the condition holds, never always-on. A gate
that can't be translated keeps the line UNRESOLVED (honest NYI) rather than silently dropping the condition.
"""
import pytest

from server import engine_stats, EngineStatsRequest

_LEADING = "If you have recently moved more than 60 m, +(25-35) % additional damage dealt by Spell Skills"


def _dps(unresolved_texts, cond, skill="chain_lightning"):
    req = EngineStatsRequest(
        slots=[None, None, None, None],
        gear=[{"item_name": "TestItem", "unresolved_texts": unresolved_texts}],
        condition_state=cond,
        skills=[{"slot": 1, "skill_id": skill, "level": 14}],
        main_skill={"skill_id": skill, "level": 14},
        characterLevel=100,
    )
    return engine_stats(req)


class TestLeadingConditionGearAffix:
    def test_resolves_not_nyi(self):
        st = [s for s in _dps([_LEADING], {})["gear_mod_statuses"] if "recently moved" in s["text"]]
        assert st and st[0]["resolved"] is True          # was red-NYI before leading-condition support

    def test_gated_off_when_condition_unmet(self):
        # Spell scope matches chain_lightning, but the gate (moved > 60 m) is unmet → no effect.
        base = _dps([], {})["offense"]["total_dps"]
        off = _dps([_LEADING], {})["offense"]["total_dps"]
        assert off == pytest.approx(base)

    def test_applies_when_condition_met(self):
        base = _dps([], {"meters_moved_recently": 100})["offense"]["total_dps"]
        on = _dps([_LEADING], {"meters_moved_recently": 100})["offense"]["total_dps"]
        assert on == pytest.approx(base * 1.30)          # +30% additional (midpoint of 25-35), gated ON

    def test_untranslatable_gate_stays_unresolved(self):
        # "if you have recently killed" has no engine condition → must NOT apply always-on; report NYI.
        text = "+30 % damage if you have recently killed"
        res = _dps([text], {})
        st = [s for s in res["gear_mod_statuses"] if s["text"] == text]
        assert st and st[0]["resolved"] is False
        assert res["offense"]["total_dps"] == pytest.approx(_dps([], {})["offense"]["total_dps"])
