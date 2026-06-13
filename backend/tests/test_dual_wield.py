"""
Tests: dual-wielding base effects — +30% Attack Block Chance and +10% additional Attack Speed,
granted (fixed, unscaled) while the 'dual_wielding' condition is active.
"""
import pytest
from engine.aggregator import aggregate
from engine.models import BuildInput


def _build():
    return BuildInput(slots=[], slates=[], season="t")


class TestDualWield:
    def test_grants_block_and_attack_speed(self):
        s = aggregate(_build(), {}, {}, active_booleans=frozenset({"dual_wielding"}))
        assert s.total("attack_block_chance_inc") == pytest.approx(0.30)
        assert s.total("attack_speed_additional") == pytest.approx(0.10)

    def test_nothing_without_dual_wielding(self):
        s = aggregate(_build(), {}, {}, active_booleans=frozenset())
        assert s.total("attack_block_chance_inc") == 0.0
        assert s.total("attack_speed_additional") == 0.0

    def test_logged_sources(self):
        s = aggregate(_build(), {}, {}, active_booleans=frozenset({"dual_wielding"}))
        labels = {e.label for e in s.source_log if e.stat in ("attack_block_chance_inc", "attack_speed_additional")}
        assert labels == {"Dual Wielding"}
