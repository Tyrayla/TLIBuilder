"""Aura/Focus buff resolution: parse UNSCALED buffs (interpolated across Lv1/Lv20 anchors), stacking → per-aura
condition, NYI surfacing. Aura Effect scaling itself is tested in test_utility (engine-side)."""
import json
import os

from server import _parse_custom_mod_text as P, _translate_condition_expr as T
from engine.aura_resolver import resolve_auras

from persistence import season_manager
_BY_ID = {s["item_id"]: s for s in season_manager.load_skills("SS12")["skills"]}


def _resolve(skill_id, level):
    return resolve_auras([{"skill_id": skill_id, "level": level, "enabled": True}], _BY_ID, P, T)


def _attack_base(skill_id, level):
    buffs, _st, _sc, _m = _resolve(skill_id, level)
    vals = [b["base_amount"] for b in buffs
            if b["stat_key"] == "attack_dmg_additional" and b.get("condition_expr") is None]
    return vals[0] if vals else None


def test_cruelty_interpolates_attack_damage_linearly():
    # Lv1 9.5%, Lv20 19% → Lv16 ~17% (matches Tyra's hand-collected Lv16 value). Base values, unscaled.
    assert round(_attack_base("cruelty", 1) * 100, 1) == 9.5
    assert round(_attack_base("cruelty", 20) * 100, 1) == 19.0
    assert round(_attack_base("cruelty", 16) * 100, 1) == 17.0


def test_disabled_aura_resolved_but_marked_disabled():
    # Disabled auras are STILL resolved (so the Skill panel shows their stats marked "Disabled"); the engine-side
    # apply_aura_buffs is what skips folding them into the source (see test_utility). meta.enabled flags the state.
    buffs, _st, _sc, meta = resolve_auras([{"skill_id": "cruelty", "level": 20, "enabled": False}], _BY_ID, P, T)
    assert buffs != []
    assert meta["cruelty"]["enabled"] is False


def test_non_aura_skill_ignored():
    buffs, _st, _sc, _m = _resolve("chain_lightning", 20)
    assert buffs == []


def test_charged_flames_grants_fire_damage():
    buffs, _st, _sc, _m = _resolve("charged_flames", 20)
    fire = [b["base_amount"] for b in buffs if b["stat_key"] == "fire_dmg_additional"]
    assert fire and fire[0] > 0


def test_cruelty_stacking_buff_becomes_a_per_stack_condition():
    # Cruelty: "2.5% additional Aura Effect per stack … Stacks up to 40" → a settable cruelty_stacks condition
    # and a per-stack buff gated by {op:per, key:cruelty_stacks}.
    buffs, _st, stack_conds, meta = _resolve("cruelty", 20)
    sc = [s for s in stack_conds if s["key"] == "cruelty_stacks"]
    assert sc and sc[0]["max"] == 40
    per = [b for b in buffs if b["stat_key"] == "aura_effect_additional"
           and (b.get("condition_expr") or {}).get("key") == "cruelty_stacks"]
    assert per and per[0]["is_aura_effect"] and per[0]["per_stack"]
    assert round(per[0]["base_amount"] * 100, 1) == 2.5
    assert meta["cruelty"]["stack_condition"] == "cruelty_stacks" and meta["cruelty"]["max_stacks"] == 40
