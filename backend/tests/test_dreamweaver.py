"""Dreamweaver (and the cloudgatherer / idling-weasel siblings) pact-spirit mechanics:
- "Damage Penetrates N% <type> Resistance" slot nodes resolve to {type}_pen.
- On-hit stacking resistance pen ("+N% Elemental Resistance Penetration … stacking up to M times") resolves
  to a PER-STACK elemental_pen scaled by the shared `elemental_hit_pen_stacks` condition (the buff = per-stack
  × stacks; the condition defaults to its max for full uptime, user-adjustable).
"""
import pytest

from server import _resolve_effect_modifiers as rem, _parse_custom_mod_text as pm, engine_stats, EngineStatsRequest


class TestDamagePenetrates:
    @pytest.mark.parametrize("text,key", [
        ("Damage Penetrates 2 % Elemental Resistance", "elemental_pen"),
        ("Damage Penetrates 4 % Elemental Resistance", "elemental_pen"),
        ("Damage Penetrates 5 % Fire Resistance", "fire_pen"),
        ("Damage Penetrates 5 % Erosion Resistance", "erosion_pen"),
    ])
    def test_resolves(self, text, key):
        r = pm(text)
        assert r and r[0]["stat_key"] == key


class TestStackingPen:
    def test_resolves_per_stack_with_condition(self):
        r = rem("+1 % Elemental Resistance Penetration when hitting an enemy with Elemental Damage, "
                "stacking up to 4 times", is_memory=False)
        assert len(r) == 1
        d = r[0]
        assert d["stat_key"] == "elemental_pen"
        assert d["amount"] == pytest.approx(0.01)                      # per-stack value
        assert d["condition"] == {"key": "elemental_hit_pen_stacks", "op": "per", "divisor": 1}

    def test_every_time_phrasing(self):
        r = rem("+3 % Elemental Resistance Penetration every time you hit an enemy with Elemental Damage "
                "recently. Stacks up to 4 times", is_memory=False)
        assert r[0]["stat_key"] == "elemental_pen" and r[0]["amount"] == pytest.approx(0.03)


class TestStackScaling:
    def _fire_resist(self, stacks):
        r = engine_stats(EngineStatsRequest(
            slots=[None, None, None, None],
            spirit_effects=["+1 % Elemental Resistance Penetration when hitting an enemy with Elemental "
                            "Damage, stacking up to 4 times"],
            condition_state={"elemental_hit_pen_stacks": stacks},
            skills=[{"slot": 1, "skill_id": "chain_lightning", "level": 14}],
            main_skill={"skill_id": "chain_lightning", "level": 14}, characterLevel=100))
        return r["target_stats"]["resists"]["fire"]["effective"]

    def test_zero_stacks_no_pen(self):
        assert self._fire_resist(0) == pytest.approx(0.30)

    def test_max_stacks_full_pen(self):
        # +1% per stack × 4 = 4% pen → 0.30 - 0.04
        assert self._fire_resist(4) == pytest.approx(0.26)


def test_dreamweaver_fully_resolves():
    from persistence.season_manager import load_pact_spirits
    dw = next(s for s in load_pact_spirits("SS12")["spirits"] if s["item_id"] == "dreamweaver")
    lines = {l for rk in dw["upgrade_ranks"] for l in rk["modifiers"]}
    lines |= {l for slot in dw["slots"] for l in slot["effect"]}
    nyi = [l for l in lines if not rem(l, is_memory=False)]
    assert not nyi, f"Dreamweaver lines still NYI: {nyi}"
