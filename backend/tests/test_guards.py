"""Tests: engine/guards.py — the damage-taken immunity tripwire."""
import pytest
from engine.models import BuildSource, SourceEntry
from engine.defense import _dmg_taken_factor
from engine.guards import check_damage_taken_immunity, ImmunityThresholdError


def _add(source: BuildSource, stat: str, amount: float, label: str, text: str) -> None:
    source.add_with_source(stat, amount, SourceEntry(stat=stat, amount=amount, source_type="test", label=label, text=text))


def test_no_violation_passes():
    s = BuildSource()
    s.add("dmg_taken_additional", -0.5)       # 50% reduction — fine
    s.add("attack_dmg_additional", 2.0)        # large offense — irrelevant
    check_damage_taken_immunity(s)             # must not raise


def test_additional_taken_at_minus_100_percent_raises():
    s = BuildSource()
    s.add("dmg_taken_additional", -0.6)
    s.add("dmg_taken_additional", -0.5)        # sums to -1.1 -> multiplier <= 0 -> immune
    with pytest.raises(ImmunityThresholdError) as e:
        check_damage_taken_immunity(s)
    assert "dmg_taken_additional" in str(e.value)


def test_just_under_threshold_passes():
    s = BuildSource()
    s.add("physical_dmg_taken_additional", -0.99)   # 99% reduction — still takes damage
    check_damage_taken_immunity(s)


def test_reduction_style_stat_at_100_percent_raises():
    # crit_dmg_taken_reduction is reduction-style: multiplier = 1 - total
    s = BuildSource()
    s.add("crit_dmg_taken_reduction", 1.0)
    with pytest.raises(ImmunityThresholdError):
        check_damage_taken_immunity(s)


def test_conversion_taken_stat_is_ignored():
    # 'taken_as' conversion stats are not magnitude reductions — never trip the guard.
    s = BuildSource()
    s.add("cold_taken_as_fire_inc", 5.0)
    check_damage_taken_immunity(s)


# ── Distinct sources multiply, not sum (owner-confirmed in-game mechanic; see 1FrxGVV) ─────────────────

def test_six_distinct_moderate_sources_multiply_instead_of_summing():
    # The exact real-world case that exposed the bug: six independently-legitimate reductions on the
    # SAME stat key (a conditional belt affix, a talent node, three blessing stacks, and a Warcry line
    # scaled by Power) summed to -121.42% under the old model, wrongly implying immunity. Multiplied,
    # they combine to ~23.44% of raw damage taken (~76.6% total reduction) — never reaching zero.
    s = BuildSource()
    _add(s, "dmg_taken_additional", -0.16, "Wayfarer Waistguard (Crafted)", "-16% additional damage taken at Low Mana")
    _add(s, "dmg_taken_additional", -0.06, "Onslaughter", "-6% additional damage taken")
    _add(s, "dmg_taken_additional", -0.16, "Focus Blessing", "-4% additional Damage Taken per Focus Blessing")
    _add(s, "dmg_taken_additional", -0.16, "Agility Blessing", "-4% additional Damage Taken per Agility Blessing")
    _add(s, "dmg_taken_additional", -0.20, "Tenacity Blessing", "-4% additional Damage Taken per Tenacity Blessing")
    _add(s, "dmg_taken_additional", -0.4742, "Resurrection Warcry", "Additional Damage Taken")

    check_damage_taken_immunity(s)   # must NOT raise — no single source is anywhere near -100%

    factor = _dmg_taken_factor(s, "physical", is_dot=False)
    assert factor == pytest.approx(0.84 * 0.94 * 0.84 * 0.84 * 0.80 * 0.5258, rel=1e-6)


def test_a_single_source_at_minus_100_percent_still_raises_even_though_it_stacks_with_others():
    # Per owner ruling: the guard must still fire when ONE source alone reaches immunity, distinct from
    # the many-moderate-sources case above (which the multiplicative model makes structurally safe).
    s = BuildSource()
    _add(s, "dmg_taken_additional", -0.10, "Minor buff", "-10% additional damage taken")
    _add(s, "dmg_taken_additional", -1.00, "Hypothetical bug/overtuned line", "-100% additional damage taken")
    with pytest.raises(ImmunityThresholdError):
        check_damage_taken_immunity(s)


def test_combining_across_stat_keys_in_the_same_pool_still_multiplies():
    # dmg_taken_additional (universal) and physical_dmg_taken_additional (type-scoped) combine into the
    # SAME pool for physical damage (defense._dmg_taken_keys) — each is its own distinct source and must
    # multiply against the other, not sum. -50% and -60% summed would wrongly cross -100%; multiplied
    # they combine to a fine 0.5 x 0.4 = 0.2.
    s = BuildSource()
    _add(s, "dmg_taken_additional", -0.5, "Source A", "-50% additional damage taken")
    _add(s, "physical_dmg_taken_additional", -0.6, "Source B", "-60% additional Physical Damage Taken")
    check_damage_taken_immunity(s)   # must NOT raise
    assert _dmg_taken_factor(s, "physical", is_dot=False) == pytest.approx(0.2)


def test_enemy_vulnerability_stat_never_trips_the_guard():
    # Offense-side "the enemy takes more damage" amplification (Licorice Note's Scattered Spore) has no
    # immunity concept and routinely exceeds 100% in normal play — must be excluded entirely, not just
    # handled differently.
    s = BuildSource()
    _add(s, "enemy_nearby_dmg_taken_additional", -5.0, "Hypothetical", "large negative — must still be ignored")
    check_damage_taken_immunity(s)
