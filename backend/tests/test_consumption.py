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


# Pin current_life_pct so these exercise the rate math at a fixed % (otherwise C solves the steady state, which
# moves life% and is covered separately in the steady-state tests).
def test_per_second_pct_current_consume():
    r = _resp([("life_consumed_pct_current_per_sec", 0.10)], conds={"current_life_pct": 100})
    ml = r["defense"]["max_life"]
    c = r["consumption"]
    assert c["life_per_sec"] == pytest.approx(0.10 * ml, rel=1e-3)          # 10% of current (=max at 100%)
    assert c["consumed_recently_life"] == pytest.approx(c["life_per_sec"] * 4.0, rel=1e-3)  # 4s window


def test_per_cast_consume_scales_with_aps():
    r = _resp([("life_consumed_pct_current_per_cast", 0.05)], conds={"current_life_pct": 100})
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
    # Pin at full life: with no recovery the drain is net-negative and unsustainable at that assumed %.
    r = _resp([("life_consumed_pct_current_per_sec", 0.10)], conds={"current_life_pct": 100})
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
    # Talent node: "when you use Attack Skills" is per-USE and ATTACK-scoped (not per-second, not generic).
    assert one("Consumes 2 % of current Life when you use Attack Skills") == {("life_consumed_pct_current_per_attack_use", 0.02)}
    # Ghost Slaughter: % current Life AND Energy Shield per second → both pools, per-second.
    assert one("Consumes (10-12) % of current Life and Energy Shield per second while Fervor is active") == {
        ("life_consumed_pct_current_per_sec", 0.11), ("energy_shield_consumed_pct_current_per_sec", 0.11)}
    # Strange Snow: % Max Life, Interval 1s → % max per second.
    assert ("life_consumed_pct_max_per_sec", 0.2) in one(
        "Consumes 20 % of Max Life and inflicts 50 Affliction to nearby enemies when at Full Life. Interval: 1s")
    # Mana Boil-style flat mana per second.
    assert one("Consumes 16 Mana every second") == {("mana_consumed_flat_per_sec", 16.0)}


def test_per_n_consumed_consumer_parsing():
    from engine.mod_parser import _parse_custom_mod_text as P
    def kv(text):
        return {r["stat_key"]: round(r["amount"], 8) for r in (P(text) or [])}
    # Tide of the Styx: +(3-5)% damage per 4000 Life consumed → midpoint 4% normalized to per-1-life (no cap).
    assert kv("+(3-5) % damage for every 4000 Life consumed recently") == {
        "dmg_additional_per_life_consumed": round(0.04 / 4000.0, 8)}
    # Tide: +1% Attack Speed per 5000 Life consumed.
    assert kv("+1 % Attack Speed for every 5000 Life consumed recently") == {
        "attack_speed_inc_per_life_consumed": round(0.01 / 5000.0, 8)}
    # Compensatory Life: +(3-6)% Spell Damage per 100 Mana consumed, up to 216% → cap captured.
    out = kv("+(3-6) % Spell Damage for every 100 Mana consumed recently, up to 216 %")
    assert out["spell_dmg_inc_per_mana_consumed"] == round(0.045 / 100.0, 8)
    assert out["spell_dmg_inc_per_mana_consumed_cap"] == 2.16


def test_steady_state_life_solves_to_equilibrium():
    # 50% current-Life/sec drain + 300/s regen → settles where recovery == consumption (net ≈ 0), sustainable.
    r = _resp([("life_consumed_pct_current_per_sec", 0.50), ("life_regen_flat", 300)])
    ac = r.get("auto_conditions") or {}
    solved = ac["current_life_pct"]["value"]
    assert ac["current_life_pct"]["source"] == "Consumption steady state"
    assert 40 < solved < 60                              # ~49.5% (300 = 0.5 × L × maxlife)
    assert r["recovery"]["net_life_per_sec"] == pytest.approx(0.0, abs=5.0)
    assert r["recovery"]["life_sustainable"] is True
    # EHP rides the steady pool (≈ solved% × max), not max life.
    assert r["recovery"]["ehp_life"] == pytest.approx(solved / 100.0 * r["defense"]["max_life"], rel=0.05)


