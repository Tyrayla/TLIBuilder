"""Split Shot (split_shot) — a Projectile Attack (347% WAD, Physical, Dexterity) that fires 3 projectiles which
"cannot hit the same enemy" (NO Shotgun Effect → single-target = 1 hit) and its four canvas supports:

  - Collaboration (Noble):  +roll% additional damage per +1 Projectile Quantity (count = intrinsic 2 + all +qty).
  - Diversion (Magnificent): +5 Projectile Quantity + a plain damage roll; stays spread (still 1 hit ST).
  - Volley (Magnificent): +2 Projectile Quantity + grants Shotgun Effect (N projectiles shotgun one target,
        falloff coefficient 77% → each subsequent deals 1−0.77 = 23%) + a negative damage roll.
  - Rapid Advance (Noble): turns Split Shot into a channeled attack (1.5/s base × attack speed, fired SMOOTHLY —
        no 30 Hz breakpoint; +100% additional AS → 3/s), −50% additional damage, per-additional-max-stack bonus.
"""
import pytest
from engine.skill_resolver import resolve_skill
from server import engine_stats, EngineStatsRequest
from tests.mock_build import make_request, DUAL_WEAPONS, weapon

COLLAB = "split_shot_collaboration_noble"
DIVERSION = "split_shot_diversion_magnificent"
RAPID = "split_shot_rapid_advance_noble"
VOLLEY = "split_shot_volley_magnificent"


def _skill_data(iid="split_shot"):
    import json, os
    d = json.load(open(os.path.join(os.path.dirname(__file__), "..", "..", "data", "seasons", "SS12", "_skills.json"), encoding="utf-8"))
    items = d if isinstance(d, list) else d.get("skills") or d.get("items") or []
    return next(x for x in items if x.get("item_id") == iid)


def _flat_item(name, pairs):
    return {"item_name": name, "contributions": [
        {"stat": k, "display_value": v, "unit": "", "slot": "ring1", "item_name": name, "text": f"{name}:{k}"}
        for k, v in pairs]}


def _off(supports=None, gear=None, conds=None):
    # Split Shot is an ATTACK → always keep real weapons; `gear` adds extra items on top (never replaces them).
    g = DUAL_WEAPONS + (gear or [])
    req = make_request("split_shot", 20, attached_supports=supports or [], gear=g, extra_conditions=conds or {})
    r = engine_stats(EngineStatsRequest(**req))
    r = r if isinstance(r, dict) else r.model_dump()
    return r["offense"]


def _off_single(supports=None, aps=1.5, gear=None, conds=None):
    """One clean weapon of a known base APS (no dual-wield attack-speed grant) → deterministic channel rate."""
    g = [weapon("weapon1", "Bow", 100, 200, aps, 600)] + (gear or [])
    req = make_request("split_shot", 20, attached_supports=supports or [], gear=g, dual_wield=False,
                       extra_conditions=conds or {})
    r = engine_stats(EngineStatsRequest(**req))
    r = r if isinstance(r, dict) else r.model_dump()
    return r["offense"]


def _sup(item_id, rank=5, slot=1, level=20):
    return {"item_id": item_id, "slot": slot, "level": level, "rank": rank, "enabled": True}


# ── Resolver ──────────────────────────────────────────────────────────────────
def test_resolver_fields():
    r = resolve_skill(_skill_data())
    assert r.supported and not r.is_spell
    assert r.main_stat == ["dexterity"]
    assert r.shotgun_requires_grant is True
    assert r.channeled is None                       # base is not channeled (Rapid Advance installs it)
    f1 = r.hit_forms_by_level[1][0]
    f20 = r.hit_forms_by_level[20][0]
    assert f1.effectiveness_pct == pytest.approx(237.0)
    assert f20.effectiveness_pct == pytest.approx(347.0)
    assert f20.hit_count == 3 and f20.scales_with_projectiles
    assert f20.shotgun_falloff == pytest.approx(0.77)


# ── Spread: base + Diversion hit a single target ONCE (no Shotgun Effect) ───────
def test_base_is_single_hit_spread():
    off = _off()
    assert off["hit_forms"][0]["hits_per_fire"] == 1
    assert off["hit_forms"][0]["shotgun_mult"] == pytest.approx(1.0)


def test_diversion_stays_spread_but_adds_damage():
    base = _off()
    div = _off(supports=[_sup(DIVERSION)])
    assert div["hit_forms"][0]["hits_per_fire"] == 1          # +5 quantity, still spread single-target
    assert div["hit_forms"][0]["shotgun_mult"] == pytest.approx(1.0)
    assert div["total_dps"] > base["total_dps"]               # +20% rank + specific roll


# ── Volley: grants Shotgun Effect → N projectiles stack with 77% falloff ────────
def test_volley_grants_shotgun():
    vol = _off(supports=[_sup(VOLLEY)])
    # 3 base + 2 from Volley = 5 projectiles on one target.
    assert vol["hit_forms"][0]["hits_per_fire"] == 5
    assert vol["hit_forms"][0]["shotgun_mult"] == pytest.approx(1.0 + 4 * (1.0 - 0.77))   # = 1.92


