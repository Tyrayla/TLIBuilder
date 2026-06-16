"""Per-slot support routing: a support on a NON-main slot must be computed into THAT slot's offense, and
must not leak into other slots. Guards the frontend fix that sends every slot's supports (tagged with the
host skill's slot) instead of only the main skill's — see statsPayload.ts buildEngineStatsPayload.
"""
from server import engine_stats, EngineStatsRequest
from tests.mock_build import make_request


def _req(with_slot2_support: bool) -> dict:
    """chain_lightning in slot 1 (main) AND slot 2 (secondary); an added-lightning support on slot 2 only."""
    supports = ([{"item_id": "added_lightning_damage", "skill_type": "support_skill", "level": 20, "slot": 2}]
                if with_slot2_support else [])
    return make_request(
        "chain_lightning", 14,
        skills=[{"slot": 1, "skill_id": "chain_lightning", "level": 14},
                {"slot": 2, "skill_id": "chain_lightning", "level": 14}],
        main_skill={"skill_id": "chain_lightning", "level": 14},
        attached_supports=supports,
    )


def _slot_dps(resp: dict, slot: int):
    so = resp.get("slot_offense") or {}
    o = so.get(slot) or so.get(str(slot)) or {}
    return o.get("total_dps_vs_target")


def test_non_main_slot_support_is_computed_without_leaking():
    with_sup = engine_stats(EngineStatsRequest(**_req(True)))
    without = engine_stats(EngineStatsRequest(**_req(False)))

    d2_with, d2_without = _slot_dps(with_sup, 2), _slot_dps(without, 2)
    d1_with, d1_without = _slot_dps(with_sup, 1), _slot_dps(without, 1)

    assert d2_with and d2_without, "slot 2 should have a computed offense"
    # The slot-2 support raises slot 2's DPS (it's actually computed there now)...
    assert d2_with > d2_without, f"slot-2 support not applied: {d2_without} -> {d2_with}"
    # ...and does NOT leak into the main slot's offense (no cross-slot contamination).
    assert d1_with == d1_without, f"slot-2 support leaked into slot 1: {d1_without} vs {d1_with}"


def _cross_cat_req(with_slot2_support: bool) -> dict:
    """Spell main skill in slot 1, ATTACK skill (berserking_blade) in slot 2 with an attack added-flat
    support — the support must categorize against slot 2 (attack), not the spell main skill, or its flat
    damage lands in the wrong pool and contributes nothing."""
    supports = ([{"item_id": "added_physical_damage", "skill_type": "support_skill", "level": 20, "slot": 2}]
                if with_slot2_support else [])
    return make_request(
        "chain_lightning", 14,
        skills=[{"slot": 1, "skill_id": "chain_lightning", "level": 14},
                {"slot": 2, "skill_id": "berserking_blade", "level": 20}],
        main_skill={"skill_id": "chain_lightning", "level": 14},
        attached_supports=supports,
    )


def test_support_categorized_by_host_slot_not_main_skill():
    with_sup = engine_stats(EngineStatsRequest(**_cross_cat_req(True)))
    without = engine_stats(EngineStatsRequest(**_cross_cat_req(False)))
    # The attack support must lift the attack skill's (slot 2) DPS even though the main skill is a spell.
    assert _slot_dps(with_sup, 2) > _slot_dps(without, 2), "attack support mis-categorized by main (spell) skill"
    # The spell main slot is untouched by the slot-2 attack support.
    assert _slot_dps(with_sup, 1) == _slot_dps(without, 1)
