"""<Hero> — <Trait Name> (trait_id "<trait_id>") end-to-end engine coverage.

Measure trait DELTAS vs trait_id=None — the mock build has baselines (e.g. dual-wield +30% Attack Block Chance),
so absolute asserts on shared stats are wrong; diff against the no-trait run.
"""
import pytest
from server import engine_stats, EngineStatsRequest
from tests.mock_build import make_request

SPELL = "chain_lightning"


def _val(stats, key):
    v = stats.get(key)
    return (v.get("value", v.get("total", 0)) if isinstance(v, dict) else (v or 0)) or 0


def _run(*, picks=None, conds=None, slot_levels=(5, 5, 5, 5), trait_id="<trait_id>", **extra):
    req = make_request(SPELL, 20, trait_id=trait_id, trait_slot_levels=list(slot_levels),
                       advanced_trait_selections=list(picks or []), extra_conditions=conds or {}, **extra)
    r = engine_stats(EngineStatsRequest(**req))
    return r.model_dump() if hasattr(r, "model_dump") else r


def _stat(resp, key):
    return float(_val(resp["stats"], key))


class TestTrait:
    def test_base_line_delta(self):
        base = _run(trait_id=None)
        r = _run()
        # assert _stat(r, "<stat>") - _stat(base, "<stat>") == pytest.approx(<expected delta>)

    def test_pick_scales(self):
        # hi = _run(picks=["<Pick>"], conds={"<key>": <hi>}); lo = _run(picks=["<Pick>"], conds={"<key>": <lo>})
        # assert hi[...] > lo[...]
        pass

    def test_node_disable(self):
        # base node disabled = negative slot level → its contributions drop, others stay.
        on = _run()
        off = _run(slot_levels=(-5, 5, 5, 5))
        # assert _stat(off, "<base stat>") < _stat(on, "<base stat>")

    def test_no_trait_unchanged(self):
        none = _run(trait_id=None)
        # assert _stat(none, "<trait-specific stat>") == 0.0
