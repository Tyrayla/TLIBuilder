"""
Tests: engine/support_resolver.resolve_support_behavior — parsing Merge's same-target shotgun /
falloff and Web's chains-per-jump from support description text (text-driven, not id-hardcoded).
"""
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

_BY_ID = {
    "merge": _sup("merge", _MERGE_DESC),
    "web":   _sup("web", _WEB_DESC),
    "plain": _sup("plain", _PLAIN_DESC),
}


def _b(*ids):
    return resolve_support_behavior([{"item_id": i} for i in ids], _BY_ID)


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

    def test_empty(self):
        assert resolve_support_behavior(None, _BY_ID) == {}
        assert resolve_support_behavior([{"item_id": "merge"}], None) == {}
