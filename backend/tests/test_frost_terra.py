"""Frost Terra + the Terra Charge model (SS13 Terra system — data/verification/frost-terra.json,
terra-charge-system.json).

Hand-derived ground truth (not recomputed from the implementation):
  - Frost Terra L20 base: "Deals 484 Persistent Cold damage every second for 2 s." A fresh 2s DoT
    instance is applied every 1s and applications STACK (owner-ruled 2026-08-10, Mind-Control-like
    ramp) → steady state = 2 concurrent instances → 484 × 2 = 968/sec before pools.
  - Standard Lv85 dummy: 30% cold resistance → resistance-only DoT target multiplier 0.70.
  - Terra Charge: +26% additional damage for the skill per charge consumed, ADDITIVE per charge
    (1 + 0.26 × N — the per-charge-multiplicative community claim is needs-verification and NOT
    modeled), defaulting to the effective max (1 base + max_terra_charge_stacks_flat).
  - Ground Divide (Lv1): +1 Max Terra Charge stacks, +55.5% Terra Charge Restoration Speed (display),
    +1.5% additional damage for the supported skill.
"""
import pytest

from engine.models import BuildSource
from engine.offense import calculate_offense
from engine.skill_resolver import ResolvedSkill, DotForm, resolve_skill
from persistence import season_manager
from tests.mock_build import make_request
from server import engine_stats, EngineStatsRequest

_SS13_ONLY = pytest.mark.skipif(
    season_manager.get_active_season() != "SS13",
    reason="Frost Terra's Terra-system form ships with SS13 (SS12 catalog predates the charge lines).",
)

FROST_TERRA_L20_BASE = 484.0   # per-instance tick, straight from the L20 progression text
STACKED = 2.0                  # 2s instance / 1s application cadence
COLD_RESIST_MULT = 0.70        # dummy 30% cold res, resistance-only (dot-armor-exclusion)


def _source(**stats) -> BuildSource:
    s = BuildSource()
    for k, v in stats.items():
        s.add(k, v)
    return s


def _terra_dot_skill(terra: bool = True, stacked: float = STACKED) -> ResolvedSkill:
    tags = ["Spell", "Cold", "Area", "Persistent"] + (["Terra"] if terra else [])
    return ResolvedSkill(
        skill_id="test_frost_terra", name="Frost Terra", tags=tags, max_level=20,
        hit_forms_by_level={}, supported=True, is_spell=True,
        base_cast_time=1.0, damage_types=["cold"],
        dot_forms_by_level={20: [DotForm(base_per_second=FROST_TERRA_L20_BASE, dtype="cold",
                                         duration=2.0, stacked_instances=stacked)]},
    )


def _dot_vs_target(skill: ResolvedSkill, source: BuildSource) -> float:
    r = calculate_offense(source, skill, 20)
    rows = [row for row in r.damage_rows if row.kind == "dot"]
    assert len(rows) == 1
    return rows[0].dps_vs_target_final


# ── Resolver (real SS13 catalog) ─────────────────────────────────────────────────────────────────


@_SS13_ONLY
def test_resolver_parses_frost_terra_from_catalog():
    sd = next(s for s in season_manager.load_skills("SS13")["skills"] if s.get("item_id") == "frost_terra")
    r = resolve_skill(sd)
    assert r.supported and r.is_spell
    assert "Terra" in r.tags
    assert r.terra_per_charge_additional == pytest.approx(0.26)
    assert r.base_cast_time == pytest.approx(1.0)
    forms = r.dot_forms_by_level[20]
    assert len(forms) == 1
    f = forms[0]
    assert (f.base_per_second, f.dtype, f.duration, f.stacked_instances) == (484.0, "cold", 2.0, 2.0)
    assert sorted(r.dot_forms_by_level) == list(range(1, 21))


# ── DoT stage units (synthetic skill, clean source) ──────────────────────────────────────────────


def test_stacked_instances_doubles_steady_state():
    # 484 × 2 × 0.70 = 677.6 vs 484 × 1 × 0.70 = 338.8 — stacking is a straight per-form multiplier.
    assert _dot_vs_target(_terra_dot_skill(), _source()) == pytest.approx(
        FROST_TERRA_L20_BASE * STACKED * COLD_RESIST_MULT)
    assert _dot_vs_target(_terra_dot_skill(stacked=1.0), _source()) == pytest.approx(
        FROST_TERRA_L20_BASE * COLD_RESIST_MULT)


def test_terra_skill_dmg_inc_gates_on_terra_tag():
    # +50% Terra Skill Damage joins the DoT increased pool ONLY on a Terra-tagged skill:
    # 968 × 1.5 × 0.70 with the tag; the tagless twin ignores the stat entirely.
    src = _source(terra_skill_dmg_inc=0.50)
    assert _dot_vs_target(_terra_dot_skill(), src) == pytest.approx(
        FROST_TERRA_L20_BASE * STACKED * 1.50 * COLD_RESIST_MULT)
    assert _dot_vs_target(_terra_dot_skill(terra=False), src) == pytest.approx(
        FROST_TERRA_L20_BASE * STACKED * COLD_RESIST_MULT)


