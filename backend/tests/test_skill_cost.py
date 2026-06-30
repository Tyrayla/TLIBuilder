"""Skill mana/life cost model (engine.skill_cost): base × support multipliers × cost mods, the Arcane mana→life
split, Frozen Lotus base-zero, percentage base costs, the override, and the per-use fold into consumption."""
import pytest
from types import SimpleNamespace

from engine.models import BuildSource
from engine.skill_cost import compute_skill_cost, has_skill_cost
from engine.mod_parser import _parse_custom_mod_text as P
from engine.core_talent_resolver import _resolve_talent
from server import engine_stats, EngineStatsRequest, _translate_condition_expr as T
from tests.mock_build import make_request, DUAL_WEAPONS


def _src(**totals):
    s = BuildSource()
    for k, v in totals.items():
        s.add(k, v)
    return s


def _skill(cost=0.0, is_percent=False):
    return SimpleNamespace(mana_cost=cost, mana_cost_is_percent=is_percent, is_spell=True)


def _supports(*mana_costs):
    """attached_supports + skills_by_id for supports with the given mana_cost percentages (e.g. '110.0%')."""
    sup = [{"item_id": f"s{i}", "slot": 1, "enabled": True} for i in range(len(mana_costs))]
    by_id = {f"s{i}": {"mana_cost": mc, "name": f"Support {i}"} for i, mc in enumerate(mana_costs)}
    return sup, by_id


# ── Base + multipliers ────────────────────────────────────────────────────────────
def test_flat_base_no_mods():
    r = compute_skill_cost(_skill(15.0), _src(), [], {})
    assert r.mana_cost == pytest.approx(15.0) and r.life_cost == 0.0


def test_support_multipliers_are_multiplicative():
    sup, by_id = _supports("110.0%", "110.0%")
    r = compute_skill_cost(_skill(10.0), _src(), sup, by_id, slot=1)
    assert r.support_mult == pytest.approx(1.21)        # 1.10 × 1.10
    assert r.mana_cost == pytest.approx(12.1)


def test_inc_and_flat_join_base_then_scale():
    # (base + flat) × (1 + inc): (15 + 35) × (1 + 4.5) = 275  (Awakening Skull shape, pre-Arcane).
    r = compute_skill_cost(_skill(15.0), _src(skill_cost_inc=4.5, skill_cost_flat=35.0), [], {})
    assert r.mana_cost == pytest.approx(275.0)


def test_reduction_lowers_and_clamps_at_zero():
    r = compute_skill_cost(_skill(20.0), _src(skill_cost_reduction=0.5), [], {})
    assert r.mana_cost == pytest.approx(10.0)            # 20 × (1 − 0.5)
    z = compute_skill_cost(_skill(20.0), _src(skill_cost_reduction=2.0), [], {})
    assert z.mana_cost == pytest.approx(0.0)             # clamped ≥ 0


def test_percentage_base_is_pct_of_max_mana():
    # Moon Strike "1%" = 1% of Max Mana per use, scaling with multipliers.
    sup, by_id = _supports("110.0%")
    r = compute_skill_cost(_skill(1.0, is_percent=True), _src(max_mana=2000.0), sup, by_id, slot=1)
    assert r.base_cost == pytest.approx(20.0)            # 1% × 2000
    assert r.mana_cost == pytest.approx(22.0)            # × 1.10


# ── Arcane (mana → life) ──────────────────────────────────────────────────────────
def test_arcane_full_conversion_all_life():
    # Awakening Skull: 100% mana cost → life. (15 + 35) × 5.5 = 275, all paid as life.
    r = compute_skill_cost(_skill(15.0), _src(skill_cost_inc=4.5, skill_cost_flat=35.0, mana_cost_to_life_cost=1.0), [], {})
    assert r.mana_cost == pytest.approx(0.0) and r.life_cost == pytest.approx(275.0)


def test_arcane_half_split():
    r = compute_skill_cost(_skill(100.0), _src(mana_cost_to_life_cost=0.5), [], {})
    assert r.mana_cost == pytest.approx(50.0) and r.life_cost == pytest.approx(50.0)


def test_bulls_rage_percent_base_converts_to_max_life():
    # Bull's Rage: 15% base + intrinsic 100% mana→life. Conversion happens BEFORE the % resolves against a pool, so
    # it's 15% of MAX LIFE paid as Life (NOT 15% of Max Mana moved to life).
    rs = SimpleNamespace(name="Bull's Rage", mana_cost=15.0, mana_cost_is_percent=True,
                         intrinsic_mana_to_life=1.0, is_spell=True)
    r = compute_skill_cost(rs, _src(max_mana=2000.0, max_life=5000.0), [], {})
    assert r.arcane_fraction == pytest.approx(1.0)
    assert r.mana_cost == pytest.approx(0.0)
    assert r.life_cost == pytest.approx(0.15 * 5000.0)      # 750 — uses Max LIFE, not Max Mana (2000)


