"""Self-consume drains (Stage B): life/mana/ES consumed per second, the rolling "consumed recently" total
(rate × 4s window), and the net-sustain + sustainability verdict. The steady-state life%-solve (Stage C) is
separate; here current_life_pct is the assumed input.
"""
import pytest
from server import engine_stats, EngineStatsRequest
from tests.mock_build import make_request


def _gear(pairs):
    return [{"item_name": "T", "contributions": [
        {"stat": k, "display_value": v, "unit": "", "slot": "ring1", "item_name": "T", "text": f"T:{k}"}
        for k, v in pairs]}]


def _resp(stats, conds=None):
    req = make_request("chromatic_shot", 20, gear=_gear(stats), extra_conditions=conds or {})
    r = engine_stats(EngineStatsRequest(**req))
    return r if isinstance(r, dict) else r.model_dump()


def test_per_second_pct_current_consume():
    r = _resp([("life_consumed_pct_current_per_sec", 0.10)])
    ml = r["defense"]["max_life"]
    c = r["consumption"]
    assert c["life_per_sec"] == pytest.approx(0.10 * ml, rel=1e-3)          # 10% of current (=max at 100%)
    assert c["consumed_recently_life"] == pytest.approx(c["life_per_sec"] * 4.0, rel=1e-3)  # 4s window


def test_per_cast_consume_scales_with_aps():
    r = _resp([("life_consumed_pct_current_per_cast", 0.05)])
    ml = r["defense"]["max_life"]
    aps = r["offense"]["attacks_per_second"]
    assert r["consumption"]["life_per_sec"] == pytest.approx(0.05 * ml * aps, rel=1e-3)


def test_pct_max_vs_current_at_low_life():
    # %-max consume is independent of current life; %-current scales with it.
    base = _resp([("life_consumed_pct_max_per_sec", 0.20)], conds={"current_life_pct": 50})
    cur = _resp([("life_consumed_pct_current_per_sec", 0.20)], conds={"current_life_pct": 50})
    ml = base["defense"]["max_life"]
    assert base["consumption"]["life_per_sec"] == pytest.approx(0.20 * ml, rel=1e-3)        # 20% of MAX
    assert cur["consumption"]["life_per_sec"] == pytest.approx(0.20 * 0.50 * ml, rel=1e-3)   # 20% of CURRENT (50%)


def test_net_and_verdict_unsustainable():
    r = _resp([("life_consumed_pct_current_per_sec", 0.10)])
    rec = r["consumption"]; rv = r["recovery"]
    assert rv["net_life_per_sec"] == pytest.approx(-rec["life_per_sec"], rel=1e-3)   # no recovery here
    assert rv["life_sustainable"] is False
    assert rv["life_time_to_empty"] == pytest.approx(r["defense"]["max_life"] / rec["life_per_sec"], rel=1e-2)


def test_no_consumption_no_drain_full_life():
    r = _resp([("max_life_flat", 100)])
    assert r["consumption"]["life_per_sec"] == pytest.approx(0.0, abs=1e-6)
    assert r["recovery"]["life_sustainable"] is True


def test_use_vs_cast_flag_surfaced():
    # Any per-cast/use consume + a cast rate → the use-vs-cast approximation is flagged (not silent).
    r = _resp([("life_consumed_pct_current_per_cast", 0.05)])
    assert any("use-vs-cast" in f for f in (r["consumption"].get("flags") or []))
    r2 = _resp([("life_consumed_pct_current_per_sec", 0.10)])   # per-second only → no flag
    assert not (r2["consumption"].get("flags") or [])


def test_consume_source_affix_parsing():
    from engine.mod_parser import _parse_custom_mod_text as P
    def one(text):
        return {(r["stat_key"], round(r["amount"], 4)) for r in (P(text) or [])}
    # Blade-dancer's Fingers: % current Life on skill use → per-cast.
    assert one("Consumes (5-10) % of current Life on skill use") == {("life_consumed_pct_current_per_cast", 0.075)}
    # Ghost Slaughter: % current Life AND Energy Shield per second → both pools, per-second.
    assert one("Consumes (10-12) % of current Life and Energy Shield per second while Fervor is active") == {
        ("life_consumed_pct_current_per_sec", 0.11), ("energy_shield_consumed_pct_current_per_sec", 0.11)}
    # Strange Snow: % Max Life, Interval 1s → % max per second.
    assert ("life_consumed_pct_max_per_sec", 0.2) in one(
        "Consumes 20 % of Max Life and inflicts 50 Affliction to nearby enemies when at Full Life. Interval: 1s")
    # Mana Boil-style flat mana per second.
    assert one("Consumes 16 Mana every second") == {("mana_consumed_flat_per_sec", 16.0)}
    # Consumer line ("for every N consumed") must NOT be mistaken for a source.
    assert not P("+(3-5) % damage for every 4000 Life consumed recently")


def test_mana_consume_independent_pool():
    r = _resp([("mana_consumed_flat_per_sec", 50)])
    assert r["consumption"]["mana_per_sec"] == pytest.approx(50.0, rel=1e-3)
    assert r["consumption"]["life_per_sec"] == pytest.approx(0.0, abs=1e-6)
    assert r["recovery"]["mana_sustainable"] is False
