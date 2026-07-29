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


# Pin a SUB-FULL current_life_pct so these exercise the rate math at a fixed % — the solver respects a real
# (<100%) what-if override, so the steady state doesn't move it. (A default/seeded 100% is NOT a meaningful pin
# for a consume build, so it no longer disables the solve; the steady state is covered separately.)
def test_per_second_pct_current_consume():
    r = _resp([("life_consumed_pct_current_per_sec", 0.10)], conds={"current_life_pct": 50})
    ml = r["defense"]["max_life"]
    c = r["consumption"]
    assert c["life_per_sec"] == pytest.approx(0.10 * 0.50 * ml, rel=1e-3)   # 10% of current (=50% of max)
    assert c["consumed_recently_life"] == pytest.approx(c["life_per_sec"] * 4.0, rel=1e-3)  # 4s window


def test_per_cast_consume_scales_with_aps():
    r = _resp([("life_consumed_pct_current_per_cast", 0.05)], conds={"current_life_pct": 50})
    ml = r["defense"]["max_life"]
    sps = r["offense"]["skills_per_second"]
    assert r["consumption"]["life_per_sec"] == pytest.approx(0.05 * 0.50 * ml * sps, rel=1e-3)


def test_pct_max_vs_current_at_low_life():
    # %-max consume is independent of current life; %-current scales with it.
    base = _resp([("life_consumed_pct_max_per_sec", 0.20)], conds={"current_life_pct": 50})
    cur = _resp([("life_consumed_pct_current_per_sec", 0.20)], conds={"current_life_pct": 50})
    ml = base["defense"]["max_life"]
    assert base["consumption"]["life_per_sec"] == pytest.approx(0.20 * ml, rel=1e-3)        # 20% of MAX
    assert cur["consumption"]["life_per_sec"] == pytest.approx(0.20 * 0.50 * ml, rel=1e-3)   # 20% of CURRENT (50%)


def test_net_and_verdict_unsustainable():
    # Pin a sub-full life% (respected): with no recovery the drain is net-negative and unsustainable at that %.
    r = _resp([("life_consumed_pct_current_per_sec", 0.10)], conds={"current_life_pct": 50})
    rec = r["consumption"]; rv = r["recovery"]
    cur_life = 0.50 * r["defense"]["max_life"]
    assert rv["net_life_per_sec"] == pytest.approx(-rec["life_per_sec"], rel=1e-3)   # no recovery here
    assert rv["life_sustainable"] is False
    assert rv["life_time_to_empty"] == pytest.approx(cur_life / rec["life_per_sec"], rel=1e-2)


def test_no_consumption_no_drain_full_life():
    r = _resp([("max_life_flat", 100)])
    assert r["consumption"]["life_per_sec"] == pytest.approx(0.0, abs=1e-6)
    assert r["recovery"]["life_sustainable"] is True


def test_per_use_consume_not_flagged_as_overcounted():
    # Per the Help DB, per-USE consume uses the active skill's base USE rate (correct, one skill at a time) — so a
    # normal per-use consume build is NOT flagged (the old "triggered casts over-count" flag was wrong).
    r = _resp([("life_consumed_pct_current_per_cast", 0.05)])
    assert not (r["consumption"].get("flags") or [])


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
    # Tide of the Styx: +(3-5)% damage per 4000 Life consumed → plain "damage" is INCREASED (bonus-vs-additional),
    # midpoint 4% normalized to per-1-life + the divisor N.
    assert kv("+(3-5) % damage for every 4000 Life consumed recently") == {
        "dmg_inc_per_life_consumed": round(0.04 / 4000.0, 8),
        "dmg_inc_per_life_consumed_unit": 4000}
    # The "additional damage" variant stays in the ADDITIONAL pool.
    assert kv("+(3-5) % additional damage for every 4000 Life consumed recently") == {
        "dmg_additional_per_life_consumed": round(0.04 / 4000.0, 8),
        "dmg_additional_per_life_consumed_unit": 4000}
    # Tide: +1% Attack Speed per 5000 Life consumed.
    assert kv("+1 % Attack Speed for every 5000 Life consumed recently") == {
        "attack_speed_inc_per_life_consumed": round(0.01 / 5000.0, 8),
        "attack_speed_inc_per_life_consumed_unit": 5000}
    # Compensatory Life: +(3-6)% Spell Damage per 100 Mana consumed, up to 216% → cap + divisor captured.
    out = kv("+(3-6) % Spell Damage for every 100 Mana consumed recently, up to 216 %")
    assert out["spell_dmg_inc_per_mana_consumed"] == round(0.045 / 100.0, 8)
    assert out["spell_dmg_inc_per_mana_consumed_cap"] == 2.16
    assert out["spell_dmg_inc_per_mana_consumed_unit"] == 100


