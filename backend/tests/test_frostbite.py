"""Frostbite ailment: Frostbite Rating → additional Cold Damage taken (base capped at 120, Frostbite Effect
scales the magnitude, Condensed Frost adds the over-120 part). Rating is auto-derived from Max Frostbite Rating
sources; enemy_frostbitten auto-applies from inflict lines; rating > 100 auto-freezes. Cold skill = icebound_beam."""
import pytest
from server import engine_stats, EngineStatsRequest
from tests.mock_build import make_request, DUAL_WEAPONS


def _gear(**stats):
    return DUAL_WEAPONS + [{"item_name": "FB", "contributions": [
        {"stat": k, "display_value": v, "unit": "", "slot": "ring", "item_name": "FB", "text": f"+{v} {k}"}
        for k, v in stats.items()]}]


def _dps(conds=None, gear=None, custom=None, supports=None):
    req = make_request("icebound_beam", 16, gear=gear, extra_conditions=conds, attached_supports=supports)
    if custom:
        req["custom_mods"] = custom
    r = engine_stats(EngineStatsRequest(**req))
    d = r.model_dump() if hasattr(r, "model_dump") else r
    return d["offense"]["total_dps"]


_BASE = _dps()


def test_no_frostbite_no_change():
    assert _dps(conds={"enemy_frostbitten": False}) == pytest.approx(_BASE)


def test_rating_from_max_frostbite_rating():
    # base 10 + 50 = rating 60 → +60% additional Cold taken (all icebound damage is cold).
    d = _dps(conds={"enemy_frostbitten": True}, gear=_gear(max_frostbite_rating_flat=50))
    assert d == pytest.approx(_BASE * 1.60, rel=1e-3)


def test_frostbite_effect_scales_magnitude():
    # rating 60, +40% Frostbite Effect → +60% × 1.4 = +84%.
    d = _dps(conds={"enemy_frostbitten": True}, gear=_gear(max_frostbite_rating_flat=50, frostbite_effect_inc=0.40))
    assert d == pytest.approx(_BASE * 1.84, rel=1e-3)


def test_base_hard_capped_at_120():
    # 10 + 120 = 130, but the BASE bonus ignores rating over 120 → +120% (not +130%).
    d = _dps(conds={"enemy_frostbitten": True}, gear=_gear(max_frostbite_rating_flat=120))
    assert d == pytest.approx(_BASE * 2.20, rel=1e-3)


def test_condensed_frost_over_120_bonus():
    # rating 130 + Condensed Frost → +120% base + (130-120)×0.35% = +3.5% → ×2.235.
    cond = _dps(conds={"enemy_frostbitten": True, "condensed_frost": True}, gear=_gear(max_frostbite_rating_flat=120))
    nocond = _dps(conds={"enemy_frostbitten": True}, gear=_gear(max_frostbite_rating_flat=120))
    assert cond == pytest.approx(_BASE * 2.235, rel=1e-3)
    assert nocond == pytest.approx(_BASE * 2.20, rel=1e-3)   # without the trait the >120 is ignored


def test_auto_apply_from_inflict_line():
    # A talent/gear/custom "Inflicts Frostbite … Cold Damage" line auto-enables enemy_frostbitten (cold skill),
    # without the user toggling it.
    d = _dps(custom=["Inflicts Frostbite when dealing Hit Cold Damage"], gear=_gear(max_frostbite_rating_flat=50))
    assert d == pytest.approx(_BASE * 1.60, rel=1e-3)


def test_rating_over_100_auto_freezes():
    # rating > 100 auto-sets enemy_frozen → Ring Blade's Frozen proc fires with NO manual enemy_frozen.
    def blade(conds=None, gear=None):
        rb = {"item_id": "icebound_beam_ring_blade_noble", "slot": 1, "level": 1, "rank": 1, "enabled": True}
        req = make_request("icebound_beam", 16, gear=gear, extra_conditions=conds, attached_supports=[rb])
        r = engine_stats(EngineStatsRequest(**req))
        d = r.model_dump() if hasattr(r, "model_dump") else r
        return next(f for f in d["offense"]["hit_forms"] if f["name"] == "Icy Blade")["dps_contribution"]
    no_frost = blade()
    high = blade(conds={"enemy_frostbitten": True}, gear=_gear(max_frostbite_rating_flat=120))
    assert high > no_frost * 1.5   # frozen proc burst fired (rating 130 > 100 → auto enemy_frozen)
