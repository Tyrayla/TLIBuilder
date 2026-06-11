"""Damage-type conversion (outgoing hit damage) — the cascade math and fraction handling.

Model locked from in-game tests (see plan / Damage Type Conversion help doc):
- priority Physical→Lightning→Cold→Fire→Erosion; conversion flows UP only;
- a converted/added slice carries its PATH: type-specific increases SUM, additionals MULTIPLY;
- generic inc/add apply once; convert reduces the source's staying portion, adds-as is extra;
- >100% convert from one source caps at 100% and redistributes by weight.
"""
import pytest

from engine.offense import _apply_conversion, _conversion_fracs, _CONV_PRIORITY


def _run(flat, spec_inc=None, spec_add=None, gi=0.0, ga=1.0, convert=None, adds=None):
    si = {t: (spec_inc or {}).get(t, 0.0) for t in _CONV_PRIORITY}
    sa = {t: (spec_add or {}).get(t, 1.0) for t in _CONV_PRIORITY}
    return _apply_conversion(flat, si, sa, gi, ga, convert or {}, adds or {})


class _StubSource:
    """Minimal source: .total(key) returns the configured fraction (0 otherwise)."""
    def __init__(self, **vals):
        self._v = vals
    def total(self, key):
        return self._v.get(key, 0.0)


class TestCascadeMath:
    def test_increases_sum_over_path(self):
        # Test 1 in-game: 100% L→C, +54% L, +54% C → cold = base × (1 + 0.54 + 0.54). Lightning emptied.
        r = _run({"lightning": (100, 100)}, spec_inc={"lightning": 0.54, "cold": 0.54},
                 convert={"lightning": {"cold": 1.0}})
        assert r["cold"][0] == pytest.approx(208.0)
        assert "lightning" not in r

    def test_additionals_multiply_over_path(self):
        # Test 3 in-game: 100% L→C, +31% L-add, +31% C-add → cold = base × 1.31 × 1.31.
        r = _run({"lightning": (100, 100)}, spec_add={"lightning": 1.31, "cold": 1.31},
                 convert={"lightning": {"cold": 1.0}})
        assert r["cold"][0] == pytest.approx(171.61)

    def test_worked_example(self):
        # 100 L + 50 C flat (post-eff), 100% L→C convert + 10% L-as-C added, +50% L, +50% C.
        r = _run({"lightning": (100, 100), "cold": (50, 50)},
                 spec_inc={"lightning": 0.5, "cold": 0.5},
                 convert={"lightning": {"cold": 1.0}}, adds={"lightning": {"cold": 0.10}})
        # native 50×1.5=75 + converted 100×2.0=200 + added 10×2.0=20 = 295
        assert r["cold"][0] == pytest.approx(295.0)
        assert "lightning" not in r

    def test_multi_hop_accumulates_all_three(self):
        # Phys→L→C (both 100%): cold gets phys+lightning+cold increases SUMMED.
        r = _run({"physical": (100, 100)},
                 spec_inc={"physical": 0.2, "lightning": 0.3, "cold": 0.4},
                 convert={"physical": {"lightning": 1.0}, "lightning": {"cold": 1.0}})
        assert r["cold"][0] == pytest.approx(190.0)   # 100 × (1+0.2+0.3+0.4)

    def test_min_max_carried(self):
        # The (min,max) range is carried through conversion (sliced proportionally).
        r = _run({"lightning": (100, 200)}, spec_inc={"lightning": 0.5, "cold": 0.5},
                 convert={"lightning": {"cold": 1.0}})
        assert r["cold"] == pytest.approx((200.0, 400.0))   # (100×2.0, 200×2.0)

    def test_partial_convert_splits_types(self):
        # 50% L→C: half stays lightning, half becomes cold; each carries the right path.
        r = _run({"lightning": (100, 100)}, spec_inc={"lightning": 0.5, "cold": 0.5},
                 convert={"lightning": {"cold": 0.5}})
        assert r["lightning"][0] == pytest.approx(50 * 1.5)          # 75, only lightning's +50%
        assert r["cold"][0] == pytest.approx(50 * (1 + 0.5 + 0.5))   # 100, both increases summed

    def test_adds_as_does_not_reduce_source(self):
        # adds-as is EXTRA: lightning stays full, cold gains 10% of lightning.
        r = _run({"lightning": (100, 100)}, adds={"lightning": {"cold": 0.10}})
        assert r["lightning"][0] == pytest.approx(100.0)
        assert r["cold"][0] == pytest.approx(10.0)

    def test_generic_applied_once(self):
        # Generic inc applies ONCE per final stream, not per path-type.
        r = _run({"lightning": (100, 100)}, spec_inc={"lightning": 0.5, "cold": 0.5}, gi=0.2,
                 convert={"lightning": {"cold": 1.0}})
        assert r["cold"][0] == pytest.approx(100 * (1 + 0.2 + 0.5 + 0.5))   # generic 0.2 once

    def test_no_conversion_is_native_scaling(self):
        # Regression: no conversion → (1 + generic + spec_inc) × generic_add × spec_add per native type.
        r = _run({"cold": (100, 200)}, spec_inc={"cold": 0.5}, spec_add={"cold": 1.2}, gi=0.1, ga=1.0)
        assert r["cold"] == pytest.approx((192.0, 384.0))


