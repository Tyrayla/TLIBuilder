"""Restoration/recovery DPS hooks (Licorice Note): Elixir of Immortality (excess restoration → Temporary
Life/Mana → +damage), Pixie Tear (per-400-Max-ES → +damage, excess Life → ES restoration), and Rebirth
(Regain → Restoration conversion in the recovery stage).
"""
import pytest
from server import engine_stats, EngineStatsRequest
from tests.mock_build import make_request


def _gear(pairs):
    return [{"item_name": "T", "contributions": [
        {"stat": k, "display_value": v, "unit": "", "slot": "ring1", "item_name": "T", "text": f"T:{k}"}
        for k, v in pairs]}]


def _resp(extra_skills=None, slot_levels=None, picks=None, gear=None, ingredients=None, conds=None):
    req = make_request("chromatic_shot", 20, gear=gear if gear is not None else _gear([("elixir_effect_inc", 0.5)]),
                       extra_conditions=conds or {})
    for sk in (extra_skills or []):
        req["skills"].append(sk)
    if slot_levels is not None:
        req["trait_id"] = "licorice_note"
        req["trait_slot_levels"] = slot_levels
    if picks is not None:
        req["advanced_trait_selections"] = picks
    if ingredients is not None:
        req["elixir_ingredients"] = ingredients
    r = engine_stats(EngineStatsRequest(**req))
    return r if isinstance(r, dict) else r.model_dump()


def _elixir(r, name_contains):
    return next(e for e in (r.get("elixirs") or []) if name_contains.lower() in e["name"].lower())


# ── Elixir of Immortality: excess restoration → Temporary Life → +damage ──────
def test_immortality_temporary_life_capped_and_damage():
    tonic = [{"slot": 2, "skill_id": "life_tonic", "level": 20}]
    base = _resp(extra_skills=tonic, slot_levels=[5, 0, 0, 0])              # no Immortality pick
    imm = _resp(extra_skills=tonic, slot_levels=[5, 1, 1, 0], picks=["Elixir of Immortality"])
    ml = imm["defense"]["max_life"]
    rec = imm["recovery"]
    # excess Life = 0.41×ML (full Life), temp = min(0.41×ML×2/3, 0.20×ML) = 0.20×ML (capped at tier-0 20%).
    assert rec["temporary_life"] == pytest.approx(0.20 * ml, rel=0.05)
    assert imm["recovery"]["total_max_life"] == pytest.approx(ml + rec["temporary_life"], rel=1e-3)
    # 4 Temporary units (temp / 5% Base Max Life) × 1%/unit = +4% additional damage → DPS rises.
    assert imm["offense"]["total_dps"] > base["offense"]["total_dps"]


def test_immortality_excess_lower_at_low_life():
    # At low Current Life % restoration refills the deficit first (effective), so LESS overflows to excess than at
    # full Life → less Temporary Life. (Directional: with a big heal some excess can remain even at low life.)
    tonic = [{"slot": 2, "skill_id": "life_tonic", "level": 20}]
    full = _resp(extra_skills=tonic, slot_levels=[5, 1, 1, 0], picks=["Elixir of Immortality"],
                 conds={"current_life_pct": 100})
    low = _resp(extra_skills=tonic, slot_levels=[5, 1, 1, 0], picks=["Elixir of Immortality"],
                conds={"current_life_pct": 50})
    assert low["recovery"]["excess_life_restoration"] < full["recovery"]["excess_life_restoration"]
    assert low["recovery"]["temporary_life"] <= full["recovery"]["temporary_life"]


# ── Pixie Tear: per-400 Max ES additional damage + excess Life → ES restoration ─
def test_pixie_tear_per_400_es_damage():
    es_gear = _gear([("elixir_effect_inc", 0.5), ("max_energy_shield_flat", 4000)])
    skills = [{"slot": 2, "skill_id": "thirst_dew", "level": 20}]
    base = _resp(extra_skills=skills, slot_levels=[5, 1, 1, 1], gear=es_gear)
    px = _resp(extra_skills=skills, slot_levels=[5, 1, 1, 1], gear=es_gear, ingredients={"2": ["Pixie Tear"]})
    # 4000 ES / 400 × 1% = +10% additional damage (under the +40% tier-0 cap) → DPS rises, ingredient surfaced.
    assert px["offense"]["total_dps"] > base["offense"]["total_dps"]
    g = next((g for g in _elixir(px, "Thirst")["granted"] if g["stat"] == "dmg_additional_per_400_es"), None)
    assert g is not None
    assert g["amount"] == pytest.approx(0.01, abs=1e-3)            # per-unit value, no_scale (not × Elixir Effect)


