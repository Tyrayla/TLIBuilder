"""Soft-invalidation slot gating (backend/server.py: EngineStatsRequest.invalid_slots).

Two game rules let a normally-passive-tagged skill (Focus / Spirit Magus) sit in an ACTIVE slot
(1-5) — Steel Vanguard's "Knowledgeable" core talent and Iris's "Merged Spirit Magi" trait. The
RENDERER decides which slots are currently invalid (missing the enabling talent/trait) and sends
their indices as `invalid_slots`; the backend doesn't know or care about tags — it just folds any
listed slot into the SAME `enabled` gate a user-disabled skill already uses everywhere (offense
via `main_enabled`, reservation/sealing via `skills_input[...]["enabled"]`, and the attached-
supports host-enable gate via `_disabled_slots`). The skill itself is never dropped from `skills`.

Uses Cruelty (a 50% Sealed Mana Aura — see test_reservation.py) purely for its known reservation
math, and Focused Slash + its Duel support (see test_support_gating.py) for known offense/support
math. Neither is actually Focus/Spirit-Magus-tagged; that tag gate is a renderer-side concern
(computeSkillSlotEligibility in api/client.ts) exercised by the renderer suite. The backend gate
under test here is tag-agnostic by design, so any skill works to prove the plumbing.
"""
import json
import os

from server import engine_stats, EngineStatsRequest

_SKILLS = os.path.join(os.path.dirname(__file__), "..", "..", "data", "seasons", "SS12", "_skills.json")
_BY_ID = {s["item_id"]: s for s in json.load(open(_SKILLS, encoding="utf-8"))["skills"]}


def _cruelty(slot):
    return [{"slot": slot, "skill_id": "cruelty", "level": 20, "enabled": True}]


def _cruelty_reservation(slot, invalid_slots=None):
    return engine_stats(EngineStatsRequest(
        slots=[], slates=[], gear=[], character=[], skills=_cruelty(slot),
        custom_mods=["+1000 Max Mana"], condition_state={},
        invalid_slots=invalid_slots or []))["reservation"]


def _baseline_sword(slot):
    def c(stat, val):
        return {"stat": stat, "display_value": val, "unit": "", "item_name": "Baseline 1H Sword",
                "text": "base", "slot": slot, "condition": None}
    return {"item_name": "Baseline 1H Sword", "base_type": "One-Handed Sword", "slot": slot,
            "contributions": [c("physical_dmg_gear_flat_min", 100), c("physical_dmg_gear_flat_max", 150),
                              c("weapon_attack_speed", 1.5), c("weapon_crit_rating_flat", 500)]}


def _focused_slash_req(invalid_slots=None, supports=None, include_field=True):
    kwargs = dict(
        slots=[None, None, None, None], condition_state={},
        gear=[_baseline_sword("weapon1"), _baseline_sword("weapon2")],
        skills=[{"slot": 1, "skill_id": "focused_slash", "level": 14, "enabled": True}],
        main_skill={"skill_id": "focused_slash", "level": 14},
        attached_supports=supports or [], characterLevel=100)
    if include_field:
        kwargs["invalid_slots"] = invalid_slots or []
    return EngineStatsRequest(**kwargs)


def _focused_slash_offense(invalid_slots=None, supports=None, include_field=True):
    return engine_stats(_focused_slash_req(invalid_slots, supports, include_field))["offense"]


def _focused_slash_dps(invalid_slots=None, supports=None, include_field=True):
    # A disabled/invalidated main skill returns `offense: None` entirely (pre-existing gate behavior — verified
    # identical for a plain user-disabled skill, not something invalid_slots introduces) rather than a
    # total_dps of 0. Normalize that here so callers can compare a single scalar.
    offense = _focused_slash_offense(invalid_slots, supports, include_field)
    return 0 if offense is None else offense["total_dps"]


# ── 1. Invalidated slot -> zero offense AND zero reservation ────────────────────────────────

