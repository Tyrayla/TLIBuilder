"""The "enhanced" skill-type tag is the one entry in engine.skill_scope._SKILL_TYPE_TAG whose tag literal is
a TWO-WORD string ("enhanced skill", not "enhanced") — every other skill-type word maps 1:1 to itself. Covers
both phrasings the scope detectors recognize: the INLINE form ("Enhanced Skill Damage") and the SUFFIX form
("... for Enhanced Skills"), at both the raw-helper level and through the real resolver
(server._parse_custom_mod_text), mirroring test_inline_skill_scope.py's style.
"""
from server import _parse_custom_mod_text as P
from engine.skill_scope import detect_inline_skill_scope, detect_skill_scope


def _one(text):
    r = P(text)
    assert len(r) == 1, f"{text!r} -> {r}"
    return r[0]


class TestHelpers:
    def test_inline_enhanced_skill_damage(self):
        assert detect_inline_skill_scope("Enhanced Skill Damage") == ("Damage", "enhanced skill")

    def test_suffix_for_enhanced_skills(self):
        residual, tag = detect_skill_scope("+10% Cast Speed for Enhanced Skills")
        assert tag == "enhanced skill"
        assert residual == "+10% Cast Speed"


class TestThroughRealResolver:
    def test_inline_enhanced_skill_damage_resolves_scoped(self):
        d = _one("+30 % additional Enhanced Skill Damage")
        assert d["stat_key"] == "dmg_additional" and d["scope"] == "enhanced skill"

    def test_suffix_for_enhanced_skills_resolves_scoped(self):
        d = _one("+10 % Cast Speed for Enhanced Skills")
        assert d["stat_key"] == "cast_speed_inc" and d["scope"] == "enhanced skill"

    def test_dealt_by_enhanced_skills_resolves_scoped(self):
        d = _one("+15 % Damage dealt by Enhanced Skills")
        assert d["scope"] == "enhanced skill"
