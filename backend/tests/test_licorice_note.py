"""Licorice Note (Sage) — scent-bottle Elixir Effect bonuses + the Pungent cross-apply to a designated
Empower/Curse, slot-scoped. Covers slot-specificity, the designate-one rule, caps, the increased-pool wording,
Scent of Ambition / Everlasting Nectar, the activation-medium warning, and that other traits are unaffected.
"""
import pytest
from server import engine_stats, EngineStatsRequest
from tests.mock_build import make_request

ELIXIR = "thirst_dew"          # goes in the Basic Scent Bottle (slot 2)
EMPOWER = "aim"
EMPOWER2 = "arcane_circle"
CURSE = "biting_cold"


def _gear(pairs):
    return [{"item_name": "T", "contributions": [
        {"stat": k, "display_value": v, "unit": "", "slot": "ring1", "item_name": "T", "text": f"T:{k}"}
        for k, v in pairs]}]


def _resp(extra_skills=None, slot_levels=None, picks=None, prepared=None, gear=None, supports=None, ingredients=None):
    req = make_request("chromatic_shot", 20, gear=gear if gear is not None else _gear([("elixir_effect_inc", 0.5)]),
                       attached_supports=supports or [])
    for sk in (extra_skills or []):
        req["skills"].append(sk)
    if slot_levels is not None:
        req["trait_id"] = "licorice_note"
        req["trait_slot_levels"] = slot_levels
    if picks is not None:
        req["advanced_trait_selections"] = picks
    if prepared is not None:
        req["licorice_prepared_skill"] = prepared
    if ingredients is not None:
        req["elixir_ingredients"] = ingredients
    r = engine_stats(EngineStatsRequest(**req))
    return r if isinstance(r, dict) else r.model_dump()


def _elixir(r, name_contains):
    return next(e for e in (r.get("elixirs") or []) if name_contains.lower() in e["name"].lower())


def _empower(r, sid):
    return next((e for e in (r.get("empowers") or []) if e["skill_id"] == sid), None)


def _curse(r, sid):
    return next((c for c in (r.get("curses") or []) if c["skill_id"] == sid), None)


# ── Artificial Moon: slot-scoped +12% additional Elixir Effect ───────────────
def test_artificial_moon_only_on_scent_bottle_slot():
    # Elixir in slot 2 (Basic Scent Bottle) AND a second elixir in slot 4. Only slot 2 gets +12%.
    r = _resp(extra_skills=[{"slot": 2, "skill_id": ELIXIR, "level": 20},
                            {"slot": 4, "skill_id": "swiftness_dew", "level": 20}],
              slot_levels=[5, 0, 0, 0])
    sb = _elixir(r, "Thirst")          # slot 2
    other = _elixir(r, "Swiftness")    # slot 4
    # slot2: (1+0.5 inc)*(1+0.12 AM) - 1 = 0.68 ; slot4: just (1+0.5) - 1 = 0.5
    assert sb["elixir_effect_inc"] == pytest.approx(0.68, abs=1e-3)
    assert other["elixir_effect_inc"] == pytest.approx(0.50, abs=1e-3)


def test_artificial_moon_needs_base_l5():
    r = _resp(extra_skills=[{"slot": 2, "skill_id": ELIXIR, "level": 20}], slot_levels=[4, 0, 0, 0])
    assert _elixir(r, "Thirst")["elixir_effect_inc"] == pytest.approx(0.50, abs=1e-3)  # no AM below L5


# ── Pungent cross-apply: one designated Empower/Curse, slot-scoped, increased pool, capped ──
def test_pungent_empower_autoselect_and_cap():
    # One eligible empower → auto-selected. basis 0.5 × ratio 2.0 = 1.0, capped to empower L1 cap 0.70.
    r = _resp(extra_skills=[{"slot": 2, "skill_id": ELIXIR, "level": 20},
                            {"slot": 3, "skill_id": EMPOWER, "level": 20}],
              slot_levels=[5, 1, 0, 0])
    assert _empower(r, EMPOWER)["empower_effect_inc"] == pytest.approx(0.70, abs=1e-3)