def test_damage_per_consumed_lands_in_increased_not_additional():
    """End-to-end: '+X% damage per N Life consumed' feeds the INCREASED pool (generic_inc), not additional, and
    '+X% Attack Speed per N Life consumed' applies AND badges Consumed (never silently Inactive)."""
    styx = _gear([
        ("max_life_flat", 60000),
        ("life_consumed_pct_current_per_sec", 0.10),
        ("dmg_inc_per_life_consumed", 0.04 / 4000.0), ("dmg_inc_per_life_consumed_unit", 4000),
        ("attack_speed_inc_per_life_consumed", 0.01 / 5000.0), ("attack_speed_inc_per_life_consumed_unit", 5000),
    ])
    from tests.mock_build import make_request, DUAL_WEAPONS
    req = make_request("split_shot", 20, gear=DUAL_WEAPONS + styx, extra_conditions={"current_life_pct": 50})
    r = engine_stats(EngineStatsRequest(**req))
    r = r if isinstance(r, dict) else r.model_dump()
    off = r["offense"]
    assert off["generic_inc"] > 0.0            # damage-per-consumed is INCREASED
    assert off["generic_add"] == pytest.approx(1.0)   # …and NOT additional
    assert "attack_speed_inc_per_life_consumed" in set(r["consumed_stats"])  # badges Consumed, not Inactive


def test_g_flat_phys_per_consumed_parsing():
    # Stage G: flat PHYSICAL damage per N consumed. Normalized per-1-unit (flat/N); the "Stacks up to Z" cap is a
    # CONSUMED-AMOUNT cap (Z × N) shared by min+max. Scope kept honest (attack-only vs attack+spell).
    from engine.mod_parser import _parse_custom_mod_text as P
    def kv(t): return {r["stat_key"]: round(r["amount"], 8) for r in (P(t) or [])}
    # Blade-dancer's Fingers: midpoints 19.5/25.5 per 3300 Life → Attacks only, cap 170×3300.
    blade = kv("Adds (18-21) - (24-27) Physical Damage to Attacks for every 3300 Life consumed recently. Stacks up to 170 time(s)")
    assert blade == {
        "physical_attack_dmg_flat_min_per_life_consumed": round(19.5 / 3300.0, 8),
        "physical_attack_dmg_flat_max_per_life_consumed": round(25.5 / 3300.0, 8),
        "physical_dmg_flat_per_life_consumed_unit": 3300.0,
        "physical_dmg_flat_per_life_consumed_cap": 170.0 * 3300.0}
    # Glacier Caster Shield: midpoints 14/24.5 per ~1025 Mana → Attacks AND Spells, divisor 1025, cap 200×1025.
    glac = kv("Adds (13-15) - (23-26) Physical Damage to Attacks and Spells for every (1000-1050) Mana consumed recently. Stacks up to 200 time(s)")
    assert glac["physical_attack_dmg_flat_min_per_mana_consumed"] == round(14.0 / 1025.0, 8)
    assert glac["physical_spell_dmg_flat_max_per_mana_consumed"] == round(24.5 / 1025.0, 8)
    assert glac["physical_dmg_flat_per_mana_consumed_unit"] == 1025.0
    assert glac["physical_dmg_flat_per_mana_consumed_cap"] == 200.0 * 1025.0


