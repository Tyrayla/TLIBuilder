"""Mana/Life sealing & reservation (engine.utility.apply_reservation, surfaced via the engine response).

Formulas (Help DB): per sealing skill amount = base_seal_frac × Max Mana × Π(support Mana Multiplier) ÷
(1 + Sealed Mana Compensation). Seal Conversion routes the amount to Sealed Life. Off the Beaten Track forces
support Mana Multipliers to 95%. Ward adds Energy Shield from sealed pools. Lunar Eclipse imparts a seal onto
an active skill (its OWN mana_cost excluded — not double-dipped) and scales damage with total Mana sealed.
"""
import json
import os

from server import engine_stats, EngineStatsRequest

_SKILLS = os.path.join(os.path.dirname(__file__), "..", "..", "data", "seasons", "SS12", "_skills.json")
_BY_ID = {s["item_id"]: s for s in json.load(open(_SKILLS, encoding="utf-8"))["skills"]}
_LUNAR = next(s["item_id"] for s in _BY_ID.values() if "Lunar Eclipse" in (s.get("name") or ""))

# Cruelty: a 50% Sealed Mana aura. 1000 Max Mana via a custom mod → base seal 500.
_CRUELTY = [{"slot": 6, "skill_id": "cruelty", "level": 20, "enabled": True}]


def _run(skills, supports=None, mods=None, conds=None):
    return engine_stats(EngineStatsRequest(
        slots=[], slates=[], gear=[], character=[], skills=skills,
        attached_supports=supports or [],
        custom_mods=mods if mods is not None else ["+1000 Max Mana"],
        condition_state=conds or {}))


def _sup(item_id, slot=6, **kw):
    return {"slot": slot, "item_id": item_id, "skill_type": kw.pop("skill_type", "support_skill"),
            "level": 20, "enabled": True, **kw}


def test_base_seal_is_pct_of_max_mana():
    r = _run(_CRUELTY)["reservation"]
    assert round(r["sealed_mana"], 1) == 500.0
    assert round(r["unsealed_mana"], 1) == 500.0


def test_support_mana_multiplier_scales_seal():
    # Added Lightning Damage has a 110% Mana Multiplier → 500 × 1.10 = 550.
    r = _run(_CRUELTY, [_sup("added_lightning_damage")])["reservation"]
    assert round(r["sealed_mana"], 1) == 550.0


def test_compensation_reduces_seal():
    # Restrain: +10% Sealed Mana Compensation at Lv20 → 500 / 1.10 = 454.5.
    r = _run(_CRUELTY, [_sup("restrain")])["reservation"]
    assert round(r["sealed_mana"], 1) == 454.5


def test_seal_conversion_seals_life_off_max_life_with_penalty():
    # Seal Conversion replaces the seal's POOL: a 50% seal becomes 50% of MAX LIFE (not 50% of mana), then the
    # −65.25% comp penalty applies → 0.50 × 4000 / (1 − 0.6525) ≈ 5755 Sealed Life, and 0 Sealed Mana.
    r = _run(_CRUELTY, [_sup("seal_conversion")], mods=["+1000 Max Mana", "+4000 Max Life"])["reservation"]
    assert r["sealed_mana"] == 0.0
    assert round(r["sealed_life"]) == 5755
    assert r["per_skill"][0]["pool"] == "life"


def test_increased_and_additional_comp_are_separate_multiplicative_pools():
    # Increased and additional Sealed Mana Compensation are SEPARATE multiplicative factors:
    # denom = (1 + Σinc) × (1 + Σadd), NOT (1 + Σboth). In-game-verified: a 50% Life seal with +29.5% talent +8%
    # Restrain (inc=37.5%) and −66.25% Seal Conversion (add) OVERFLOWS Life because 1.375 × 0.3375 = 0.464 < 0.5
    # — whereas summing would give 0.7125 and falsely fit. 0.50 × 4000 ÷ 0.4640625 ≈ 4310 > 4000 Max Life.
    r = _run(_CRUELTY, [_sup("restrain", level=16), _sup("seal_conversion", level=16)],
             mods=["+1000 Max Mana", "+4000 Max Life", "29.5% Sealed Mana Compensation"])["reservation"]
    ps = r["per_skill"][0]
    assert round(ps["comp_increased"], 4) == 0.375 and round(ps["comp_additional"], 4) == -0.6625
    assert round(r["sealed_life"]) == 4310
    assert r["insufficient_life"] is True   # reservation exceeds Max Life


def test_off_the_beaten_track_forces_95pct_multiplier():
    # 110% support, but OtBT fixes every support's Mana Multiplier to 95% → 500 × 0.95 = 475.
    r = _run(_CRUELTY, [_sup("added_lightning_damage")],
             conds={"core_support_mana_mult_95": True})["reservation"]
    assert round(r["sealed_mana"], 1) == 475.0


def test_ward_adds_energy_shield_from_sealed():
    # 500 sealed mana × 13% → +65 Max Energy Shield.
    d = _run(_CRUELTY, mods=["+1000 Max Mana", "Adds 13 % of Sealed Mana as Energy Shield"])["defense"]
    assert round(d["max_energy_shield"]) == 65


def test_lunar_eclipse_imparts_seal_without_its_own_multiplier():
    # Moon Strike (active, no own seal) + Lunar Eclipse → seals 10% Max Mana = 100. The imparting support's
    # own 110% mana_cost must NOT apply to the imparted seal (no double-dip).
    r = _run([{"slot": 1, "skill_id": "moon_strike", "level": 20, "enabled": True}],
             [_sup(_LUNAR, slot=1, skill_type="noble_support_skill", rank=5)])["reservation"]
    assert round(r["sealed_mana"], 1) == 100.0
    assert r["per_skill"][0]["support_mults"] == []


def test_imparted_seal_ignores_other_support_multipliers_but_scales_with_global_comp():
    # A support-imparted seal is a fixed reservation: NO support Mana Multiplier scales it (verified in-game),
    # only the GLOBAL Sealed Mana Compensation pool does. A 110% support leaves it at 100; +20% global → 83.3.
    moon = [{"slot": 1, "skill_id": "moon_strike", "level": 20, "enabled": True}]
    le = _sup(_LUNAR, slot=1, skill_type="noble_support_skill", rank=5)
    with_sup = _run(moon, [le, _sup("added_lightning_damage", slot=1)])["reservation"]
    assert round(with_sup["sealed_mana"], 1) == 100.0   # the 110% support does NOT scale the imparted seal
    with_comp = _run(moon, [le], mods=["+1000 Max Mana", "+20 % Sealed Mana Compensation"])["reservation"]
    assert round(with_comp["sealed_mana"], 1) == 83.3   # global comp DOES scale it


def test_no_sealers_is_full_pools():
    d = _run([{"slot": 1, "skill_id": "chain_lightning", "level": 14, "enabled": True}],
             mods=["+1000 Max Mana"])["defense"]
    assert d["sealed_mana"] == 0.0 and d["unsealed_mana"] == d["max_mana"]
