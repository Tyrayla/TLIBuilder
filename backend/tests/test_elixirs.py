"""Elixir system — enabled elixir skills grant player-wide buffs scaled by Elixir Effect (full uptime assumed).

Covers: elixir_active / elixir_skill_count auto-conditions, the per-elixir summary (Elixir Effect + granted buffs
+ timing), Elixir Effect scaling, Tenacity Dew (max elemental res), Tortoise Shell (max-life-as-ES + es_bypass
flag), Putrid Toad (Blur auto-set + gated buffs), Thunder Wood (Lucky flag, no_scale), Tailored Remedy gating,
support gems, and NYI surfacing (restoration tonics).
"""
import pytest
from server import engine_stats, EngineStatsRequest
from tests.mock_build import make_request


def _resp(elixirs=None, supports=None, conds=None, gear=None, core_talents=None):
    """chromatic_shot main in slot 1 + optional elixir skills in slots 2+."""
    req = make_request("chromatic_shot", 20, attached_supports=supports or [], gear=gear or [],
                       extra_conditions=conds or {})
    for i, eid in enumerate(elixirs or []):
        req["skills"].append({"slot": 2 + i, "skill_id": eid, "level": 20})
    if core_talents:
        req["core_talents"] = core_talents
    r = engine_stats(EngineStatsRequest(**req))
    return r if isinstance(r, dict) else r.model_dump()


def _resp_disabled(elixir_id):
    """Main skill + one DISABLED elixir in slot 2."""
    req = make_request("chromatic_shot", 20)
    req["skills"].append({"slot": 2, "skill_id": elixir_id, "level": 20, "enabled": False})
    r = engine_stats(EngineStatsRequest(**req))
    return r if isinstance(r, dict) else r.model_dump()


def _gear(pairs):
    return [{"item_name": "Test", "contributions": [
        {"stat": k, "display_value": v, "unit": "", "slot": "ring1", "item_name": "Test", "text": f"Test:{k}"}
        for k, v in pairs]}]


def _summary(resp, name):
    return next((e for e in (resp.get("elixirs") or []) if e["name"] == name), None)


# ── Auto-conditions ──────────────────────────────────────────────────────────
def test_elixir_active_autoset():
    r = _resp(elixirs=["thirst_dew"])
    auto = r.get("auto_conditions") or {}
    assert auto.get("elixir_active", {}).get("value") is True
    assert auto.get("elixir_skill_count", {}).get("value") == 1.0


def test_no_elixir_no_autoset():
    r = _resp()
    auto = r.get("auto_conditions") or {}
    assert "elixir_active" not in auto


def test_elixir_skill_count_two():
    r = _resp(elixirs=["thirst_dew", "swiftness_dew"])
    assert (r["auto_conditions"]["elixir_skill_count"]["value"]) == 2.0


# ── Summary shape ────────────────────────────────────────────────────────────
def test_summary_present_with_timing():
    s = _summary(_resp(elixirs=["swiftness_dew"]), "Swiftness Dew")
    assert s is not None
    assert s["duration"] == pytest.approx(3.0)        # base 3s, no elixir duration sources
    assert s["cooldown"] == pytest.approx(0.5)
    stats = {g["stat"] for g in s["granted"]}
    assert "movement_speed_inc" in stats


def test_restoration_surfaced_nyi():
    r = _resp(elixirs=["life_tonic"])
    texts = " ".join(x["text"] for x in (r.get("elixir_statuses") or []))
    assert "Restores" in texts


# ── Elixir Effect scaling ────────────────────────────────────────────────────
def test_thirst_dew_raises_dps():
    base = _resp()["offense"]["total_dps"]
    with_elixir = _resp(elixirs=["thirst_dew"])["offense"]["total_dps"]
    assert with_elixir > base


def test_elixir_effect_scales_buff():
    """+55% damage from Thirst Dew, scaled by +100% additional Elixir Effect → the dmg buff ~doubles."""
    plain = _summary(_resp(elixirs=["thirst_dew"]), "Thirst Dew")
    scaled = _summary(_resp(elixirs=["thirst_dew"], gear=_gear([("elixir_effect_additional", 1.0)])), "Thirst Dew")
    dmg_plain = next(g for g in plain["granted"] if g["stat"] == "dmg_inc")
    dmg_scaled = next(g for g in scaled["granted"] if g["stat"] == "dmg_inc")
    assert dmg_plain["base"] == pytest.approx(0.55)
    assert dmg_plain["amount"] == pytest.approx(0.55)          # factor 1.0 with no Elixir Effect
    assert dmg_scaled["amount"] == pytest.approx(1.10)         # ×(1 + 1.0)
    assert scaled["elixir_effect_inc"] == pytest.approx(1.0)


# ── Tenacity Dew: max elemental resistance ───────────────────────────────────
def test_tenacity_dew_raises_max_res():
    base = _resp()["defense"]
    ten = _resp(elixirs=["tenacity_dew"])["defense"]
    assert ten["fire_resist_max"] == pytest.approx(base["fire_resist_max"] + 6.0)
    assert ten["cold_resist_max"] == pytest.approx(base["cold_resist_max"] + 6.0)
    assert ten["lightning_resist_max"] == pytest.approx(base["lightning_resist_max"] + 6.0)
    # Erosion is NOT elemental — its cap is unchanged.
    assert ten["erosion_resist_max"] == pytest.approx(base["erosion_resist_max"])