def test_g_crit_and_compound_parsing():
    from engine.mod_parser import _parse_custom_mod_text as P
    def kv(t): return {r["stat_key"]: round(r["amount"], 8) for r in (P(t) or [])}
    # Tyrant's Iron Fist: +5% Crit Rating AND Crit Damage per ~890 Mana → both pools, per-1-mana, no cap.
    tyrant = kv("+5 % Critical Strike Rating and Critical Strike Damage for every (880-900) Mana consumed recently")
    assert tyrant == {"crit_rating_inc_per_mana_consumed": round(0.05 / 890.0, 8),
                      "crit_dmg_inc_per_mana_consumed": round(0.05 / 890.0, 8),
                      "crit_rating_inc_per_mana_consumed_unit": 890.0,
                      "crit_dmg_inc_per_mana_consumed_unit": 890.0}
    # Crimson King compound (threshold gate split off upstream): flat +50% to BOTH increased Crit Rating + Crit Damage.
    assert kv("+50 % Critical Strike Rating and Critical Strike Damage") == {
        "crit_rating_inc": 0.5, "crit_dmg_inc": 0.5}
    # Crimson King defensive (gate split off): negative additional damage taken → tracked in the dmg_taken_additional
    # pool (NOT wired into defense yet — tracking only).
    assert kv("(-50–-40) % additional damage taken") == {"dmg_taken_additional": -0.45}
    # Compensatory Life: Mana Regeneration Speed per N Mana consumed → folds into mana_regen_speed_inc (per-1-unit + N + cap).
    assert kv("+(3-4) % Mana Regeneration Speed for every 100 Mana consumed recently, up to 360 %") == {
        "mana_regen_speed_inc_per_mana_consumed": round(0.035 / 100.0, 8),
        "mana_regen_speed_inc_per_mana_consumed_unit": 100,
        "mana_regen_speed_inc_per_mana_consumed_cap": 3.6}


def test_per_n_affix_keeps_stacks_cap_as_one_clause():
    # REGRESSION: "… for every N … recently. Stacks up to M time(s)" must resolve as ONE gear clause WITH the cap,
    # not split on the period into a resolved "Adds…" + a separate "Stacks up to M" NYI line (which also broke the
    # item badge and dropped the cap). Glacier Caster Shield.
    req = make_request("chromatic_shot", 20)
    req["gear"] = [{"item_name": "Glacier", "contributions": [], "unresolved_texts": [
        "Adds 14 - 25 Physical Damage to Attacks and Spells for every 1025 Mana consumed recently. Stacks up to 200 time(s)"]}]
    r = engine_stats(EngineStatsRequest(**req))
    r = r if isinstance(r, dict) else r.model_dump()
    gm = [s for s in r["gear_mod_statuses"] if "Physical Damage" in s["text"] or "Stacks up to" in s["text"]]
    assert len(gm) == 1                                  # one status, not split
    assert gm[0]["resolved"] is True
    assert "Stacks up to 200" in gm[0]["text"]           # cap stays in the same clause
    assert "physical_dmg_flat_per_mana_consumed_cap" in gm[0]["stat_display"]   # cap captured


def test_g_flat_phys_raises_dps_and_crit_per_consumed_raises_crit():
    from tests.mock_build import DUAL_WEAPONS
    def run(mods):
        # Consume rates chosen so consumed-recently clears the per-N divisors (≥1 discrete stack): life 2000/s × 4s =
        # 8000 ≥ 3300 (Blade → 2 stacks); mana 300/s × 4s = 1200 ≥ 890 (Tyrant → 1 stack).
        g = DUAL_WEAPONS + [{"item_name": "T", "contributions": [
            {"stat": "life_consumed_flat_per_sec", "display_value": 2000, "unit": "", "slot": "helmet", "item_name": "T", "text": "d"},
            {"stat": "mana_consumed_flat_per_sec", "display_value": 300, "unit": "", "slot": "helmet", "item_name": "T", "text": "m"},
            {"stat": "mana_regen_flat", "display_value": 99999, "unit": "", "slot": "helmet", "item_name": "T", "text": "r"}]}]
        req = make_request("berserking_blade", 20, gear=g, extra_conditions={"dual_wielding": True})
        req["custom_mods"] = mods
        r = engine_stats(EngineStatsRequest(**req))
        return r if isinstance(r, dict) else r.model_dump()
    base = run([])
    blade = run(["Adds (18-21) - (24-27) Physical Damage to Attacks for every 3300 Life consumed recently. Stacks up to 170 time(s)"])
    tyrant = run(["+5 % Critical Strike Rating and Critical Strike Damage for every (880-900) Mana consumed recently"])
    assert base["recovery"]["consumed_recently_life"] > 0 and base["recovery"]["consumed_recently_mana"] > 0
    assert blade["offense"]["total_dps"] > base["offense"]["total_dps"]          # flat phys per Life consumed
    # REGRESSION (bug-221): the flat must land in the REAL physical_attack_dmg_flat source stat (folds into damage +
    # shows a source in the breakdown), not a display-only local var (which raised Added Min/Max but not DPS, 0 sources).
    _pf = blade["stats"].get("physical_attack_dmg_flat_min")
    assert _pf and _pf["total"] > 0 and len(_pf["sources"]) >= 1
    # Discrete "for every N" stacks (not fractional): 8000 Life recently / 3300 = floor 2 stacks × 19.5 min = 39.
    assert _pf["total"] == pytest.approx(2 * 19.5)
    assert tyrant["offense"]["crit_chance"] > base["offense"]["crit_chance"]      # +Crit Rating per Mana consumed
    assert tyrant["offense"]["crit_multiplier"] > base["offense"]["crit_multiplier"]  # +Crit Damage per Mana consumed
    # NUMERIC PIN (engine refactor: post-loop fold in offense.py → in-loop injection into crit_dmg_inc in compute.py).
    # consumed_recently_mana = 300/s × 4s = 1200; floor(1200/890) = 1 stack × 5% = +0.05 crit_dmg_inc → base 1.50 + 0.05.
    # EXACT pin (not just ">") proves the in-loop injection is byte-identical to the old post-loop fold.
    assert tyrant["offense"]["crit_multiplier"] == pytest.approx(1.55)
    _cdi = tyrant["stats"]["crit_dmg_inc"]
    assert _cdi["total"] == pytest.approx(0.05)
    assert len(_cdi["sources"]) >= 1                       # the labeled "Mana Consumed" source now appears in-loop
    assert "crit_dmg_inc_per_mana_consumed" in set(tyrant["consumed_stats"])  # badges Consumed, not Inactive


