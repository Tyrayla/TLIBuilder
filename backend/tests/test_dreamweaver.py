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


class TestAbsentConditionDefaultsToMax:
    """Regression for the "absent condition_state key silently reads as 0" bug: a build whose stored
    condition_state simply never carries `elemental_hit_pen_stacks` (e.g. an older/sparse save made before
    the key existed) must still get the stacking pen at its catalog default (4, full uptime) — NOT 0. An
    EXPLICIT 0 must still win over that default (the override guard)."""

    # A Dreamweaver rank carrying BOTH stacking elemental-pen lines simultaneously.
    _BOTH_LINES = [
        "+1.2 % Elemental Resistance Penetration when hitting an enemy with Elemental Damage, "
        "stacking up to 4 times",
        "+3 % Elemental Resistance Penetration every time you hit an enemy with Elemental Damage "
        "recently. Stacks up to 4 times",
    ]

    def _run(self, condition_state):
        return engine_stats(EngineStatsRequest(
            slots=[None, None, None, None],
            spirit_effects=self._BOTH_LINES,
            condition_state=condition_state,
            skills=[{"slot": 1, "skill_id": "chain_lightning", "level": 14}],
            main_skill={"skill_id": "chain_lightning", "level": 14}, characterLevel=100))

    def test_absent_key_falls_back_to_catalog_default_max_stacks(self):
        # condition_state has NO elemental_hit_pen_stacks key at all — must fall back to the catalog
        # default of 4 (max stacks), not silently evaluate as 0.
        r = self._run(condition_state={})
        fire_resist = r["target_stats"]["resists"]["fire"]["effective"]
        # (0.012 * 4) + (0.03 * 4) = 0.048 + 0.12 = 0.168 total elemental_pen
        assert fire_resist == pytest.approx(0.30 - 0.168)

    def test_explicit_zero_still_beats_the_default(self):
        # An EXPLICIT 0 must still win over the catalog default of 4 — the override guard.
        r = self._run(condition_state={"elemental_hit_pen_stacks": 0})
        fire_resist = r["target_stats"]["resists"]["fire"]["effective"]
        assert fire_resist == pytest.approx(0.30)


def test_dreamweaver_fully_resolves():
    from persistence.season_manager import load_pact_spirits
    dw = next(s for s in load_pact_spirits("SS12")["spirits"] if s["item_id"] == "dreamweaver")
    lines = {l for rk in dw["upgrade_ranks"] for l in rk["modifiers"]}
    lines |= {l for slot in dw["slots"] for l in slot["effect"]}
    nyi = [l for l in lines if not rem(l, is_memory=False)]
    assert not nyi, f"Dreamweaver lines still NYI: {nyi}"
