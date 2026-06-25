"""Editable calc-target ("dummy") stats: the request's target_config parameterizes offense mitigation. Default
Lv85 == the old hardcoded constants (goldens unchanged elsewhere); lower levels / negative resist take more damage."""
import pytest
from server import engine_stats, EngineStatsRequest
from tests.mock_build import make_request


def _vt(target_config=None):
    req = make_request("icebound_beam", 16)   # cold skill
    if target_config is not None:
        req["target_config"] = target_config
    r = engine_stats(EngineStatsRequest(**req))
    d = r.model_dump() if hasattr(r, "model_dump") else r
    return d


def _res(level, armor, res):
    return {"level": level, "armor": armor, "fireRes": res, "coldRes": res, "lightningRes": res, "erosionRes": res}


def test_lower_level_dummy_takes_more_damage():
    base = _vt()                              # Lv85 default (50 armor / 30 res)
    lv40 = _vt(_res(40, 20, 10))             # less armor + resist → more damage vs target
    assert lv40["offense"]["total_dps_vs_target"] > base["offense"]["total_dps_vs_target"]


def test_target_stats_reflect_config():
    d = _vt(_res(40, 20, 10))
    ts = d["target_stats"]
    assert ts["source"] == "Lvl 40 Dummy"
    assert ts["armor"]["base_phys"] == pytest.approx(0.20)
    assert ts["armor"]["base_nonphys"] == pytest.approx(0.20 * 0.60)
    assert ts["resists"]["cold"]["base"] == pytest.approx(0.10)


def test_negative_resist_amplifies():
    # icebound_beam is cold: -50% cold resist drives effective resist negative → cold mitigation < 0 (amplify),
    # so vs-target DPS exceeds the 0%-resist case.
    neg = _vt({"level": 85, "armor": 50, "fireRes": 0, "coldRes": -50, "lightningRes": 0, "erosionRes": 0})
    zero = _vt({"level": 85, "armor": 50, "fireRes": 0, "coldRes": 0, "lightningRes": 0, "erosionRes": 0})
    assert neg["offense"]["total_dps_vs_target"] > zero["offense"]["total_dps_vs_target"]