def test_per_n_consumed_is_discrete_floored():
    # "For every N consumed recently" procs in whole stacks (floor), not fractionally. Below 1 full N → no benefit.
    from tests.mock_build import DUAL_WEAPONS
    def run(consume_per_sec):
        g = DUAL_WEAPONS + [{"item_name": "T", "contributions": [
            {"stat": "mana_consumed_flat_per_sec", "display_value": consume_per_sec, "unit": "", "slot": "helmet", "item_name": "T", "text": "m"},
            {"stat": "mana_regen_flat", "display_value": 99999, "unit": "", "slot": "helmet", "item_name": "T", "text": "r"}]}]
        req = make_request("chromatic_shot", 20, gear=g)
        req["gear"] = list(req["gear"]) + [{"item_name": "Glacier", "contributions": [], "unresolved_texts": [
            "Adds 23 - 28 Physical Damage to Attacks and Spells for every 1004 Mana consumed recently. Stacks up to 200 time(s)"]}]
        r = engine_stats(EngineStatsRequest(**req))
        return r if isinstance(r, dict) else r.model_dump()
    # 250/s × 4s = 1000 recently < 1004 → 0 stacks → no flat; 600/s × 4s = 2400 → floor 2 stacks × 23 = 46.
    below = run(250)["stats"].get("physical_spell_dmg_flat_min")
    assert (below is None) or below["total"] == pytest.approx(0.0)
    two = run(600)["stats"]["physical_spell_dmg_flat_min"]
    assert two["total"] == pytest.approx(2 * 23)


def test_compensatory_spell_dmg_per_mana_consumed_raises_spell_dps():
    # Compensatory Life: increased Spell Damage per N Mana consumed folds into the REAL spell_dmg_inc (with a source)
    # and raises a spell skill's DPS. Needs a mana consume source so consumed_recently_mana clears the divisor.
    def run(mods):
        g = [{"item_name": "T", "contributions": [
            {"stat": "mana_consumed_flat_per_sec", "display_value": 600, "unit": "", "slot": "helmet", "item_name": "T", "text": "m"},
            {"stat": "mana_regen_flat", "display_value": 99999, "unit": "", "slot": "helmet", "item_name": "T", "text": "r"}]}]
        req = make_request("chromatic_shot", 20, gear=g)
        req["custom_mods"] = mods
        r = engine_stats(EngineStatsRequest(**req))
        return r if isinstance(r, dict) else r.model_dump()
    base = run([])
    comp = run(["+5 % Spell Damage for every 100 Mana consumed recently, up to 216 %"])
    assert base["recovery"]["consumed_recently_mana"] > 0
    assert comp["offense"]["total_dps"] > base["offense"]["total_dps"]
    sdi = comp["stats"].get("spell_dmg_inc")
    assert sdi and sdi["total"] > 0 and len(sdi["sources"]) >= 1     # folded into the real stat, shows a source
    # 600/s × 4s = 2400 consumed → floor 2400/100 = 24 stacks × 5% = 120% increased spell damage.
    assert sdi["total"] == pytest.approx(1.20)