def test_tenacity_dew_scales_with_effect():
    ten = _resp(elixirs=["tenacity_dew"], gear=_gear([("elixir_effect_additional", 1.0)]))["defense"]
    base = _resp()["defense"]
    # 6% base × (1 + 1.0) = 12% added to the cap.
    assert ten["fire_resist_max"] == pytest.approx(base["fire_resist_max"] + 12.0)


# ── Tortoise Shell: max-life-as-ES + es_bypass flag ──────────────────────────
def test_tortoise_shell_es_from_life():
    base = _resp()["defense"]
    ts = _resp(elixirs=["tortoise_shell_distillate"])["defense"]
    # 15% of Max Life becomes flat ES (then scaled by ES inc/additional; with none here it's ~ a flat add).
    assert ts["max_energy_shield"] > base["max_energy_shield"]
    assert ts["max_energy_shield"] >= base["max_energy_shield"] + 0.15 * base["max_life"] - 1.0


def test_es_bypass_flag_surfaced():
    s = _summary(_resp(elixirs=["tortoise_shell_distillate"]), "Tortoise Shell Distillate")
    bypass = next((g for g in s["granted"] if g["stat"] == "es_bypass_pct"), None)
    assert bypass is not None
    assert bypass["no_scale"] is True
    assert bypass["amount"] == pytest.approx(50.0)   # flag value not scaled by Elixir Effect


# ── Putrid Toad: Blur ────────────────────────────────────────────────────────
def test_putrid_toad_sets_blur():
    r = _resp(elixirs=["putrid_toad_distillate"])
    assert (r["auto_conditions"].get("blur_active") or {}).get("value") is True


# ── Thunder Wood: Lucky flag (no_scale) ──────────────────────────────────────
def test_thunder_wood_lucky_no_scale():
    s = _summary(_resp(elixirs=["thunder_wood_distillate"], gear=_gear([("elixir_effect_additional", 1.0)])),
                 "Thunder Wood Distillate")
    lucky = [g for g in s["granted"] if g["stat"].startswith("lucky_")]
    assert len(lucky) == 5
    assert all(g["no_scale"] and g["amount"] == pytest.approx(1.0) for g in lucky)


# ── Support gems ─────────────────────────────────────────────────────────────
def test_support_gem_charge_per_second():
    sup = [{"item_id": "hyper_metabolism", "slot": 2, "level": 1, "enabled": True}]
    s = _summary(_resp(elixirs=["swiftness_dew"], supports=sup), "Swiftness Dew")
    assert s["charge_per_second"] == pytest.approx(0.5)


def test_support_gem_max_charges():
    sup = [{"item_id": "medicinal_buildup", "slot": 2, "level": 1, "enabled": True}]
    s = _summary(_resp(elixirs=["swiftness_dew"], supports=sup), "Swiftness Dew")
    assert s["max_charges"] == pytest.approx(2.0)   # base 1 + 1


# ── Disabled elixir: shown but not applied ───────────────────────────────────
def test_disabled_elixir_shown_not_applied():
    r = _resp_disabled("thirst_dew")
    s = _summary(r, "Thirst Dew")
    assert s is not None and s["enabled"] is False     # still shown in the panel
    assert s["granted"]                                # with its (would-be) stats
    # Not applied: no auto elixir_active, and DPS unchanged from the no-elixir baseline.
    assert "elixir_active" not in (r.get("auto_conditions") or {})
    assert r["offense"]["total_dps"] == pytest.approx(_resp()["offense"]["total_dps"])


def test_disabled_elixir_no_max_res():
    # Tenacity Dew disabled → Fire/Cold/Lightning caps unchanged.
    base = _resp()["defense"]
    dis = _resp_disabled("tenacity_dew")["defense"]
    assert dis["fire_resist_max"] == pytest.approx(base["fire_resist_max"])


# ── Timing scaling: Skill Effect Duration + Cooldown Recovery + Max Charge ───
def test_duration_scales_with_skill_effect_duration():
    s = _summary(_resp(elixirs=["swiftness_dew"], gear=_gear([("skill_effect_duration_inc", 0.5)])), "Swiftness Dew")
    assert s["duration"] == pytest.approx(4.5)   # 3.0 × (1 + 0.5)


def test_cooldown_scales_with_cdr():
    s = _summary(_resp(elixirs=["swiftness_dew"], gear=_gear([("cdr_speed_inc", 1.0)])), "Swiftness Dew")
    assert s["cooldown"] == pytest.approx(0.25)   # 0.5 ÷ (1 + 1.0)


def test_max_charges_scales_with_global_pool():
    s = _summary(_resp(elixirs=["swiftness_dew"], gear=_gear([("max_charge_flat", 2)])), "Swiftness Dew")
    assert s["max_charges"] == pytest.approx(3.0)   # base 1 + 2
