"""Skill-scope feature — scoped contributions apply ONLY to matching skills and fold into the BASE stat
pool (plan Test B). Includes the CRITICAL invariant: scoped additionals stay distinctly MULTIPLICATIVE
(never additively merge with unscoped or different-scoped additionals)."""
import pytest

from engine.models import BuildSource, SourceEntry
from engine.offense import calculate_offense
from engine.skill_resolver import ResolvedSkill, SkillHitForm

ALL = ("physical", "fire", "cold", "lightning", "erosion")


def _base_source(**unscoped):
    s = BuildSource()
    s.add("weapon_attack_speed", 1.0)
    for t in ALL:
        s.add(f"{t}_dmg_gear_flat_min", 10.0)
        s.add(f"{t}_dmg_gear_flat_max", 10.0)
    for k, v in unscoped.items():
        s.add(k, v)
    return s


def _scoped(s, stat, amount, scope, text):
    s.add_scoped(stat, amount, scope, SourceEntry(stat=stat, amount=amount, source_type="custom",
                                                  label="X", text=text, scope=scope))


def _skill(tags):
    return ResolvedSkill(skill_id="t", name="T", tags=list(tags), max_level=1,
                         hit_forms_by_level={1: [SkillHitForm(name="H", effectiveness_pct=100.0,
                                                              form_type="additive", proc_stat_key=None)]},
                         supported=True, base_steep_strike_chance=0.0, is_spell=False,
                         base_dmg_by_level={}, base_cast_time=1.0, added_dmg_effectiveness=1.0, main_stat=[])


def _off(source, tags):
    mod_tags = {t.lower() for t in tags}
    return calculate_offense(source.materialize_for_skill(mod_tags), _skill(tags), 1)


class TestScopedApply:
    def test_increase_applies_only_to_matching_skill(self):
        s = _base_source()
        _scoped(s, "lightning_dmg_inc", 0.20, "channeled", "+20% Lightning Damage for Channeled Skills")
        assert _off(s, ["attack", "channeled"]).type_inc["lightning"] == pytest.approx(0.20)
        assert _off(s, ["attack"]).type_inc["lightning"] == pytest.approx(0.0)  # not channeled → gated out

    def test_scoped_folds_into_base_pool_summing_for_increases(self):
        s = _base_source(lightning_dmg_inc=0.10)  # unscoped 10%
        _scoped(s, "lightning_dmg_inc", 0.20, "channeled", "+20% Lightning Damage for Channeled Skills")
        assert _off(s, ["channeled"]).type_inc["lightning"] == pytest.approx(0.30)  # 0.10 + 0.20 (sum)
        assert _off(s, ["attack"]).type_inc["lightning"] == pytest.approx(0.10)     # only unscoped


class TestAdditionalsMultiply:
    """CRITICAL INVARIANT: a scoped additional is its OWN multiplicative factor — it must multiply with the
    unscoped additional, never additively merge."""

    def test_scoped_and_unscoped_additionals_multiply(self):
        s = _base_source()
        s.add_with_source("dmg_additional", 0.10,
                          SourceEntry(stat="dmg_additional", amount=0.10, source_type="gear",
                                      label="U", text="+10% additional damage"))
        _scoped(s, "dmg_additional", 0.14, "channeled", "+14% additional damage for Channeled Skills")
        ga = _off(s, ["channeled"]).generic_add
        assert ga == pytest.approx(1.10 * 1.14)        # 1.254 — MULTIPLY
        assert ga != pytest.approx(1.0 + 0.10 + 0.14)  # NOT 1.24 (additive merge)

    def test_different_scopes_stay_separate_and_absent_off_skill(self):
        s = _base_source()
        _scoped(s, "dmg_additional", 0.10, "channeled", "+10% additional damage for Channeled Skills")
        _scoped(s, "dmg_additional", 0.08, "attack", "+8% additional damage for Attack Skills")
        # Channeled-only skill: just the channeled factor; the attack-scoped one is absent.
        assert _off(s, ["channeled"]).generic_add == pytest.approx(1.10)
        # A skill that is both: both factors multiply.
        assert _off(s, ["channeled", "attack"]).generic_add == pytest.approx(1.10 * 1.08)