def test_compensatory_mana_regen_per_mana_consumed_raises_regen():
    def run(mods):
        g = [{"item_name": "T", "contributions": [
            {"stat": "mana_consumed_flat_per_sec", "display_value": 600, "unit": "", "slot": "helmet", "item_name": "T", "text": "m"}]}]
        req = make_request("chromatic_shot", 20, gear=g)
        req["custom_mods"] = mods
        r = engine_stats(EngineStatsRequest(**req))
        return r if isinstance(r, dict) else r.model_dump()
    base = run([])
    comp = run(["+5 % Mana Regeneration Speed for every 100 Mana consumed recently, up to 360 %"])
    assert comp["recovery"]["mana_regen_per_sec"] > base["recovery"]["mana_regen_per_sec"]


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


def test_seeded_full_life_does_not_disable_solve():
    # REGRESSION: the frontend seeds current_life_pct=100 into every build. That default/full value must NOT count
    # as a what-if pin that disables the steady-state solve — it did, so consume builds always read recovery at
    # full Life where missing-based regain is 0, and showed "unsustainable" even with regain that would stabilize
    # them. With a missing-based regain the build settles below full Life and is sustainable.
    r = _resp([("life_consumed_pct_max_per_sec", 0.20), ("life_regain_inc", 2.0)],
              conds={"current_life_pct": 100})   # the seeded full-life default the frontend always sends
    ac = r.get("auto_conditions") or {}
    assert ac["current_life_pct"]["source"] == "Consumption steady state"   # solve ran despite the seeded 100
    assert ac["current_life_pct"]["value"] < 100.0                          # settled below full Life
    assert r["recovery"]["life_sustainable"] is True                        # regain closes the gap
    assert r["recovery"]["steady_life_pct"] < 100.0


def test_manual_life_pct_overrides_solve():
    # A user-pinned current_life_pct is respected (what-if override) — the solver does NOT move it.
    r = _resp([("life_consumed_pct_current_per_sec", 0.50), ("life_regen_flat", 300)],
              conds={"current_life_pct": 80})
    ac = r.get("auto_conditions") or {}
    assert ac.get("current_life_pct", {}).get("source") != "Consumption steady state"


def test_base_mana_regen_present():
    # Every character has baseline Mana Regen (Help DB): 7/s + 1.75% Max Mana/s. Present on all builds.
    r = _resp([("max_life_flat", 100)])
    ml = r["defense"]["max_mana"]
    assert r["recovery"]["base_mana_regen_per_sec"] == pytest.approx(7.0 + 0.0175 * ml, rel=1e-6)
    assert r["recovery"]["mana_regen_per_sec"] >= r["recovery"]["base_mana_regen_per_sec"]


def test_steady_state_mana_solves_and_verdict():
    # Stage F: a mana-consume build solves the steady-state Mana % independently of Life.
    # A huge FLAT Mana drain (>> base regen) → death spiral → mana% clamps to 0, unsustainable. (A %-current drain
    # no longer reaches 0: as Mana falls the drain shrinks below the always-on base regen, so it settles >0.)
    # (steady=0 is filtered out of auto_conditions by _is_active, so assert the steady/verdict fields directly.)
    r = _resp([("mana_consumed_flat_per_sec", 100000)])
    assert r["recovery"]["steady_mana_pct"] == pytest.approx(0.0, abs=1.0)
    assert r["recovery"]["mana_sustainable"] is False
    # With enough flat Mana regen it settles sustainably (here regen beats max drain → stays ~full).
    r2 = _resp([("mana_consumed_pct_current_per_sec", 0.20), ("mana_regen_flat", 100000)])
    assert r2["recovery"]["mana_sustainable"] is True
    assert r2["recovery"]["net_es_per_sec"] == pytest.approx(0.0, abs=1e-6)   # ES untouched (no ES consume)


def test_steady_state_es_solves_to_equilibrium():
    # Stage F: ES self-consume + missing-based Shield Regain settles ES below full (net ≈ 0).
    # 20%/s current-ES drain, 1000 Max ES, strong Shield Regain → equilibrium at ~75% (regain fills the gap).
    r = _resp([("energy_shield_consumed_pct_current_per_sec", 0.20),
               ("max_energy_shield_flat", 1000), ("energy_shield_regain_inc", 2.0)])
    ac = r.get("auto_conditions") or {}
    solved = ac["current_es_pct"]["value"]
    assert ac["current_es_pct"]["source"] == "Consumption steady state"
    assert 60 < solved < 90
    assert r["recovery"]["net_es_per_sec"] == pytest.approx(0.0, abs=5.0)
    assert r["recovery"]["es_sustainable"] is True
    assert r["recovery"]["steady_es"] == pytest.approx(solved / 100.0 * 1000.0, rel=0.05)


