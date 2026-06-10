"""
Tests: the Six Gods' Blessings base-effect mechanic — each blessing grants a per-stack base effect,
scaled by its user-set stack count. Stacks of one blessing ADD (one summed factor). Focus/Agility feed
the additional-damage and increased-speed pools; Tenacity feeds damage-taken (defensive). The override
hook (_BLESSING_OVERRIDES) is architected but unwired, so defaults always apply today.
Source: TLI Help DB /Battle Mechanics/Statuses/Six Gods' Blessings.
"""
import pytest
from engine.aggregator import aggregate
from engine.models import BuildInput


def _build():
    return BuildInput(slots=[], slates=[], season="t")


class TestFocus:
    def test_additive_per_stack(self):
        # 4 stacks × +5% additional damage = +20% (one summed factor).
        src = aggregate(_build(), {}, {}, numeric_vals={"focus_blessings": 4.0})
        assert src.total("dmg_additional") == pytest.approx(0.20)

    def test_zero_stacks_no_effect(self):
        assert aggregate(_build(), {}, {}, numeric_vals={"focus_blessings": 0.0}).total("dmg_additional") == 0.0

    def test_logged_as_condition(self):
        src = aggregate(_build(), {}, {}, numeric_vals={"focus_blessings": 1.0})
        entry = next(e for e in src.source_log if e.stat == "dmg_additional")
        assert entry.label == "Focus Blessing" and entry.source_type == "condition"


class TestAgility:
    def test_speed_and_additional(self):
        # 3 stacks: +12% attack speed, +12% cast speed, +6% additional damage.
        src = aggregate(_build(), {}, {}, numeric_vals={"agility_blessings": 3.0})
        assert src.total("attack_speed_inc") == pytest.approx(0.12)
        assert src.total("cast_speed_inc") == pytest.approx(0.12)
        assert src.total("dmg_additional") == pytest.approx(0.06)


class TestTenacity:
    def test_defensive_damage_taken(self):
        # 4 stacks × -4% damage taken = -16% (defensive; no offensive contribution by default).
        src = aggregate(_build(), {}, {}, numeric_vals={"tenacity_blessings": 4.0})
        assert src.total("dmg_taken_additional") == pytest.approx(-0.16)
        assert src.total("dmg_additional") == 0.0


class TestCombined:
    def test_focus_and_agility_additional_are_distinct_entries(self):
        # Focus and Agility both feed dmg_additional but via DISTINCT source text, so offense's per-affix
        # pool multiplies them rather than summing. Here we assert both contributions are present and
        # logged as separate rows (the multiplication happens later, in offense._build_additional_factors).
        src = aggregate(_build(), {}, {}, numeric_vals={"focus_blessings": 2.0, "agility_blessings": 2.0})
        add_entries = [e for e in src.source_log if e.stat == "dmg_additional"]
        texts = {e.text for e in add_entries}
        assert any("Focus" in t for t in texts) and any("Agility" in t for t in texts)
        # Raw stat-key total is the additive sum of the two (0.10 + 0.04); multiplicative split is offense's job.
        assert src.total("dmg_additional") == pytest.approx(0.14)
