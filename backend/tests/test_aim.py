"""Aim / Euphoria buff: a "Triggers Lv. N Aim while standing still" gear line auto-enables the buff. Euphoria
grants global -16% Attack & Cast Speed (all levels) + Ranged/Beam-scoped +additional damage AND +additional
Ailment Damage = (15 + level)% (Lv20 = 35%, -1%/level below). Not affected by Empower (aggregator base effects
are never empower-scaled). Full-uptime while toggled on. Source: TLI _skills.json "aim" / glossary "Quickness"."""
import pytest
from server import engine_stats, EngineStatsRequest
from tests.mock_build import make_request, DUAL_WEAPONS


def _run(extra_gear, conds=None):
    # split_shot is Ranged-tagged (Attack, Projectile, Physical, Ranged, Horizontal), so the scoped bonus applies.
    gear = DUAL_WEAPONS + extra_gear
    r = engine_stats(EngineStatsRequest(**make_request("split_shot", 20, gear=gear, extra_conditions=conds or {})))
    return r if isinstance(r, dict) else r.model_dump()


def test_aim_trigger_auto_enables_and_applies():
    boots = [{"item_name": "Trigger Boots",
              "unresolved_texts": ["Triggers Lv. 8 Aim while standing still. Interval: 1 s"]}]
    r = _run(boots)
    ac = r["auto_conditions"]
    assert ac.get("aim_active", {}).get("value") is True
    assert ac.get("aim_level", {}).get("value") == 8.0

    # Global -16% Attack Speed (increased) — surfaces in the breakdown.
    as_srcs = r["stats"].get("attack_speed_inc", {}).get("sources", [])
    assert any(s["amount"] == pytest.approx(-0.16) and "Aim" in (s.get("label") or "") for s in as_srcs)

    # Ranged-scoped +23% additional Damage (15 + level=8) — surfaces in slot_sources with scope "ranged".
    dmg = r["stats"].get("dmg_additional", {}).get("slot_sources", [])
    assert any(s.get("scope") == "ranged" and s["amount"] == pytest.approx(0.23)
               and "Aim" in (s.get("label") or "") for s in dmg), dmg
    # Separate +23% additional Ailment Damage, also Ranged-scoped.
    ail = r["stats"].get("ailment_dmg_additional", {}).get("slot_sources", [])
    assert any(s.get("scope") == "ranged" and s["amount"] == pytest.approx(0.23)
               and "Aim" in (s.get("label") or "") for s in ail), ail


def test_aim_level_scales_additional():
    # Lv 20 → +35% additional damage; the -16% AS is constant regardless of level.
    r = _run([{"item_name": "Boots", "unresolved_texts": ["Triggers Lv. 20 Aim while standing still"]}])
    assert r["auto_conditions"].get("aim_level", {}).get("value") == 20.0
    dmg = r["stats"].get("dmg_additional", {}).get("slot_sources", [])
    assert any(s.get("scope") == "ranged" and s["amount"] == pytest.approx(0.35) for s in dmg), dmg


def test_aim_slotted_skill_self_grants():
    # Aim equipped as a buff skill in another slot self-grants Euphoria at its own level (no gear trigger needed).
    req = make_request("split_shot", 20, gear=DUAL_WEAPONS)
    req["skills"] = [{"slot": 1, "skill_id": "split_shot", "level": 20},
                     {"slot": 2, "skill_id": "aim", "level": 15, "enabled": True}]
    r = engine_stats(EngineStatsRequest(**req))
    r = r if isinstance(r, dict) else r.model_dump()
    ac = r["auto_conditions"]
    assert ac.get("aim_active", {}).get("value") is True
    assert ac.get("aim_level", {}).get("value") == 15.0
    dmg = r["stats"].get("dmg_additional", {}).get("slot_sources", [])   # 15 + 15 = 30%
    assert any(s.get("scope") == "ranged" and s["amount"] == pytest.approx(0.30) for s in dmg), dmg


def test_aim_disabled_slot_does_not_grant():
    req = make_request("split_shot", 20, gear=DUAL_WEAPONS)
    req["skills"] = [{"slot": 1, "skill_id": "split_shot", "level": 20},
                     {"slot": 2, "skill_id": "aim", "level": 15, "enabled": False}]
    r = engine_stats(EngineStatsRequest(**req))
    r = r if isinstance(r, dict) else r.model_dump()
    assert "aim_active" not in (r["auto_conditions"] or {})


def test_aim_absent_without_trigger():
    r = _run([{"item_name": "Plain", "unresolved_texts": ["+10 % Movement Speed"]}])
    assert "aim_active" not in (r["auto_conditions"] or {})
    as_srcs = r["stats"].get("attack_speed_inc", {}).get("sources", [])
    assert not any("Aim" in (s.get("label") or "") for s in as_srcs)