def test_consume_pool_solve_is_independent():
    # A life-only consume build never engages the Mana/ES solver (their % stays default).
    r = _resp([("life_consumed_pct_current_per_sec", 0.50), ("life_regen_flat", 300)])
    ac = r.get("auto_conditions") or {}
    assert ac["current_life_pct"]["source"] == "Consumption steady state"
    assert ac.get("current_mana_pct", {}).get("source") != "Consumption steady state"
    assert ac.get("current_es_pct", {}).get("source") != "Consumption steady state"


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
        # Pin a sub-full life% (respected) so the attack-USE rate math is measured at a fixed %.
        req = make_request(skill, 20, gear=g, extra_conditions={"current_life_pct": 50, "dual_wielding": True})
        r = engine_stats(EngineStatsRequest(**req))
        return r if isinstance(r, dict) else r.model_dump()
    atk = run("berserking_blade")                  # attack → consume fires at sps × 2% current
    sps = atk["offense"]["skills_per_second"]
    assert atk["consumption"]["life_per_sec"] == pytest.approx(0.02 * 0.50 * atk["defense"]["max_life"] * sps, rel=1e-2)
    spell = run("chromatic_shot")                  # spell → no attack use → no attack-scoped consume
    assert spell["consumption"]["life_per_sec"] == pytest.approx(0.0, abs=1e-6)


def test_current_consume_uses_unreserved_max_uses_raw():
    # "% of current" consume is taken against UNRESERVED Life (Max − Sealed); "% of Max" still uses raw Max.
    from engine.consumption import calculate_consumption

    class _Src:
        def __init__(self, vals): self.v = vals
        def total(self, k): return self.v.get(k, 0.0)
    cur = _Src({"max_life": 1000.0, "life_consumed_pct_current_per_sec": 0.08})
    assert calculate_consumption(cur, condition_state={"current_life_pct": 100},
                                 reservation={"sealed_life": 300}).life_per_sec == pytest.approx(56.0)   # 8% of 700
    assert calculate_consumption(cur, condition_state={"current_life_pct": 100}).life_per_sec == pytest.approx(80.0)
    mx = _Src({"max_life": 1000.0, "life_consumed_pct_max_per_sec": 0.08})
    assert calculate_consumption(mx, condition_state={"current_life_pct": 100},
                                 reservation={"sealed_life": 300}).life_per_sec == pytest.approx(80.0)   # raw Max


def test_consumed_recently_threshold_gate_translation():
    # Crimson King / Awakening Skull gate text → the registered numeric conditions.
    from server import _translate_condition_expr as T
    assert T("if you have consumed more than +100 % of Max Life recently") == {
        "key": "life_consumed_recently_pct_max", "op": ">", "value": 100.0}
    assert T("if you have consumed more than 120 % of Max Life recently")["value"] == 120.0
    assert T("if you have consumed more than 100 % Life recently")["key"] == "life_consumed_recently_pct_max"
    assert T("if more than 15000 Life has been consumed recently") == {
        "key": "life_consumed_recently_flat", "op": ">", "value": 15000.0}


def test_consumed_recently_gate_fires_above_threshold():
    # A "consumed > 100% Max Life recently" gated bonus fires once consumed-recently crosses that, and not below.
    # 40%/s × 4s window = 160% of Max consumed recently (above the 100% gate); 10%/s = 40% (below).
    def run(consume_pct, mod):
        req = make_request("chromatic_shot", 20, gear=_gear([("life_consumed_pct_max_per_sec", consume_pct)]))
        if mod:
            req["custom_mods"] = mod
        r = engine_stats(EngineStatsRequest(**req))
        return (r if isinstance(r, dict) else r.model_dump())["offense"]["total_dps"]
    mod = ["+50 % damage if you have consumed more than 100 % of Max Life recently"]
    base = run(0.40, None)
    gated_hi = run(0.40, mod)                 # 160% recently → gate fires
    gated_lo = run(0.10, mod)                 # 40% recently → below threshold, no fire
    assert gated_hi > base * 1.4              # ~+50%
    assert gated_lo == pytest.approx(run(0.10, None), rel=1e-3)   # unchanged below threshold


