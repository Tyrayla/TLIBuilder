"""<Skill Name> (<skill_id>) — resolver/offense coverage. Mirror test_channeled.py / test_group1_offense.py."""
import pytest
from server import engine_stats, EngineStatsRequest
from tests.mock_build import make_request


def _offense(level=20, gear=None, conds=None, **extra):
    req = make_request("<skill_id>", level, gear=gear, extra_conditions=conds, **extra)
    r = engine_stats(EngineStatsRequest(**req))
    d = r.model_dump() if hasattr(r, "model_dump") else r
    return d["offense"]


def test_supported_and_base_damage():
    o = _offense()
    assert o["supported"] is True
    # SPELL: a form's avg_hit_pre_crit with no added flat == the level-N base midpoint (base unscaled by eff).
    # assert o["hit_forms"][0]["avg_hit_pre_crit"] == pytest.approx((<min> + <max>) / 2.0)

# CHANNELED extras (see test_channeled.py):
# - two forms named "<Continuous>"/"<Burst>"; channeled_max_stacks/min_stacks/behavior set.
# - continuous fires every use (fires_per_sec == aps); burst once per cycle (aps / rounds_per_cycle).
# - added flat scales by per-form effectiveness; base is NOT double-dipped.
# - Min raises burst cadence; Min==Max-1 saturates rounds at 1.