class TestEndToEnd:
    """Through the live calculate_offense path: an attack skill with source flat + conversion stats."""

    def _offense(self, **stats):
        from engine.models import BuildSource
        from engine.offense import calculate_offense
        from engine.skill_resolver import ResolvedSkill, SkillHitForm
        src = BuildSource()
        for k, v in stats.items():
            src.add(k, v)
        skill = ResolvedSkill(
            skill_id="t", name="T", tags=["attack"], max_level=1,
            hit_forms_by_level={1: [SkillHitForm(name="Hit", effectiveness_pct=100.0,
                                                 form_type="additive", proc_stat_key=None)]},
            supported=True, base_steep_strike_chance=0.0,
        )
        r = calculate_offense(src, skill, 1)
        return r.hit_forms[0].damage_by_type

    def test_convert_retypes_and_sums_increases(self):
        # 100 physical flat, 100% phys→lightning, +20% phys +30% lightning → lightning 150, no physical.
        d = self._offense(physical_attack_dmg_flat_min=100.0, physical_attack_dmg_flat_max=100.0,
                          physical_convert_to_lightning=1.0, physical_dmg_inc=0.2, lightning_dmg_inc=0.3)
        assert d.get("lightning") == pytest.approx(150.0)
        assert d.get("physical", 0.0) == pytest.approx(0.0)

    def test_lucky_applies_on_final_type(self):
        # Lightning flat 100–200, lucky_lightning, no conversion → lightning gets the EV uplift.
        d = self._offense(lightning_attack_dmg_flat_min=100.0, lightning_attack_dmg_flat_max=200.0,
                          lucky_lightning=1.0)
        # avg 150 × (150 + (2/3)·100)/(150 + 50)... uplift = (100+66.67)/(100+50)=1.1111 on min-based spread
        assert d["lightning"] == pytest.approx(150.0 * (100 + (2/3)*100) / (100 + 0.5*100))

    def test_lucky_vanishes_when_its_type_converted_away(self):
        # Same lucky_lightning, but 100% lightning→cold: final type is Cold (not lucky) → plain average.
        d = self._offense(lightning_attack_dmg_flat_min=100.0, lightning_attack_dmg_flat_max=200.0,
                          lucky_lightning=1.0, lightning_convert_to_cold=1.0)
        assert d.get("cold") == pytest.approx(150.0)   # no luck uplift on cold
        assert d.get("lightning", 0.0) == pytest.approx(0.0)


class TestConversionFracs:
    def test_over_100_percent_caps_and_redistributes(self):
        # Physical 60%→Lightning + 60%→Cold = 120% → capped to 100%, redistributed by weight (0.5/0.5).
        conv, _ = _conversion_fracs(_StubSource(
            physical_convert_to_lightning=0.6, physical_convert_to_cold=0.6))
        assert conv["physical"]["lightning"] == pytest.approx(0.5)
        assert conv["physical"]["cold"] == pytest.approx(0.5)

    def test_asymmetric_over_100_rebalances_by_weight(self):
        # Help DB example: 60% phys→fire + 100% phys→cold = 160% → fire 0.375, cold 0.625 (proportional).
        conv, _ = _conversion_fracs(_StubSource(
            physical_convert_to_fire=0.6, physical_convert_to_cold=1.0))
        assert conv["physical"]["fire"] == pytest.approx(0.375)
        assert conv["physical"]["cold"] == pytest.approx(0.625)
        assert sum(conv["physical"].values()) == pytest.approx(1.0)
        # End-to-end: 100 physical fully consumed → 37.5 fire + 62.5 cold (no increases).
        r = _run({"physical": (100, 100)}, convert=conv)
        assert r["fire"][0] == pytest.approx(37.5)
        assert r["cold"][0] == pytest.approx(62.5)
        assert "physical" not in r

    def test_under_100_unchanged(self):
        conv, _ = _conversion_fracs(_StubSource(lightning_convert_to_cold=0.3))
        assert conv["lightning"]["cold"] == pytest.approx(0.3)

    def test_physical_as_elemental_spreads(self):
        # physical_as_elemental adds its % as each of fire/cold/lightning.
        _, adds = _conversion_fracs(_StubSource(physical_as_elemental=0.4))
        for d in ("fire", "cold", "lightning"):
            assert adds["physical"][d] == pytest.approx(0.4)

    def test_only_up_chain_pairs(self):
        # Erosion (highest) has no outgoing conversions; fire only → erosion.
        conv, adds = _conversion_fracs(_StubSource())
        assert conv["erosion"] == {} and adds["erosion"] == {}
        # Reading a down-chain key (cold→lightning) is never attempted (not in higher list).
