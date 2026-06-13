"""
Tests: engine/support_resolver.resolve_support_behavior — parsing Merge's same-target shotgun /
falloff and Web's chains-per-jump from support description text (text-driven, not id-hardcoded).
"""
import pytest
from engine.support_resolver import resolve_support_behavior


def _sup(item_id, desc):
    return {"item_id": item_id, "name": item_id, "skill_type": "noble_support_skill",
            "description_lines": [desc], "progression": []}


_MERGE_DESC = ("Supports X. +20 % additional damage for the supported skill Multiple Chain Lightnings "
               "can target the same enemy. The Shotgun Effect falloff coefficient of the supported "
               "skill is 80 % (-14.0 to -12.0) % additional damage for the supported skill")
_WEB_DESC = ("Supports X. +20 % additional damage for the supported skill For every 1 Jump , the "
             "supported skill releases 1 additional Chain Lightning (does not target the same enemy). "
             "Each Chain Lightning can only Jump 1 time(s) +(16-18) % additional damage")
_PLAIN_DESC = "Supports X. +20 % additional damage for the supported skill"
_LUCKY_DESC = ("Supports X. +20 % additional damage for the supported skill +1 Jump(s) for the skill "
               "when the supported skill defeats an enemy The supported skill deals Lucky Damage "
               "(-7 to -5) % additional damage for the supported skill")


def _aug():
    s = _sup("aug", "Supports X. +20 % additional damage for the supported skill "
                    "+(5.5-5.9) % additional damage for every 1 Jump remaining (multiplies)")
    s["progression"] = [{"level": 1, "values": {
        "name": "+(5.5-5.9) % additional damage for every 1 Jump(s) remaining of the supported skill (multiplies)"}}]
    return s


_BY_ID = {
    "merge": _sup("merge", _MERGE_DESC),
    "web":   _sup("web", _WEB_DESC),
    "plain": _sup("plain", _PLAIN_DESC),
    "lucky": _sup("lucky", _LUCKY_DESC),
    "aug":   _aug(),
}


def _b(*ids):
    # resolve_support_behavior now returns a per-slot map {slot: {...}}; these supports are all slot 1.
    return resolve_support_behavior([{"item_id": i} for i in ids], _BY_ID).get(1, {})


class TestBehavior:
    def test_merge_falloff_and_same_target(self):
        b = _b("merge")
        assert b["same_target_shotgun"] is True
        assert b["falloff_coefficient"] == 0.80
        assert "chains_per_jump" not in b

    def test_web_chains_per_jump(self):
        b = _b("web")
        assert b["chains_per_jump"] == 1
        assert "same_target_shotgun" not in b

    def test_web_plus_merge(self):
        b = _b("web", "merge")
        assert b["same_target_shotgun"] is True
        assert b["falloff_coefficient"] == 0.80
        assert b["chains_per_jump"] == 1

    def test_plain_support_no_behavior(self):
        assert _b("plain") == {}

    def test_lucky_damage(self):
        b = _b("lucky")
        assert b["lucky_damage"] is True
        assert "augmentation_per_jump" not in b

    def test_augmentation_per_jump(self):
        b = _b("aug")
        assert b["augmentation_per_jump"] == pytest.approx(0.057)  # mid of 5.5–5.9%
        assert "lucky_damage" not in b

    def test_aug_plus_lucky(self):
        b = _b("aug", "lucky")
        assert b["augmentation_per_jump"] == pytest.approx(0.057)
        assert b["lucky_damage"] is True

    def test_empty(self):
        assert resolve_support_behavior(None, _BY_ID) == {}
        assert resolve_support_behavior([{"item_id": "merge"}], None) == {}
