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
    assert 150 < len(u) < 260, f"universe size {len(u)} outside sane range — synthetic run likely changed shape"
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


def test_aggregator_total_reads_are_in_universe():
    """Scan engine/aggregator.py for `source.total("literal")` and assert each is in the universe — so an
    aggregator propagation read added later can't silently badge a modeled stat as 'engine never reads it'."""
    agg = os.path.join(os.path.dirname(__file__), "..", "engine", "aggregator.py")
    text = open(agg, encoding="utf-8").read()
    reads = set(re.findall(r'source\.total\(\s*"([a-z0-9_]+)"\s*\)', text))
    assert reads, "expected to find source.total(\"...\") reads in aggregator.py"
    u = consumable_universe()
    missing = {k for k in reads if k in {s.value for s in STAT_META}} - u
    assert not missing, (
        f"aggregator reads these stats but they're missing from the consumable universe: {sorted(missing)}. "
        "Add them to _AGGREGATOR_PROPAGATION_INPUTS in engine/consumable_universe.py."
    )
