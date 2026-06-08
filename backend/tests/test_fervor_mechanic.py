"""
Tests: the Fervor Rating mechanic — Fervor's base effects (today +2% generic Critical Strike Rating
per point) scale per point of Fervor Rating AND are multiplied by Fervor Effect. Driven off the
user-set fervor_rating condition for now.
"""
import pytest
from engine.aggregator import aggregate
from engine.models import BuildInput


def _build(custom=None):
    return BuildInput(slots=[], slates=[], season="t", custom_contributions=custom or [])


def _fervor_effect(frac):
    # Feed fervor_effect_inc into the aggregated source via a custom contribution.
    return [{"stat_key": "fervor_effect_inc", "amount": frac, "text": "Fervor Effect"}]


class TestFervorCrit:
    def test_fervor_rating_grants_generic_crit(self):
        src = aggregate(_build(), {}, {}, numeric_vals={"fervor_rating": 100.0})
        assert src.total("crit_rating_inc") == pytest.approx(2.0)  # 0.02 * 100 = +200%, no Fervor Effect

    def test_fervor_130(self):
        src = aggregate(_build(), {}, {}, numeric_vals={"fervor_rating": 130.0})
        assert src.total("crit_rating_inc") == pytest.approx(2.6)  # +260%

    def test_scales_with_fervor_effect(self):
        # +50% Fervor Effect multiplies the whole base bonus: 0.02 * 100 * (1 + 0.5) = 3.0.
        src = aggregate(_build(_fervor_effect(0.5)), {}, {}, numeric_vals={"fervor_rating": 100.0})
        assert src.total("crit_rating_inc") == pytest.approx(3.0)

    def test_fervor_effect_noop_without_rating(self):
        # Fervor Effect alone (no rating) grants no crit.
        src = aggregate(_build(_fervor_effect(0.5)), {}, {}, numeric_vals={"fervor_rating": 0.0})
        assert src.total("crit_rating_inc") == 0.0

    def test_no_fervor_no_crit(self):
        assert aggregate(_build(), {}, {}, numeric_vals={}).total("crit_rating_inc") == 0.0

    def test_logged_as_source(self):
        src = aggregate(_build(), {}, {}, numeric_vals={"fervor_rating": 50.0})
        entry = next(e for e in src.source_log if e.stat == "crit_rating_inc")
        assert entry.label == "Fervor Rating" and entry.source_type == "condition"
