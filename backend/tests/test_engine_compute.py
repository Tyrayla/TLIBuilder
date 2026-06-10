"""
Tests: engine/compute.py — the pure helpers that drive the condition fixed-point loop:
view splitting, numeric clamping + *_active re-derivation, and condition max/min derivation.
The full compute() loop needs season/filter data, so it's exercised end-to-end elsewhere.
"""
import pytest
from engine.models import BuildSource
from engine.compute import (
    _derive_views, _clamp_and_rederive,
    derive_condition_maximums, derive_condition_minimums,
)
from models.conditions import ConditionDef


def _src(**stats) -> BuildSource:
    s = BuildSource()
    for k, v in stats.items():
        s.add(k, v)
    return s


def _cond(key, **kw) -> ConditionDef:
    return ConditionDef(key=key, label=key, category="test", **kw)


class TestDeriveViews:
    def test_splits_bool_and_numeric(self):
        active, numeric = _derive_views({"a": True, "b": False, "c": 5, "d": 2.5})
        assert active == frozenset({"a"})        # only truthy booleans
        assert numeric == {"c": 5.0, "d": 2.5}

    def test_bool_never_leaks_into_numeric(self):
        _, numeric = _derive_views({"flag": True})
        assert "flag" not in numeric


class TestClampAndRederive:
    def test_clamps_down_to_max(self):
        assert _clamp_and_rederive({"x": 10.0}, {"x": 5.0}, {})["x"] == 5.0

    def test_raises_up_to_min(self):
        assert _clamp_and_rederive({"x": 2.0}, {}, {"x": 5.0})["x"] == 5.0

    def test_within_bounds_unchanged(self):
        assert _clamp_and_rederive({"x": 7.0}, {"x": 10.0}, {"x": 3.0})["x"] == 7.0

    def test_key_without_bounds_unchanged(self):
        assert _clamp_and_rederive({"x": 99.0}, {}, {})["x"] == 99.0

    def test_bool_untouched(self):
        assert _clamp_and_rederive({"flag": True}, {}, {})["flag"] is True

    def test_active_flag_rederived_from_stack(self, monkeypatch):
        monkeypatch.setattr("models.conditions.DERIVED_ACTIVE_KEYS", {"foo_active": "foo"})
        assert _clamp_and_rederive({"foo": 3.0}, {}, {})["foo_active"] is True
        assert _clamp_and_rederive({"foo": 0.0}, {}, {})["foo_active"] is False

    def test_active_flag_uses_clamped_value(self, monkeypatch):
        monkeypatch.setattr("models.conditions.DERIVED_ACTIVE_KEYS", {"foo_active": "foo"})
        out = _clamp_and_rederive({"foo": 5.0}, {"foo": 0.0}, {})   # clamped to 0 → inactive
        assert out["foo"] == 0.0
        assert out["foo_active"] is False

    def test_derived_numeric_sums_sources(self, monkeypatch):
        monkeypatch.setattr("models.conditions.DERIVED_NUMERIC_KEYS", {"any_blessings": ["a", "b", "c"]})
        out = _clamp_and_rederive({"a": 2.0, "b": 3.0, "c": 1.0}, {}, {})
        assert out["any_blessings"] == pytest.approx(6.0)

    def test_derived_numeric_uses_clamped_values(self, monkeypatch):
        monkeypatch.setattr("models.conditions.DERIVED_NUMERIC_KEYS", {"any_blessings": ["a", "b"]})
        out = _clamp_and_rederive({"a": 9.0, "b": 4.0}, {"a": 4.0}, {})  # a clamped 9→4
        assert out["any_blessings"] == pytest.approx(8.0)

    def test_derived_numeric_missing_sources_zero(self, monkeypatch):
        monkeypatch.setattr("models.conditions.DERIVED_NUMERIC_KEYS", {"any_blessings": ["a", "b"]})
        assert _clamp_and_rederive({"a": 2.0}, {}, {})["any_blessings"] == pytest.approx(2.0)


class TestConditionMaximums:
    def test_max_from_stat_adds_base_and_stat(self, monkeypatch):
        monkeypatch.setattr("models.conditions.ALL_CONDITIONS",
                            [_cond("a", value_type="numeric", max_from_stat="a_max", max_base=10)])
        assert derive_condition_maximums(_src(a_max=5))["a"] == pytest.approx(15)

    def test_numeric_max_literal(self, monkeypatch):
        monkeypatch.setattr("models.conditions.ALL_CONDITIONS",
                            [_cond("b", value_type="numeric", numeric_max=50)])
        assert derive_condition_maximums(_src())["b"] == pytest.approx(50)

    def test_max_base_only(self, monkeypatch):
        monkeypatch.setattr("models.conditions.ALL_CONDITIONS",
                            [_cond("c", value_type="numeric", max_base=7)])
        assert derive_condition_maximums(_src())["c"] == pytest.approx(7)

    def test_booleans_and_unbounded_numeric_excluded(self, monkeypatch):
        monkeypatch.setattr("models.conditions.ALL_CONDITIONS", [
            _cond("d", value_type="boolean", max_base=99),   # not numeric → skipped
            _cond("e", value_type="numeric"),                # numeric but no max → excluded
        ])
        out = derive_condition_maximums(_src())
        assert "d" not in out and "e" not in out


class TestConditionMinimums:
    def test_min_from_stat_adds_base_and_stat(self, monkeypatch):
        monkeypatch.setattr("models.conditions.ALL_CONDITIONS",
                            [_cond("a", value_type="numeric", min_from_stat="a_min", min_base=2)])
        assert derive_condition_minimums(_src(a_min=4))["a"] == pytest.approx(6)

    def test_min_base_only(self, monkeypatch):
        monkeypatch.setattr("models.conditions.ALL_CONDITIONS",
                            [_cond("b", value_type="numeric", min_base=3)])
        assert derive_condition_minimums(_src())["b"] == pytest.approx(3)

    def test_no_min_excluded(self, monkeypatch):
        monkeypatch.setattr("models.conditions.ALL_CONDITIONS",
                            [_cond("c", value_type="numeric")])
        assert "c" not in derive_condition_minimums(_src())
