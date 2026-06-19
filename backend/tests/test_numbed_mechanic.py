"""
Tests: the Numbed enemy-vulnerability mechanic — Numbed's base effect (+5% Lightning Damage the
target takes per stack) scales per stack of the user-set numbed_stacks condition AND is multiplied by
Numbed Effect (numbed_effect_inc). Baked into the lightning-scoped `numbed_lightning_taken` stat, which
offense's enemy-vulnerability stage consumes. (The per-stack value is modelled engine-side like Fervor,
not on the condition.)
"""
import pytest
from engine.aggregator import aggregate
from engine.models import BuildInput


def _build(custom=None):
    return BuildInput(slots=[], slates=[], season="t", custom_contributions=custom or [])


def _numbed_effect(frac):
    # Feed numbed_effect_inc into the aggregated source via a custom contribution.
    return [{"stat_key": "numbed_effect_inc", "amount": frac, "text": "Numbed Effect"}]


def _numbed_effect_mix(inc=0.0, additional=0.0):
    return [
        {"stat_key": "numbed_effect_inc", "amount": inc, "text": "Numbed Effect"},
        {"stat_key": "numbed_effect_additional", "amount": additional, "text": "additional Numbed Effect"},
    ]


class TestNumbed:
    def test_stacks_grant_lightning_taken(self):
        # 0.05 * 10 stacks = +50% Lightning Damage taken, no Numbed Effect.
        src = aggregate(_build(), {}, {}, numeric_vals={"numbed_stacks": 10.0})
        assert src.total("numbed_lightning_taken") == pytest.approx(0.50)

    def test_partial_stacks(self):
        src = aggregate(_build(), {}, {}, numeric_vals={"numbed_stacks": 4.0})
        assert src.total("numbed_lightning_taken") == pytest.approx(0.20)

    def test_scales_with_numbed_effect(self):
        # +50% Numbed Effect multiplies the base: 0.05 * 10 * (1 + 0.5) = 0.75.
        src = aggregate(_build(_numbed_effect(0.5)), {}, {}, numeric_vals={"numbed_stacks": 10.0})
        assert src.total("numbed_lightning_taken") == pytest.approx(0.75)

    def test_additional_numbed_effect_is_separate_multiplicative_pool(self):
        # inc and additional multiply separately: 0.05 * 10 * (1+0.5) * (1+0.6) = 1.20.
        src = aggregate(_build(_numbed_effect_mix(inc=0.5, additional=0.6)), {}, {},
                        numeric_vals={"numbed_stacks": 10.0})
        assert src.total("numbed_lightning_taken") == pytest.approx(1.20)

    def test_additional_numbed_effect_alone(self):
        # 0.05 * 10 * (1+0.6) = 0.80.
        src = aggregate(_build(_numbed_effect_mix(additional=0.6)), {}, {},
                        numeric_vals={"numbed_stacks": 10.0})
        assert src.total("numbed_lightning_taken") == pytest.approx(0.80)

    def test_additional_numbed_effect_multiplies_per_distinct_source(self):
        # Two DISTINCT additional sources MULTIPLY (×1.2 × ×1.3 = ×1.56), like every other additional pool —
        # NOT sum (which would be ×1.5). 0.05 * 10 * 1.2 * 1.3 = 0.78.
        contribs = [
            {"stat_key": "numbed_effect_additional", "amount": 0.2, "text": "Source A"},
            {"stat_key": "numbed_effect_additional", "amount": 0.3, "text": "Source B"},
        ]
        src = aggregate(_build(contribs), {}, {}, numeric_vals={"numbed_stacks": 10.0})
        assert src.total("numbed_lightning_taken") == pytest.approx(0.78)

    def test_same_source_additional_numbed_effect_sums(self):
        # Same-text additional positives SUM into one factor (×1.5), not multiply: 0.05*10*1.5 = 0.75.
        contribs = [
            {"stat_key": "numbed_effect_additional", "amount": 0.25, "text": "Same Source"},
            {"stat_key": "numbed_effect_additional", "amount": 0.25, "text": "Same Source"},
        ]
        src = aggregate(_build(contribs), {}, {}, numeric_vals={"numbed_stacks": 10.0})
        assert src.total("numbed_lightning_taken") == pytest.approx(0.75)

    def test_numbed_effect_noop_without_stacks(self):
        src = aggregate(_build(_numbed_effect(0.5)), {}, {}, numeric_vals={"numbed_stacks": 0.0})
        assert src.total("numbed_lightning_taken") == 0.0

    def test_no_stacks_no_effect(self):
        assert aggregate(_build(), {}, {}, numeric_vals={}).total("numbed_lightning_taken") == 0.0

    def test_logged_as_source(self):
        src = aggregate(_build(), {}, {}, numeric_vals={"numbed_stacks": 5.0})
        entry = next(e for e in src.source_log if e.stat == "numbed_lightning_taken")
        assert entry.label == "Numbed Stacks" and entry.source_type == "condition"
