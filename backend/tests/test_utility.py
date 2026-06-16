"""engine.utility.apply_aura_buffs — scales aura buffs by the TRUE aggregated Aura Effect (gear/talent/custom/
support + the aura's own per-stack), inside the compute loop. This is what makes custom/support Aura Effect and
the self-feedback actually reach the aura's buffs."""
import json
import os

from server import _parse_custom_mod_text as P, _translate_condition_expr as T
from engine.aura_resolver import resolve_auras
from engine.utility import apply_aura_buffs
from engine.models import BuildSource, SourceEntry

_SKILLS = os.path.join(os.path.dirname(__file__), "..", "..", "data", "seasons", "SS12", "_skills.json")
_BY_ID = {s["item_id"]: s for s in json.load(open(_SKILLS, encoding="utf-8"))["skills"]}


def _cruelty():
    return resolve_auras([{"skill_id": "cruelty", "level": 20, "enabled": True}], _BY_ID, P, T)


def _src_with_aura_effect(inc):
    src = BuildSource()
    if inc:
        src.add_with_source("aura_effect_inc", inc, SourceEntry(
            stat="aura_effect_inc", amount=inc, source_type="custom", label="Custom", text="Aura Effect", points=1))
    return src


def test_aura_effect_from_other_sources_scales_the_buff():
    # Cruelty 19% attack-damage at Lv20, with +30% Aura Effect from custom/support → 19 × 1.30 = 24.7%.
    buffs, _st, _sc, meta = _cruelty()
    src = _src_with_aura_effect(0.30)
    summ = apply_aura_buffs(src, buffs, meta, frozenset(), {"cruelty_stacks": 0})
    assert round(src.total("attack_dmg_additional") * 100, 1) == 24.7
    assert round(summ[0]["aura_effect_inc"], 2) == 0.30


def test_zero_aura_effect_is_just_the_base():
    buffs, _st, _sc, meta = _cruelty()
    src = _src_with_aura_effect(0.0)
    apply_aura_buffs(src, buffs, meta, frozenset(), {"cruelty_stacks": 0})
    assert round(src.total("attack_dmg_additional") * 100, 1) == 19.0


def test_self_per_stack_aura_effect_feeds_back_into_own_buffs():
    # 10 Cruelty stacks → +25% ADDITIONAL Aura Effect (2.5%/stack, unscaled), on top of +10% INCREASED custom.
    # Increased and additional are separate factors: 19 × (1 + 0.10) × (1 + 0.25) = 26.125%.
    buffs, _st, _sc, meta = _cruelty()
    src = _src_with_aura_effect(0.10)
    apply_aura_buffs(src, buffs, meta, frozenset(), {"cruelty_stacks": 10})
    assert round(src.total("aura_effect_inc"), 2) == 0.10
    assert round(src.total("aura_effect_additional"), 2) == 0.25   # 10 × 2.5%, NOT scaled by the +10% increased
    assert round(src.total("attack_dmg_additional") * 100, 3) == 26.125


def test_full_cruelty_stacks_with_increased_is_multiplicative():
    # The owner's worked example: 40 stacks (+100% additional) with +30% increased → 19 × 1.3 × 2.0 = 49.4%.
    buffs, _st, _sc, meta = _cruelty()
    src = _src_with_aura_effect(0.30)
    apply_aura_buffs(src, buffs, meta, frozenset(), {"cruelty_stacks": 40})
    assert round(src.total("aura_effect_additional"), 2) == 1.00
    assert round(src.total("attack_dmg_additional") * 100, 1) == 49.4
