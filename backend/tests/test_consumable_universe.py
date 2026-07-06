"""The maximal consumable-stat universe (engine/consumable_universe.py) backs the 4-state modifier badges:
a resolved stat in `consumed_stats` → green; in the universe but not consumed → grey "Inactive"; resolved
but NOT in the universe → yellow "Unconsumed"; unresolved → red NYI.

Two guarantees here:
  • the synthetic run stays stable and covers the offense/defense floor (no silent shrink);
  • every literal `source.total("X")` the AGGREGATOR reads is in the universe, so propagation inputs never
    misreport as "engine never reads it". This test fails the moment a new aggregator read drifts out of sync.
"""
import os
import re

from engine.consumable_universe import consumable_universe, _SANITY_FLOOR
from models.stat_meta import STAT_META


def test_universe_is_stable_and_nonempty():
    u = consumable_universe()
    assert 150 < len(u) < 600, f"universe size {len(u)} outside sane range — synthetic run likely changed shape"
    assert consumable_universe() is u  # cached singleton


def test_universe_covers_sanity_floor():
    u = consumable_universe()
    assert _SANITY_FLOOR <= u


def test_universe_overlaps_stat_meta():
    # The universe may also contain engine-internal intermediate keys (gear pre-pool, ailment intermediates)
    # that aren't STAT_META modifier keys — harmless for badges (no modifier resolves to them). Just assert
    # the bulk are real modifier stats so a future enum rename can't quietly empty the overlap.
    valid = {s.value for s in STAT_META}
    assert len(consumable_universe() & valid) >= 150


def test_speed_additional_pools_present():
    # Read via source_log, not source.total — must be added back explicitly (regression guard).
    u = consumable_universe()
    assert "attack_speed_additional" in u and "cast_speed_additional" in u


# pipeline.py is the DEPRECATED legacy engine (/api/engine/compute, no renderer caller). Its reads don't
# reflect the live badge path, so exclude it — the stats it reads but the live engine doesn't are genuine
# yellow gaps (e.g. elemental_dmg_inc, double_dmg_chance), not universe misses.
_DEPRECATED_ENGINE_FILES = {"pipeline.py"}


def test_all_live_engine_stat_reads_are_in_universe():
    """Scan EVERY live engine file for `source.total/get/sum("literal")` and assert each real stat is in the
    universe. This is the whack-a-mole guard: a modeled read added anywhere (offense/defense/derive/compute/
    aggregator, support-gated, condition-cap) can't silently badge a stat 'engine never reads it'. If this
    fails, make the universe synthetic run exercise that path (or add the stat) in consumable_universe.py."""
    import glob
    engine_dir = os.path.join(os.path.dirname(__file__), "..", "engine")
    reads: dict[str, set] = {}
    for f in glob.glob(os.path.join(engine_dir, "*.py")):
        if os.path.basename(f) in _DEPRECATED_ENGINE_FILES:
            continue
        text = open(f, encoding="utf-8").read()
        for m in re.findall(r'source\.(?:total|get|sum)\(\s*"([a-z0-9_]+)"\s*\)', text):
            reads.setdefault(m, set()).add(os.path.basename(f))
    assert reads, "expected to find source reads across the live engine"
    valid = {s.value for s in STAT_META}
    u = consumable_universe()
    missing = {k: sorted(v) for k, v in reads.items() if k in valid and k not in u}
    assert not missing, (
        f"live engine reads these stats but they're missing from the consumable universe: {missing}. "
        "Make the synthetic run in engine/consumable_universe.py exercise that read path so badges don't "
        "false-yellow a modeled stat."
    )
