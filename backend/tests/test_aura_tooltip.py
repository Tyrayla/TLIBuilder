"""Aura/Focus skill tooltips: the "… gain the following buff:" intro is flavor (no badge), and each buff
clause is its own line with a resolvable badge_text — so a modeled buff badges as working instead of the
whole description blob reading 'Unrecognized (NYI)'. Regression guard for the reported false-NYI badges."""
import json
import os

from engine.tooltip import build_tooltip
from server import _resolve_skill_line_keys

_SKILLS = os.path.join(os.path.dirname(__file__), "..", "..", "data", "seasons", "SS12", "_skills.json")
_BY_ID = {s["item_id"]: s for s in json.load(open(_SKILLS, encoding="utf-8"))["skills"]}


def _lines(sid):
    return build_tooltip(_BY_ID[sid])["lines"]


def test_aura_buff_line_resolves_not_nyi():
    lines = _lines("electric_conversion")
    intro = [ln for ln in lines if "gain the following buff" in ln["text"].lower()]
    assert intro and intro[0]["badge_text"] == ""           # intro is flavor, never badged
    buff = [ln for ln in lines if "Lightning Damage" in ln["text"]]
    assert buff, "buff clause should be its own line"
    assert _resolve_skill_line_keys(buff[0]["badge_text"]) == ["lightning_dmg_additional"]


def test_spell_amplification_buff_resolves():
    buff = [ln for ln in _lines("spell_amplification") if "Spell Damage" in ln["text"]]
    assert buff and _resolve_skill_line_keys(buff[0]["badge_text"]) == ["spell_dmg_additional"]


def test_no_whole_blob_single_line():
    # The old bug: the entire "Activates the Aura … 16% additional Lightning Damage" was ONE unparseable line.
    for ln in _lines("electric_conversion"):
        assert not ("gain the following buff" in ln["text"].lower() and "Lightning Damage" in ln["text"])