def test_terra_additional_multiplies_per_source_enhancement_sums():
    # Two DISTINCT-WORDING additional-Terra-Skill-Damage affixes multiply (1.10 × 1.20) — per the pool's
    # value-stripped affix identity, same-wording sources sum, distinct wordings multiply (like any
    # *_additional pool). Enhancement sources ALWAYS sum additively within their own pool regardless of
    # wording and apply as ONE factor (1 + 0.10 + 0.20) — owner-ruled *_enhancement_additional identity rule.
    from engine.models import SourceEntry
    s = _source()
    s.add_with_source("terra_skill_dmg_additional", 0.10, SourceEntry(
        stat="terra_skill_dmg_additional", amount=0.10, source_type="gear",
        label="Affix A", text="+10 % additional Terra Skill Damage"))
    s.add_with_source("terra_skill_dmg_additional", 0.20, SourceEntry(
        stat="terra_skill_dmg_additional", amount=0.20, source_type="spirit",
        label="Mirrored Shade", text="+20 % additional Terra Skill Damage while having Mirrored Shade"))
    assert _dot_vs_target(_terra_dot_skill(), s) == pytest.approx(
        FROST_TERRA_L20_BASE * STACKED * 1.10 * 1.20 * COLD_RESIST_MULT)
    e = _source()
    e.add_with_source("terra_dmg_enhancement_additional", 0.10, SourceEntry(
        stat="terra_dmg_enhancement_additional", amount=0.10, source_type="gear",
        label="Affix C", text="+10 % Terra Damage Enhancement"))
    e.add_with_source("terra_dmg_enhancement_additional", 0.20, SourceEntry(
        stat="terra_dmg_enhancement_additional", amount=0.20, source_type="talent",
        label="Affix D", text="+20 % Terra Damage Enhancement while on a Terra"))
    assert _dot_vs_target(_terra_dot_skill(), e) == pytest.approx(
        FROST_TERRA_L20_BASE * STACKED * 1.30 * COLD_RESIST_MULT)


# ── Terra Charge model (end-to-end through engine_stats) ─────────────────────────────────────────


def _dps(conds=None, supports=None):
    req = make_request("frost_terra", 20, extra_conditions=conds, attached_supports=supports)
    r = engine_stats(EngineStatsRequest(**req))
    d = r.model_dump() if hasattr(r, "model_dump") else r
    return d["offense"]


@_SS13_ONLY
def test_charge_factor_defaults_to_max_and_is_overridable():
    base = _dps(conds={"terra_charges_consumed": 0})["total_dps"]
    full = _dps()["total_dps"]
    # Default = effective max (1 charge, no stack sources) → exactly the 1.26 MORE factor over 0 charges.
    assert full / base == pytest.approx(1.26, rel=1e-6)
    # Override clamps to the effective max: asking for 99 charges with max 1 is just the default.
    assert _dps(conds={"terra_charges_consumed": 99})["total_dps"] == pytest.approx(full, rel=1e-9)
    # Negative override clamps to 0 charges (the max(0.0, …) floor).
    assert _dps(conds={"terra_charges_consumed": -5})["total_dps"] == pytest.approx(base, rel=1e-9)


@_SS13_ONLY
def test_ground_divide_raises_max_and_default_charges():
    gd = {"item_id": "ground_divide", "slot": 1, "level": 1, "enabled": True}
    off_gd = _dps(supports=[gd])
    off_gd0 = _dps(conds={"terra_charges_consumed": 0}, supports=[gd])
    # Same build either side (support attached in both) so the ratio isolates the charge factor:
    # +1 Max Terra Charge stacks → default 2 charges consumed → 1 + 0.26×2 = 1.52.
    assert off_gd["total_dps"] / off_gd0["total_dps"] == pytest.approx(1.52, rel=1e-6)
    tc = off_gd["terra_charge"]
    assert tc["max_stacks"] == 2
    assert tc["charges_consumed"] == pytest.approx(2.0)
    # +55.5% restoration speed (Lv1) → 0.5s / 1.555 per stack.
    assert tc["restore_seconds_per_stack"] == pytest.approx(0.5 / 1.555, rel=1e-6)


@_SS13_ONLY
def test_terra_charge_info_surfaced_without_supports():
    tc = _dps()["terra_charge"]
    assert tc["max_stacks"] == 1
    assert tc["per_charge_additional"] == pytest.approx(0.26)
    assert tc["restore_seconds_per_stack"] == pytest.approx(0.5)


# ── Mod parser coverage (every Terra line maps to a stat) ────────────────────────────────────────


@pytest.mark.parametrize("text,key,amount", [
    ("+12 % Terra Skill Damage", "terra_skill_dmg_inc", 0.12),
    ("+8 % additional Terra Skill Damage", "terra_skill_dmg_additional", 0.08),
    ("+20 % Terra Damage Enhancement", "terra_dmg_enhancement_additional", 0.20),
    ("+16 % Terra Skill Area", "terra_skill_area_inc", 0.16),
    ("+10 % Terra Skill Duration", "terra_skill_duration_inc", 0.10),
    ("-20 % Terra Skill Duration", "terra_skill_duration_inc", -0.20),
    ("+2 to Terra Skill Level", "terra_skill_level", 2.0),
    ("+75 % Terra Charge Restoration Speed", "terra_charge_recovery_speed_inc", 0.75),
])
def test_terra_mod_lines_resolve(text, key, amount):
    from engine.mod_parser import _parse_custom_mod_text
    got = _parse_custom_mod_text(text)
    assert [(g["stat_key"], pytest.approx(g["amount"])) for g in got] == [(key, pytest.approx(amount))]


def test_terra_graft_compound_line_resolves():
    from engine.mod_parser import _parse_custom_mod_text
    got = _parse_custom_mod_text("Max Terra Charge Stacks +1 +(16–20) % additional Terra Skill Damage")
    assert {g["stat_key"]: g["amount"] for g in got} == {
        "max_terra_charge_stacks_flat": 1.0,
        "terra_skill_dmg_additional": pytest.approx(0.18),
    }
