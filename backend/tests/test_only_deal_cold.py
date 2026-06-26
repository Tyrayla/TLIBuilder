"""Extreme Coldness — "You can only deal Cold Damage": any FINAL (post-conversion) damage that isn't Cold
deals zero, but damage that CONVERTS to Cold still counts (the filter runs after the conversion cascade)."""
import pytest
from server import engine_stats, EngineStatsRequest
from tests.mock_build import make_request, DUAL_WEAPONS


def _gear(**stats):
    return DUAL_WEAPONS + [{"item_name": "X", "contributions": [
        {"stat": k, "display_value": v, "unit": "", "slot": "ring", "item_name": "X", "text": f"+{v} {k}"}
        for k, v in stats.items()]}]


def _off(gear=None):
    r = engine_stats(EngineStatsRequest(**make_request("chain_lightning", 20, gear=gear)))
    d = r if isinstance(r, dict) else r.model_dump()
    return d["offense"]


def test_parser_maps_only_deal_cold():
    from engine.mod_parser import _parse_custom_mod_text
    out = _parse_custom_mod_text("You can only deal Cold Damage")
    assert out == [{"stat_key": "can_only_deal_cold", "amount": 1.0, "text": "You can only deal Cold Damage"}]


def test_non_cold_zeroed():
    base = _off()["total_dps"]
    cold_only = _off(_gear(can_only_deal_cold=1))["total_dps"]
    assert base > 0
    assert cold_only == pytest.approx(0.0)          # lightning is non-cold at the end → zero


def test_converted_to_cold_counts():
    base = _off()["total_dps"]
    converted = _off(_gear(can_only_deal_cold=1, lightning_convert_to_cold=1.0))
    assert converted["total_dps"] == pytest.approx(base, rel=1e-6)   # converted to Cold → full damage
    assert set(k for k, v in converted["hit_forms"][0]["damage_by_type"].items() if v) == {"cold"}