def test_attack_speed_per_consumed_feedback_converges():
    # Tide of the Styx: +Attack Speed per Life consumed recently is a feedback loop (AS → more attack uses → more
    # Life consumed → more AS). It must converge (damped + quantized) and raise sps/DPS for an attack build.
    from tests.mock_build import DUAL_WEAPONS
    conds = {"current_life_pct": 50, "dual_wielding": True}   # pinned sub-full so the rate is fixed for the feedback

    def run(extra):
        g = DUAL_WEAPONS + [{"item_name": "T", "contributions": [
            {"stat": k, "display_value": v, "unit": "", "slot": "ring1", "item_name": "T", "text": "T"}
            for k, v in ([("life_consumed_pct_current_per_attack_use", 0.05)] + extra)]}]
        r = engine_stats(EngineStatsRequest(**make_request("berserking_blade", 20, gear=g, extra_conditions=conds)))
        return r if isinstance(r, dict) else r.model_dump()
    base = run([])
    # 1% AS per 100 Life consumed (real Tide carries the per-unit value AND its "_unit" divisor, like the mod parser emits).
    tide = run([("attack_speed_inc_per_life_consumed", 0.01 / 100), ("attack_speed_inc_per_life_consumed_unit", 100)])
    assert tide["offense"]["skills_per_second"] > base["offense"]["skills_per_second"]   # feedback raised sps
    assert tide["offense"]["total_dps"] > base["offense"]["total_dps"]

    # CONSISTENCY invariant (regression for the lagging-consumed bug): after convergence the Tide attack-speed
    # contribution must match the FINAL consumed_recently, not a damped value that lags behind it when the fire
    # rate jumps a breakpoint mid-loop (which used to under-relax the feedback and terminate the loop early —
    # e.g. showing +24% off a stale 120k while consumed_recently was really 186k → should have been +37%). The
    # ONLY attack_speed_inc difference between the two runs is the Tide feedback fold.
    from engine.consumption import floored_consumed
    _as_inc = lambda r: (r["stats"].get("attack_speed_inc") or {}).get("total", 0.0)
    tide_term = _as_inc(tide) - _as_inc(base)                            # the only AS-inc difference = the fold
    consumed = tide["consumption"]["life_per_sec"] * 4.0                 # "recently" = rate × 4s window
    expected = floored_consumed(consumed, 100) * (0.01 / 100)            # floored to whole 100-Life chunks × per
    assert tide_term == pytest.approx(expected, rel=0.03), (tide_term, expected, consumed)


def test_custom_mod_consume_resolves():
    # A consume line with an inline use-scope ("when you use Attack Skills") must resolve as a CUSTOM MOD too — the
    # custom-mod path tries the full text first (like gear/talent nodes), not split-condition-first which dropped it.
    from tests.mock_build import DUAL_WEAPONS
    req = make_request("berserking_blade", 20, gear=DUAL_WEAPONS,
                       extra_conditions={"current_life_pct": 50, "dual_wielding": True})
    req["custom_mods"] = ["Consumes 2 % of current Life when you use Attack Skills"]
    r = engine_stats(EngineStatsRequest(**req))
    r = r if isinstance(r, dict) else r.model_dump()
    st = next(s for s in r["custom_mod_statuses"] if "Consumes" in s["text"])
    assert st["resolved"] is True
    assert r["consumption"]["life_per_sec"] > 0


def test_mana_boil_override_and_empower_scaling():
    # Mana Boil's crawler-mangled data is overridden: consume = 3% Max Mana/s (all ranks), Euphoria = +16.65%
    # additional Spell Damage at Lv20. BOTH scale with Empower Effect. The consume routes into the consumption
    # subsystem (no longer dropped as empower 'noise'); no line is left Unrecognized.
    def run(emp_eff):
        gear = ([{"item_name": "T", "contributions": [{"stat": "empower_effect_inc", "display_value": emp_eff,
                  "unit": "", "slot": "ring1", "item_name": "T", "text": "ee"}]}] if emp_eff else [])
        req = make_request("chromatic_shot", 20, gear=gear)
        req["skills"] = list(req["skills"]) + [{"slot": 2, "skill_id": "mana_boil", "level": 20, "enabled": True}]
        r = engine_stats(EngineStatsRequest(**req))
        return r if isinstance(r, dict) else r.model_dump()
    r = run(0)
    e = next(x for x in r["empowers"] if x["name"] == "Mana Boil")
    assert e["nyi"] == []                                       # all lines resolved (was 3x Unrecognized)
    gr = {x["stat"]: x["amount"] for x in e["granted"]}
    assert gr["spell_dmg_additional"] == pytest.approx(0.1665)
    assert gr["mana_consumed_pct_max_per_sec"] == pytest.approx(0.03)
    # mana_per_sec is the CONSUME drain only (skill cost is a separate line, not consumption).
    assert r["consumption"]["mana_per_sec"] == pytest.approx(0.03 * r["defense"]["max_mana"])
    # Both effects scale with Empower Effect (+50% → ×1.5).
    e50 = next(x for x in run(0.5)["empowers"] if x["name"] == "Mana Boil")
    gr50 = {x["stat"]: x["amount"] for x in e50["granted"]}
    assert gr50["spell_dmg_additional"] == pytest.approx(0.1665 * 1.5)
    assert gr50["mana_consumed_pct_max_per_sec"] == pytest.approx(0.045)