def test_bulls_rage_intrinsic_detected_from_skill_text():
    from engine.skill_resolver import resolve_skill
    rs = resolve_skill({"item_id": "bull_s_rage", "mana_cost": "15%",
                        "description_lines": ["All Mana costs of the skill will be converted to Life costs."]})
    assert rs.intrinsic_mana_to_life == pytest.approx(1.0)
    assert rs.mana_cost_is_percent is True


# ── Frozen Lotus / no-cost + override ──────────────────────────────────────────────
def test_frozen_lotus_zeros_base_but_flat_survives():
    # skill_no_mana_cost zeros the BASE only; a "+80 Skill Cost" still costs (scaled). (0 + 80) × 1 = 80.
    via_cond = compute_skill_cost(_skill(15.0), _src(skill_cost_flat=80.0), [], {},
                                  condition_state={"skill_no_mana_cost": True})
    assert via_cond.base_cost == 0.0 and via_cond.mana_cost == pytest.approx(80.0)
    # Same via a source flag (support-emitted).
    via_src = compute_skill_cost(_skill(15.0), _src(skill_no_mana_cost=1.0), [], {})
    assert via_src.mana_cost == pytest.approx(0.0)       # no flat → 0


def test_override_replaces_final_cost():
    r = compute_skill_cost(_skill(50.0), _src(mana_cost_override=5.0), [], {})
    assert r.mana_cost == pytest.approx(5.0) and "override" in " ".join(r.flags).lower()


def test_has_skill_cost():
    assert not has_skill_cost(compute_skill_cost(_skill(0.0), _src(), [], {}))
    assert has_skill_cost(compute_skill_cost(_skill(10.0), _src(), [], {}))


# ── Parser + Frozen Lotus core talent ──────────────────────────────────────────────
def test_cost_parser_and_arcane_disambiguation():
    def kv(t): return {r["stat_key"]: round(r["amount"], 4) for r in (P(t) or [])}
    assert kv("+10 % Skill Cost") == {"skill_cost_inc": 0.1}
    assert kv("+(400-500) % Skill Cost") == {"skill_cost_inc": 4.5}
    assert kv("15 % increased Mana Cost") == {"skill_cost_inc": 0.15}     # NOT mana_cost_to_life_cost
    assert kv("20 % reduced Mana Cost") == {"skill_cost_inc": -0.2}
    assert kv("+30 Skill Cost") == {"skill_cost_flat": 30.0}
    assert kv("Converts 100 % of Mana Cost to Life Cost") == {"mana_cost_to_life_cost": 1.0}
    # The Arcane conversion must NOT be reachable by a plain "increased Mana Cost".
    assert "mana_cost_to_life_cost" not in kv("15 % increased Mana Cost")


def test_frozen_lotus_core_talent_yields_flag():
    _, flags, statuses = _resolve_talent("Frozen Lotus", ["Skills no longer cost Mana (Max Divinity Effect: 1)"], P, T)
    assert "skill_no_mana_cost" in flags
    assert statuses and statuses[0]["resolved"] is True


# ── Integration: cost is a SEPARATE drain (NOT consumption), summed per active skill ───
def test_cost_is_separate_drain_not_consumption():
    req = make_request("chromatic_shot", 20, gear=DUAL_WEAPONS)
    base = engine_stats(EngineStatsRequest(**req)); base = base if isinstance(base, dict) else base.model_dump()
    req2 = make_request("chromatic_shot", 20, gear=DUAL_WEAPONS)
    req2["custom_mods"] = ["+200 % Skill Cost"]
    hi = engine_stats(EngineStatsRequest(**req2)); hi = hi if isinstance(hi, dict) else hi.model_dump()
    c, sc = hi["consumption"], hi["skill_cost"]
    # Per-skill cost breakdown names the skill; +200% Skill Cost raises it vs base.
    entry = next(s for s in sc["per_skill"] if s["skill_name"] == hi["offense"]["skill_name"])
    assert entry["mana_per_cast"] > 8.0      # base 8 × (1 + 2.0)
    assert sc["total_mana_per_sec"] > base["skill_cost"]["total_mana_per_sec"]
    # Cost is NOT consume: no consume affix → mana_per_sec (consumed) + consumed_recently stay 0; cost lives in its
    # own field and in recovery.skill_cost_mana_per_sec (subtracted from Net Mana Recovery, not "Mana Consumed").
    assert c["mana_per_sec"] == pytest.approx(0.0, abs=1e-6)
    assert c["consumed_recently_mana"] == pytest.approx(0.0, abs=1e-6)
    assert c["skill_cost_mana_per_sec"] == pytest.approx(sc["total_mana_per_sec"], rel=1e-6)
    assert hi["recovery"]["skill_cost_mana_per_sec"] == pytest.approx(sc["total_mana_per_sec"], rel=1e-6)
    assert hi["recovery"]["consumption_mana_per_sec"] == pytest.approx(0.0, abs=1e-6)
