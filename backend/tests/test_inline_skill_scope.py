"""Inline skill-type scope fallback: "Melee Skill Damage" / "Melee Attack Speed" — phrasings the suffix
detector ("… for X Skills") and the base resolver miss. The fallback fires ONLY when normal resolution fails,
so typed-stat phrasings ("additional Spell Damage" → spell_dmg_additional) are never disturbed."""
from server import _parse_custom_mod_text as P
from engine.skill_scope import detect_inline_skill_scope


def _one(text):
    r = P(text)
    assert len(r) == 1, f"{text!r} -> {r}"
    return r[0]


def test_melee_skill_damage_resolves_scoped():
    d = _one("+30 % additional Melee Skill Damage")
    assert d["stat_key"] == "dmg_additional" and d["scope"] == "melee"


def test_melee_attack_speed_resolves_scoped():
    d = _one("+8 % Melee Attack Speed")
    assert d["stat_key"] == "attack_speed_inc" and d["scope"] == "melee"


def test_typed_damage_forms_unaffected():
    # These resolve on the FIRST (no-peel) try → must keep their typed stat + no scope.
    assert _one("+30 % additional Spell Damage") == {
        "stat_key": "spell_dmg_additional", "amount": 0.3, "text": "+30 % additional Spell Damage"}
    assert _one("+33 % additional Area Damage")["stat_key"] == "area_dmg_additional"
    assert _one("+30 % additional Channeled Skill Damage")["stat_key"] == "channeled_dmg_additional"
    assert "scope" not in _one("8% Attack Speed")  # plain attack speed, no inline scope


def test_helper_leaves_unknown_text_untouched():
    assert detect_inline_skill_scope("additional Damage") == ("additional Damage", None)
