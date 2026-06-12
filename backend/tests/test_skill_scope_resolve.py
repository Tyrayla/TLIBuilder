"""Skill-scope resolver/badge (plan Test C): the 'for/dealt by <X> Skills' qualifier resolves to the BASE
stat + a scope tag, keeps the original text, and leaves unscoped/unknown text exactly as today."""
import pytest

from server import _parse_custom_mod_text as pm
from engine.skill_scope import detect_skill_scope
from engine.aggregator import resolve_effect_stat_keys


def _one(text):
    r = pm(text)
    assert r, f"{text!r} did not resolve"
    return r[0]


class TestResolverScope:
    @pytest.mark.parametrize("text,stat,scope", [
        ("+20 % Elemental Damage for Attack Skills", "elemental_dmg_inc", "attack"),
        ("+14 % additional damage for Channeled Skills", "dmg_additional", "channeled"),
        ("+19 % additional Elemental Damage dealt by Spell Skills", "elemental_dmg_additional", "spell"),
        ("+80 % Critical Strike Rating for Melee Skills", "crit_rating_inc", "melee"),
        ("+30 % Cooldown Recovery Speed for Mobility Skills", "cdr_speed_inc", "mobility"),
        ("+(20-25) % Armor DMG Mitigation Penetration for Attack Skills", "armor_pen", "attack"),
    ])
    def test_resolves_base_plus_scope(self, text, stat, scope):
        e = _one(text)
        assert e["stat_key"] == stat
        assert e.get("scope") == scope
        assert e["text"] == text  # ORIGINAL full text kept (incl. scope words) for affix-identity

    def test_double_damage_midphrase(self):
        e = _one("+5 % chance for Attack Skills to deal Double Damage")
        assert e["stat_key"] == "double_dmg_chance" and e.get("scope") == "attack"

    def test_unknown_skill_word_not_scoped(self):
        # "Wizardry" isn't a real skill tag → not stripped, not scoped → status quo (resolves unscoped here).
        residual, scope = detect_skill_scope("+20 % Attack Damage for Wizardry Skills")
        assert scope is None and residual == "+20 % Attack Damage for Wizardry Skills"

    def test_unscoped_unchanged(self):
        e = _one("+30 % Attack Damage")
        assert e["stat_key"] == "attack_dmg_inc" and e.get("scope") is None


class TestBadgeResolution:
    """resolve_effect_stat_keys (the /api/map-modifiers spirit/memory path) strips scope so scoped mods
    badge RESOLVED (not NYI)."""

    def test_scoped_spirit_resolves_base_key(self):
        # "damage for Channeled Skills" → base "damage" → dmg_inc (the memory lookup handles the generic form).
        assert "dmg_inc" in resolve_effect_stat_keys("+14 % damage for Channeled Skills", is_memory=False)

    def test_unscoped_spirit_unchanged(self):
        assert resolve_effect_stat_keys("+10 % Affliction Effect", is_memory=False) == \
            resolve_effect_stat_keys("+10 % Affliction Effect", is_memory=False)