def test_mana_boil_warns_not_disables_when_mana_unsustainable():
    # We DON'T auto-disable Mana Boil's Euphoria at 0 Mana — we WARN when Mana is unsustainable so the user sees the
    # buff would turn off in play (e.g. once skill costs spiral Mana down). Buff stays applied; warning surfaces.
    def run(extra_drain):
        # Big baseline Mana Regen so run(0) is sustainable despite Mana Boil + the skill's own mana cost; the huge
        # extra drain still overwhelms it (unsustainable). Isolates the warn-vs-sustainable contrast.
        contribs = [{"stat": "mana_regen_flat", "display_value": 500, "unit": "", "slot": "ring1", "item_name": "T", "text": "r"}]
        if extra_drain:
            contribs.append({"stat": "mana_consumed_flat_per_sec", "display_value": extra_drain,
                             "unit": "", "slot": "ring1", "item_name": "T", "text": "d"})
        g = [{"item_name": "T", "contributions": contribs}]
        req = make_request("chromatic_shot", 20, gear=g)
        req["skills"] = list(req["skills"]) + [{"slot": 2, "skill_id": "mana_boil", "level": 20, "enabled": True}]
        r = engine_stats(EngineStatsRequest(**req))
        return r if isinstance(r, dict) else r.model_dump()
    def warns(r): return [w for w in (r.get("warnings") or []) if w.get("kind") == "mana_deactivation"]
    sus = run(0)
    assert sus["recovery"]["mana_sustainable"] is True
    assert warns(sus) == []                                          # sustainable → no warning
    uns = run(100000)                                                # huge Mana drain → unsustainable
    assert uns["recovery"]["mana_sustainable"] is False
    w = warns(uns)
    assert len(w) == 1 and "Mana Boil" in w[0]["text"]              # warned, not disabled
    # The Euphoria buff is still applied (not auto-removed).
    e = next(x for x in uns["empowers"] if x["name"] == "Mana Boil")
    assert any(g["stat"] == "spell_dmg_additional" for g in e["granted"])


def test_mana_boil_override_staleness_flags():
    from engine.skill_overrides import apply_skill_overrides
    _corrupt = "Consumes 16.65 % additional Spell Damage while the skill lasts Mana every second."
    def mk():
        return {"mana_boil": {"item_id": "mana_boil", "detailed_description": [_corrupt],
                              "raw_text": _corrupt, "simple_description": []}}
    s = mk()
    assert apply_skill_overrides(s, "SS12") == []                                  # authored season, snippet present
    assert "Consumes 3 % of Max Mana every second" in s["mana_boil"]["detailed_description"]
    assert any("re-validate" in r for r in apply_skill_overrides(mk(), "SS13"))     # new season → flag, still applied
    # Source changed (corrupted snippet gone) → override SKIPPED + flagged (don't re-break corrected data).
    s3 = {"mana_boil": {"item_id": "mana_boil", "detailed_description": ["Consumes 3 % of Max Mana every second"],
                        "raw_text": "Consumes 3 % of Max Mana every second", "simple_description": []}}
    assert any("manual review" in r for r in apply_skill_overrides(s3, "SS12"))


def test_mana_consume_independent_pool():
    r = _resp([("mana_consumed_flat_per_sec", 50)])
    c = r["consumption"]
    # mana_per_sec is the 50/s affix consume only (skill cost is a separate, non-consumption drain).
    assert c["mana_per_sec"] == pytest.approx(50.0, rel=1e-3)
    assert c["life_per_sec"] == pytest.approx(0.0, abs=1e-6)
    assert r["recovery"]["mana_sustainable"] is False