def test_invalidated_active_slot_zero_offense():
    assert _focused_slash_dps() > 0
    assert _focused_slash_offense(invalid_slots=[1]) is None   # main-skill-disabled gate: no offense at all
    assert _focused_slash_dps(invalid_slots=[1]) == 0


def test_invalidated_active_slot_zero_reservation():
    # Sanity: Cruelty in slot 1 with nothing invalidated seals the expected 500 (matches test_reservation.py's
    # passive-slot baseline — see next test for the direct passive/active comparison).
    assert round(_cruelty_reservation(1)["sealed_mana"], 1) == 500.0
    invalidated = _cruelty_reservation(1, invalid_slots=[1])
    assert invalidated["sealed_mana"] == 0.0
    assert invalidated["unsealed_mana"] == invalidated["max_mana"]


# ── 2. Valid active-slot skill == same skill in a passive slot (the owner's explicit requirement) ──

def test_valid_active_slot_reservation_matches_passive_slot():
    passive = _cruelty_reservation(6)               # slot 6 = passive, untouched by invalid_slots
    active_uninvalidated = _cruelty_reservation(1, invalid_slots=[])  # slot 1 = active, explicitly NOT invalidated
    assert round(passive["sealed_mana"], 1) == round(active_uninvalidated["sealed_mana"], 1) == 500.0


# ── 3. Backward compatibility: invalid_slots absent entirely behaves like invalid_slots=[] ──────────

def test_invalid_slots_absent_is_backward_compatible():
    req = _focused_slash_req(include_field=False)
    assert "invalid_slots" not in req.model_fields_set   # truly absent, not defaulted-then-set
    assert req.invalid_slots == []                        # the pydantic default still applies
    without_field = engine_stats(req)["offense"]["total_dps"]
    with_empty_field = _focused_slash_dps(invalid_slots=[])
    assert without_field == with_empty_field
    assert without_field > 0


# ── 4. Supports attached to an invalidated slot also drop ───────────────────────────────────────────

def test_supports_attached_to_invalidated_slot_also_drop():
    sup = [{"item_id": "focused_slash_duel_magnificent", "skill_type": "magnificent_support_skill",
            "rank": 1, "level": 1}]
    baseline = _focused_slash_dps()
    with_support = _focused_slash_dps(supports=sup)
    assert with_support > baseline   # sanity: the support contributes when the slot is valid
    invalidated_with_support = _focused_slash_dps(invalid_slots=[1], supports=sup)
    assert invalidated_with_support == 0   # not just reduced to baseline — the whole slot (skill + support) is inert


# ── 5. Multiple active slots simultaneously valid — no count cap anywhere in the backend gate ───────

def test_multiple_valid_active_slots_no_count_cap():
    # Two Aura-slot skills, both placed in ACTIVE slots (1, 2), neither invalidated. The backend has no notion
    # of "how many" — invalid_slots is a per-slot set, not a counter — so both seal simultaneously (500 + 500),
    # confirming nothing silently caps a second occupant.
    r = engine_stats(EngineStatsRequest(
        slots=[], slates=[], gear=[], character=[], skills=_cruelty(1) + _cruelty(2),
        custom_mods=["+1000 Max Mana"], condition_state={}, invalid_slots=[]))["reservation"]
    assert round(r["sealed_mana"], 1) == 1000.0
    assert len(r["per_skill"]) == 2


def test_one_invalidated_one_valid_active_slot_independent():
    # Slot 1 invalidated, slot 2 valid — only slot 1's contribution zeroes; slot 2 is untouched.
    r = engine_stats(EngineStatsRequest(
        slots=[], slates=[], gear=[], character=[], skills=_cruelty(1) + _cruelty(2),
        custom_mods=["+1000 Max Mana"], condition_state={}, invalid_slots=[1]))["reservation"]
    assert round(r["sealed_mana"], 1) == 500.0
    assert len(r["per_skill"]) == 1