def test_pungent_requires_designation_when_multiple():
    # Two empowers, no designation → NO bonus on either.
    skills = [{"slot": 2, "skill_id": ELIXIR, "level": 20},
              {"slot": 3, "skill_id": EMPOWER, "level": 20},
              {"slot": 4, "skill_id": EMPOWER2, "level": 20}]
    r = _resp(extra_skills=skills, slot_levels=[5, 1, 0, 0])
    assert _empower(r, EMPOWER)["empower_effect_inc"] == pytest.approx(0.0, abs=1e-3)
    assert _empower(r, EMPOWER2)["empower_effect_inc"] == pytest.approx(0.0, abs=1e-3)
    # Designate one → only that one gets it.
    r2 = _resp(extra_skills=skills, slot_levels=[5, 1, 0, 0], prepared=EMPOWER2)
    assert _empower(r2, EMPOWER)["empower_effect_inc"] == pytest.approx(0.0, abs=1e-3)
    assert _empower(r2, EMPOWER2)["empower_effect_inc"] == pytest.approx(0.70, abs=1e-3)


def test_pungent_curse_slot_scoped():
    # One eligible curse → auto-selected; cross-apply lands on its (increased) curse effect, capped to 0.50.
    r = _resp(extra_skills=[{"slot": 2, "skill_id": ELIXIR, "level": 20},
                            {"slot": 3, "skill_id": CURSE, "level": 20}],
              slot_levels=[5, 1, 0, 0])
    c = _curse(r, CURSE)
    assert c is not None
    assert c["curse_effect_inc"] == pytest.approx(0.50, abs=1e-3)   # 0.5×2.0=1.0 capped to curse L1 cap 0.50


def test_pungent_curse_only_designated_when_multiple():
    skills = [{"slot": 2, "skill_id": ELIXIR, "level": 20},
              {"slot": 3, "skill_id": CURSE, "level": 20},
              {"slot": 4, "skill_id": "corruption", "level": 20}]
    r = _resp(extra_skills=skills, slot_levels=[5, 1, 0, 0], prepared=CURSE)
    assert _curse(r, CURSE)["curse_effect_inc"] == pytest.approx(0.50, abs=1e-3)
    assert _curse(r, "corruption")["curse_effect_inc"] == pytest.approx(0.0, abs=1e-3)


# ── Scent of Ambition / Everlasting Nectar ───────────────────────────────────
def test_scent_of_ambition_additional_and_duration():
    r = _resp(extra_skills=[{"slot": 2, "skill_id": ELIXIR, "level": 20}],
              slot_levels=[5, 1, 1, 0], picks=["Scent of Ambition"])
    e = _elixir(r, "Thirst")
    # (1+0.5 inc)*(1+0.12 AM + 0.24 Ambition) - 1 = 1.5*1.36 - 1 = 1.04
    assert e["elixir_effect_inc"] == pytest.approx(1.04, abs=1e-3)


def test_everlasting_nectar_increased_from_life():
    # +200% increased Max Life → bonus 2.0 × ratio 1.0 = 2.0 capped to 0.60. Outputs increased elixir effect.
    r = _resp(extra_skills=[{"slot": 2, "skill_id": ELIXIR, "level": 20}],
              slot_levels=[5, 1, 0, 1], picks=["Everlasting Nectar"],
              gear=_gear([("elixir_effect_inc", 0.5), ("max_life_inc", 2.0)]))
    e = _elixir(r, "Thirst")
    # increased pool now 0.5 + 0.60 (nectar) = 1.10; ×(1+0.12 AM) = 2.10*1.12 - 1 = 1.352
    assert e["elixir_effect_inc"] == pytest.approx(1.352, abs=2e-3)


# ── Activation-medium warning ────────────────────────────────────────────────
def test_activation_medium_warning():
    sup = [{"item_id": "activation_medium_boss", "slot": 3, "level": 1, "enabled": True}]
    r = _resp(extra_skills=[{"slot": 2, "skill_id": ELIXIR, "level": 20},
                            {"slot": 3, "skill_id": EMPOWER, "level": 20}],
              slot_levels=[5, 1, 0, 0], supports=sup)
    warns = [s for s in (r.get("trait_mod_statuses") or []) if s.get("status") == "warning"]
    assert any("Activation Medium" in s["text"] for s in warns)


def test_no_activation_medium_no_warning():
    r = _resp(extra_skills=[{"slot": 2, "skill_id": ELIXIR, "level": 20},
                            {"slot": 3, "skill_id": EMPOWER, "level": 20}],
              slot_levels=[5, 1, 0, 0])
    warns = [s for s in (r.get("trait_mod_statuses") or []) if s.get("status") == "warning"]
    assert not any("Activation Medium" in s["text"] for s in warns)