def test_pixie_tear_damage_capped():
    # Huge ES → the per-400 damage clamps at the tier-0 cap (+40%); doubling ES past the cap doesn't add more DPS.
    g1 = _gear([("elixir_effect_inc", 0.5), ("max_energy_shield_flat", 40000)])
    g2 = _gear([("elixir_effect_inc", 0.5), ("max_energy_shield_flat", 80000)])
    skills = [{"slot": 2, "skill_id": "thirst_dew", "level": 20}]
    a = _resp(extra_skills=skills, slot_levels=[5, 1, 1, 1], gear=g1, ingredients={"2": ["Pixie Tear"]})
    b = _resp(extra_skills=skills, slot_levels=[5, 1, 1, 1], gear=g2, ingredients={"2": ["Pixie Tear"]})
    assert b["offense"]["total_dps"] == pytest.approx(a["offense"]["total_dps"], rel=1e-3)


def test_pixie_tear_excess_life_to_es_restoration():
    es_gear = _gear([("elixir_effect_inc", 0.5), ("max_energy_shield_flat", 4000),
                     ("elixir_charging_progress_flat", 40)])
    skills = [{"slot": 2, "skill_id": "life_tonic", "level": 20}]
    px = _resp(extra_skills=skills, slot_levels=[5, 1, 1, 1], gear=es_gear, ingredients={"2": ["Pixie Tear"]})
    rec = px["recovery"]
    # 80% of excess Life restoration is also applied to ES restoration.
    assert rec["restoration_es_total"] == pytest.approx(0.80 * rec["excess_life_restoration"], rel=0.02)
    assert rec["restoration_es_per_sec"] > 0


# ── Restoration value level-interpolation + uptime modes ──────────────────────
def test_life_tonic_value_interpolates_with_level():
    # "Restores 41% Max Life (Lv1:41)(Lv21:61)" → Lv1=41%, Lv20=60% (interpolated), Lv21=61%.
    def total_pct(level):
        req = make_request("chromatic_shot", 20)
        req["skills"].append({"slot": 2, "skill_id": "life_tonic", "level": level})
        r = engine_stats(EngineStatsRequest(**req)); r = r if isinstance(r, dict) else r.model_dump()
        return r["recovery"]["restoration_life_total"] / r["defense"]["max_life"]
    assert total_pct(1) == pytest.approx(0.41, abs=0.01)
    assert total_pct(20) == pytest.approx(0.60, abs=0.01)
    assert total_pct(21) == pytest.approx(0.61, abs=0.01)


def test_life_tonic_tooltip_restoration_modeled_single_line():
    import json as _json
    from engine.tooltip import build_tooltip
    skills = _json.load(open("../data/seasons/SS12/_skills.json", encoding="utf-8"))["skills"]
    s = next(x for x in skills if x.get("name") == "Life Tonic")
    lines = build_tooltip(s)["lines"]
    restore = [ln for ln in lines if "restores" in (ln.get("badge_text", "") + str(ln.get("values_by_level") or "")).lower()]
    assert len(restore) == 1                                # the flat duplicate is deduped
    assert restore[0].get("coverage") == "modeled"          # not NYI
    assert not restore[0].get("badge_text")                 # green, no badge
    # Charging-progress lines are modeled (drive the recast), not NYI.
    charge = [ln for ln in lines if "charging progress" in (ln.get("badge_text", "") or ln.get("text", "")).lower()]
    assert charge and all(ln.get("coverage") == "modeled" or not ln.get("badge_text") for ln in charge)


# ── Rebirth: a fraction of Regain converted to Restoration ────────────────────
def test_rebirth_converts_regain_to_restoration():
    # Life Regain present (missing Life) + Rebirth conversion → part of the regain rate moves to restoration.
    gear = _gear([("life_regain_inc", 0.1), ("life_regain_to_restoration", 0.5)])
    r = _resp(gear=gear, conds={"current_life_pct": 50})
    rec = r["recovery"]
    assert any("Rebirth" in (s.get("source") or "") for s in (rec.get("restoration_sources") or []))
    assert rec["restoration_life_per_sec"] > 0