def test_steady_state_death_spiral_clamps_to_zero():
    # Heavy drain, no recovery → no equilibrium → life% clamps to 0 (steady pool/EHP ≈ 0), unsustainable.
    r = _resp([("life_consumed_pct_current_per_sec", 0.50)])
    assert r["recovery"]["ehp_life"] == pytest.approx(0.0, abs=1.0)
    assert r["recovery"]["life_sustainable"] is False


def test_manual_life_pct_overrides_solve():
    # A user-pinned current_life_pct is respected (what-if override) — the solver does NOT move it.
    r = _resp([("life_consumed_pct_current_per_sec", 0.50), ("life_regen_flat", 300)],
              conds={"current_life_pct": 80})
    ac = r.get("auto_conditions") or {}
    assert ac.get("current_life_pct", {}).get("source") != "Consumption steady state"


def test_damage_per_life_consumed_raises_dps():
    base = _resp([("life_consumed_pct_current_per_sec", 0.50), ("life_regen_flat", 300)])
    tide = _resp([("life_consumed_pct_current_per_sec", 0.50), ("life_regen_flat", 300),
                  ("dmg_additional_per_life_consumed", 0.05 / 4000.0)])  # Tide: +5% per 4000 Life
    assert tide["offense"]["total_dps"] > base["offense"]["total_dps"]


def test_no_consumption_leaves_life_pct_untouched():
    # Builds without any consume source never engage the solver (current_life_pct stays the default/user value).
    r = _resp([("max_life_flat", 100)])
    assert (r.get("auto_conditions") or {}).get("current_life_pct", {}).get("source") != "Consumption steady state"


def test_attack_scoped_node_resolves_and_scopes():
    # The warrior node "Consumes 2% of current Life when you use Attack Skills" must RESOLVE (was NYI) — the
    # condition split + untranslatable gate previously dropped it — and route to the attack-USE-scoped stat.
    from engine.mod_parser import _parse_custom_mod_text as P
    from engine.core_talent_resolver import _classify_effect
    from server import _translate_condition_expr
    txt = "Consumes 2 % of current Life when you use Attack Skills"
    assert P(txt) == [{"stat_key": "life_consumed_pct_current_per_attack_use", "amount": 0.02, "text": txt}]
    cls = _classify_effect(txt, P, _translate_condition_expr)
    assert cls["kind"] == "stat"   # resolved, not unresolved
    assert cls["contribs"][0]["stat_key"] == "life_consumed_pct_current_per_attack_use"


def test_attack_scoped_consume_only_fires_for_attacks():
    # Attack-USE-scoped consume uses the attack skill's use rate and only fires when the active skill is an attack.
    from tests.mock_build import DUAL_WEAPONS
    g = DUAL_WEAPONS + [{"item_name": "T", "contributions": [
        {"stat": "life_consumed_pct_current_per_attack_use", "display_value": 0.02, "unit": "", "slot": "ring1",
         "item_name": "T", "text": "T"}]}]

    def run(skill):
        req = make_request(skill, 20, gear=g, extra_conditions={"current_life_pct": 100, "dual_wielding": True})
        r = engine_stats(EngineStatsRequest(**req))
        return r if isinstance(r, dict) else r.model_dump()
    atk = run("berserking_blade")                  # attack → consume fires at aps × 2% current
    aps = atk["offense"]["attacks_per_second"]
    assert atk["consumption"]["life_per_sec"] == pytest.approx(0.02 * atk["defense"]["max_life"] * aps, rel=1e-2)
    spell = run("chromatic_shot")                  # spell → no attack use → no attack-scoped consume
    assert spell["consumption"]["life_per_sec"] == pytest.approx(0.0, abs=1e-6)


def test_mana_consume_independent_pool():
    r = _resp([("mana_consumed_flat_per_sec", 50)])
    assert r["consumption"]["mana_per_sec"] == pytest.approx(50.0, rel=1e-3)
    assert r["consumption"]["life_per_sec"] == pytest.approx(0.0, abs=1e-6)
    assert r["recovery"]["mana_sustainable"] is False