def test_warning_names_skill_and_source():
    # The warning should name the buffed Empower AND the exact medium on its slot.
    sup = [{"item_id": "activation_medium_boss", "slot": 3, "level": 1, "enabled": True}]
    r = _resp(extra_skills=[{"slot": 2, "skill_id": ELIXIR, "level": 20},
                            {"slot": 3, "skill_id": EMPOWER, "level": 20}],
              slot_levels=[5, 1, 0, 0], supports=sup)
    warns = [s["text"] for s in (r.get("trait_mod_statuses") or []) if s.get("status") == "warning"]
    assert any("Aim" in t and "Activation Medium: Boss" in t for t in warns)


def test_normal_preparation_support_warns():
    # "Preparation" support (normal spell preparation, not an Activation Medium) on the empower's slot also warns.
    sup = [{"item_id": "preparation", "slot": 3, "skill_type": "support_skill", "level": 1, "enabled": True}]
    r = _resp(extra_skills=[{"slot": 2, "skill_id": ELIXIR, "level": 20},
                            {"slot": 3, "skill_id": EMPOWER, "level": 20}],
              slot_levels=[5, 1, 0, 0], supports=sup)
    warns = [s["text"] for s in (r.get("trait_mod_statuses") or []) if s.get("status") == "warning"]
    assert any("Aim" in t and "Preparation" in t for t in warns)


def test_preparation_on_other_slot_no_warning():
    # A medium on a slot WITHOUT an eligible empower/curse is not a Pungent conflict → no warning.
    sup = [{"item_id": "activation_medium_boss", "slot": 1, "level": 1, "enabled": True}]
    r = _resp(extra_skills=[{"slot": 2, "skill_id": ELIXIR, "level": 20},
                            {"slot": 3, "skill_id": EMPOWER, "level": 20}],
              slot_levels=[5, 1, 0, 0], supports=sup)
    warns = [s for s in (r.get("trait_mod_statuses") or []) if s.get("status") == "warning"]
    assert not any("Pungent" in s.get("source", "") for s in warns)


# ── Ingredients (Phase 2): fold into the scent-bottle elixir, scaled by Elixir Effect, NYI surfaced ──
def _resp_ing(ingredients, slot_levels=(5, 1, 0, 0)):
    return _resp(extra_skills=[{"slot": 2, "skill_id": ELIXIR, "level": 20}],
                 slot_levels=list(slot_levels), gear=_gear([("elixir_effect_inc", 0.5)]), ingredients=ingredients)


def test_ingredient_razor_leaf_applies_scaled():
    # Razor Leaf (+16% additional damage at base L5) → the CRIT-WEIGHTED pool (offense weights by crit chance),
    # folded into the slot-2 elixir and scaled by Elixir Effect.
    r = _resp_ing({"2": ["Razor Leaf"]})
    e = _elixir(r, "Thirst")
    g = next((g for g in e["granted"] if g["stat"] == "dmg_additional_on_crit"), None)
    assert g is not None
    assert g["base"] == pytest.approx(0.16, abs=1e-3)            # base L5 tier
    assert g["amount"] == pytest.approx(0.16 * 1.5 * 1.12, abs=2e-3)   # × (1+0.5 inc)(1+0.12 Artificial Moon)


def test_ingredient_reaping_surfaces_nyi():
    r = _resp_ing({"2": ["Twinspine Flower"]})
    assert any("Reap" in s.get("text", "") and "Ingredient" in s.get("text", "")
               for s in (r.get("elixir_statuses") or []))


def test_ingredient_tier_scales_with_base_level():
    # Damage ingredients scale with the BASE trait level: L1 → +12%, L5 → +16%.
    lo = _resp_ing({"2": ["Razor Leaf"]}, slot_levels=(1, 1, 0, 0))
    g = next(g for g in _elixir(lo, "Thirst")["granted"] if g["stat"] == "dmg_additional_on_crit")
    assert g["base"] == pytest.approx(0.12, abs=1e-3)


# ── Other traits unaffected by the curse slot-aware change ────────────────────
def test_curse_global_effect_unchanged_without_trait():
    # A curse with a global +Curse Effect mod, no Licorice Note → behaves as before (global applies).
    r = _resp(extra_skills=[{"slot": 2, "skill_id": CURSE, "level": 20}],
              gear=_gear([("curse_effect_inc", 0.3)]))
    c = _curse(r, CURSE)
    assert c is not None and c["curse_effect_inc"] == pytest.approx(0.3, abs=1e-3)
