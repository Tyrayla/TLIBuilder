"""referenced_conditions: the engine reports every condition key a build mod references (gate ON or OFF), so the
Config screen can hide conditions nothing in the build sources."""
from server import engine_stats, EngineStatsRequest
from tests.mock_build import make_request
from engine.aggregator import _extract_cond_keys


def _result(custom=None, conds=None):
    req = make_request("icebound_beam", 16, extra_conditions=conds)
    if custom:
        req["custom_mods"] = custom
    r = engine_stats(EngineStatsRequest(**req))
    return r.model_dump() if hasattr(r, "model_dump") else r


def test_extract_cond_keys_shapes():
    def keys(expr):
        out: set[str] = set()
        _extract_cond_keys(expr, out)
        return out
    assert keys("low_life") == {"low_life"}
    assert keys({"key": "willpower_stacks", "op": "per", "divisor": 1}) == {"willpower_stacks"}
    assert keys({"and": ["a", {"key": "b"}]}) == {"a", "b"}
    assert keys({"or": ["a", "b"]}) == {"a", "b"}
    assert keys({"not": {"key": "c"}}) == {"c"}
    assert keys({"const": True}) == set()        # benign always-on clause carries no key
    assert keys(None) == set()


def test_referenced_includes_condition_even_when_toggled_off():
    # A custom mod gated on "low life" — with low_life OFF the bonus isn't applied, but the condition is still
    # REFERENCED (the build has a source for it), so it must appear in referenced_conditions.
    d = _result(custom=["10% additional attack damage while at low life"])
    assert "low_life" in (d.get("referenced_conditions") or [])


def test_unreferenced_condition_absent():
    # A plain build with no willpower-scaling source never references willpower_stacks.
    d = _result()
    assert "willpower_stacks" not in (d.get("referenced_conditions") or [])
