"""
Generalized "inflicts Numbed" detection (engine.ailment_inflict) — works from ANY mod source
(talents / gear / custom mods), not just attached supports. Numbed stacks stay user-set; an inflict line
enables the enemy_numbed gate + auto-floors a baseline (max-rule, gated by hit damage type). "cannot
inflict Numbed" hard-overrides.
"""
import pytest
from engine.ailment_inflict import scan_numbed_inflict
from server import engine_stats, EngineStatsRequest
from tests.mock_build import make_request

A = "Inflicts Numbed when dealing Hit Lightning Damage"
C2 = "Inflicts 2 additional stack(s) of Numbed"
E = "Critical Strikes are guaranteed to inflict Numbed"
G = "When the supported skill deals Elemental Hit Damage, inflicts Frostbite, Numbed, or Ignite based on element"
H = "The supported skill cannot inflict Ignite, Frostbite or Numbed"


def _stacks(skill="chain_lightning", mods=None, conds=None):
    r = engine_stats(EngineStatsRequest(**make_request(skill, 14, custom_mods=mods or [], extra_conditions=conds or {})))
    return float((r.get("numbed") or {}).get("stacks") or 0.0)


class TestScan:
    def test_a_is_lightning(self):
        s = scan_numbed_inflict([A]); assert s.lightning and not s.elemental and s.additional == 0
    def test_additional(self):
        s = scan_numbed_inflict([A, C2]); assert s.lightning and s.additional == 2
    def test_block(self):
        assert scan_numbed_inflict([A, H]).blocked
    def test_elemental(self):
        s = scan_numbed_inflict([G]); assert s.elemental
    def test_excludes_effect_and_recently(self):
        s = scan_numbed_inflict(["+20 % Numbed Effect", "+15 % Movement Speed if you have inflicted Numbed recently"])
        assert not s.active


class TestEngine:
    def test_floor_one_on_lightning(self):
        assert _stacks(mods=[A]) == pytest.approx(1.0)

    def test_additional_raises_floor(self):
        assert _stacks(mods=[A, C2]) == pytest.approx(3.0)   # 1 + 2

    def test_user_value_respected_over_floor(self):
        assert _stacks(mods=[A], conds={"numbed_stacks": 8}) == pytest.approx(8.0)

    def test_block_forces_zero(self):
        assert _stacks(mods=[A, H]) == 0.0

    def test_block_overrides_user_value(self):
        assert _stacks(mods=[H], conds={"numbed_stacks": 9}) == 0.0

    def test_gated_on_lightning_damage(self):
        # A non-lightning skill carrying the line inflicts no Numbed (no Lightning hit).
        assert _stacks(skill="berserking_blade", mods=[A]) == 0.0

    def test_no_line_no_numbed(self):
        assert _stacks() == 0.0

    def test_inflict_line_badges_resolved(self):
        r = engine_stats(EngineStatsRequest(**make_request("chain_lightning", 14, custom_mods=[A])))
        st = next(s for s in r["custom_mod_statuses"] if "Inflicts Numbed" in s["text"])
        assert st["resolved"] is True