def test_volley_shotgun_scales_with_projectile_quantity():
    vol = _off(supports=[_sup(VOLLEY)], gear=[_flat_item("Q", [("projectile_quantity_flat", 3)])])
    assert vol["hit_forms"][0]["hits_per_fire"] == 8          # 3 + 2 + 3
    assert vol["hit_forms"][0]["shotgun_mult"] == pytest.approx(1.0 + 7 * (1.0 - 0.77))


def test_projectile_quantity_alone_does_not_shotgun_without_grant():
    """+Projectile Quantity with no Shotgun-Effect grant still lands 1 on a single target (spread)."""
    off = _off(gear=[_flat_item("Q", [("projectile_quantity_flat", 5)])])
    assert off["hit_forms"][0]["hits_per_fire"] == 1


# ── Collaboration: +roll% additional damage per +1 Projectile Quantity ──────────
def test_collaboration_scales_with_projectile_quantity():
    base = _off()
    collab = _off(supports=[_sup(COLLAB)])
    more_qty = _off(supports=[_sup(COLLAB)], gear=[_flat_item("Q", [("projectile_quantity_flat", 5)])])
    assert collab["total_dps"] > base["total_dps"]
    assert more_qty["total_dps"] > collab["total_dps"]        # count 2 → 7 raises the per-quantity bonus


# ── Rapid Advance: channel transform ────────────────────────────────────────────
def test_rapid_advance_channels_at_three_per_second():
    # Keys off the WEAPON attack rate and fires SMOOTHLY (no 30 Hz breakpoint): 1.5 base × the +100% additional = 3/s.
    ra = _off_single(supports=[_sup(RAPID)], aps=1.5)
    assert "channeled" in [t.lower() for t in ra["skill_tags"]]
    assert ra["channel_attack_ticks"] == 0                   # no breakpoint snapping
    assert ra["skills_per_second"] == pytest.approx(3.0)
    assert ra["channeled_max_stacks"] == 5


def test_channel_rate_keys_off_weapon_attack_speed():
    """The channel is weapon-APS-driven: a faster weapon → a faster (smooth) channel rate."""
    slow = _off_single(supports=[_sup(RAPID)], aps=1.5)      # 1.5 × 2 = 3.0/s
    fast = _off_single(supports=[_sup(RAPID)], aps=3.0)      # 3.0 × 2 = 6.0/s
    assert fast["skills_per_second"] > slow["skills_per_second"]


def test_rapid_advance_rate_is_smooth_not_snapped():
    """Channeled attacks fire at the SMOOTH rate — NO 30 Hz breakpoint (Split Shot's old snap was removed in-game).
    A small attack-speed bump changes the rate continuously; a breakpoint would freeze it across a tick band."""
    base = _off(supports=[_sup(RAPID)])
    more = _off(supports=[_sup(RAPID)], gear=[_flat_item("AS", [("attack_speed_inc", 0.05)])])
    assert base["channel_attack_ticks"] == 0 and more["channel_attack_ticks"] == 0   # never quantized
    assert more["skills_per_second"] > base["skills_per_second"]                       # +5% AS raises it (no plateau)


def test_rapid_advance_damage_penalty():
    base = _off()
    ra = _off(supports=[_sup(RAPID, rank=1)])                 # rank 1 = 0% universal → isolate the −50%
    # per-fire damage is halved by the −50% additional (rate/shotgun aside).
    base_per = base["hit_forms"][0]["dps_contribution"] / base["hit_forms"][0]["fires_per_sec"]
    ra_per = ra["hit_forms"][0]["dps_contribution"] / ra["hit_forms"][0]["fires_per_sec"]
    assert ra_per == pytest.approx(base_per * 0.5, rel=1e-3)


def test_rapid_advance_per_additional_max_stack():
    ra = _off(supports=[_sup(RAPID, rank=1)])
    ra_stacks = _off(supports=[_sup(RAPID, rank=1)], gear=[_flat_item("S", [("max_channeled_stacks_flat", 3)])])
    assert ra_stacks["channeled_max_stacks"] == 8             # base 5 + 3
    assert ra_stacks["total_dps"] > ra["total_dps"]           # +3 additional stacks → +~67.5% additional


def test_rapid_advance_plus_volley_shotguns_in_channel():
    """Volley (3rd) + Rapid Advance (5th) coexist → the channel shotguns the target."""
    ra_vol = _off(supports=[_sup(RAPID, slot=1), _sup(VOLLEY, slot=1)])
    assert ra_vol["hit_forms"][0]["hits_per_fire"] == 5
    assert ra_vol["skills_per_second"] > 0 and ra_vol["channel_attack_ticks"] == 0   # smooth, no breakpoint
